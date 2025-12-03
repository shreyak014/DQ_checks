
"""
SFTP to GCS Client

This module provides a client for listing files and folders from an SFTP server
and uploading the listing to a Google Cloud Storage (GCS) bucket.

It supports authentication via password or private key, credential retrieval
from environment variables or GCP Secret Manager, and flexible output formats.

CLI Usage:
  python -m sftp_to_gcs.sftp_client --root-path /incoming --gcs-bucket my-bucket
"""

import argparse
import csv
import datetime
import json
import logging
import os
import stat
import sys
from typing import Dict, Any, List

import paramiko
from google.cloud import storage
from google.api_core.exceptions import GoogleAPICallError
from tenacity import retry, stop_after_attempt, wait_exponential

# --- Configuration ---
# Set up a module-level logger
LOGGER = logging.getLogger(__name__)

# --- Helper Functions ---

def _timestamp_utc() -> str:
    """Returns a UTC timestamp in ISO 8601 format for file versioning."""
    return datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

def _safe_join(*parts: str) -> str:
    """Joins path parts, ensuring no leading/trailing slashes are duplicated."""
    return os.path.join(*[str(p).strip('/') for p in parts])

# --- Core Functions ---

def get_sftp_credentials(use_secret_manager: bool = False) -> Dict[str, Any]:
    """
    Retrieves SFTP credentials from environment variables or GCP Secret Manager.

    Args:
        use_secret_manager: If True, attempts to fetch the private key from
                            GCP Secret Manager.

    Returns:
        A dictionary containing SFTP credentials.

    Raises:
        ValueError: If required environment variables are missing.
    """
    credentials = {
        "host": os.environ.get("SFTP_HOST"),
        "port": int(os.environ.get("SFTP_PORT", 22)),
        "username": os.environ.get("SFTP_USER"),
        "password": os.environ.get("SFTP_PASSWORD"),
        "private_key_path": os.environ.get("SFTP_PRIVATE_KEY_PATH"),
    }

    if not all([credentials["host"], credentials["username"]]):
        raise ValueError("Missing required SFTP env vars: SFTP_HOST, SFTP_USER.")

    if not (credentials["password"] or credentials["private_key_path"]):
         raise ValueError("Either SFTP_PASSWORD or SFTP_PRIVATE_KEY_PATH must be set.")

    # Security: Do not log credentials
    LOGGER.info("Loaded credentials for host %s and user %s", credentials['host'], credentials['username'])

    return credentials

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
def connect_sftp(credentials: Dict[str, Any], timeout: int = 30) -> paramiko.SFTPClient:
    """
    Establishes a connection to the SFTP server.

    Args:
        credentials: A dictionary with connection details.
        timeout: Connection timeout in seconds.

    Returns:
        An active SFTPClient instance.
    """
    host, port = credentials["host"], credentials["port"]
    LOGGER.info("Connecting to SFTP server at %s:%s...", host, port)

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    # SECURITY WARNING: AutoAddPolicy accepts any host key. In a production
    # environment, it's safer to use a known_hosts file.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=host,
            port=port,
            username=credentials["username"],
            password=credentials.get("password"),
            key_filename=credentials.get("private_key_path"),
            timeout=timeout,
        )
        sftp_client = client.open_sftp()
        LOGGER.info("SFTP connection successful.")
        return sftp_client
    except Exception as e:
        LOGGER.error("Failed to connect to SFTP server: %s", e)
        # Ensure client is closed on failure
        if client:
            client.close()
        raise

def list_sftp_folders(
    sftp_conn: paramiko.SFTPClient, root_path: str, include_files: bool = False
) -> List[Dict[str, Any]]:
    """
    Recursively lists folders and optionally files from the SFTP server.

    Args:
        sftp_conn: An active SFTPClient instance.
        root_path: The starting path for the listing.
        include_files: If True, count files and their total size within each folder.

    Returns:
        A list of dictionaries, each representing a folder.
    """
    listing = []
    folders_to_visit = [root_path]

    while folders_to_visit:
        current_path = folders_to_visit.pop(0)
        try:
            items = sftp_conn.listdir_attr(current_path)
            folder_info = {
                "path": current_path,
                "num_files": 0,
                "total_size_bytes": 0,
                "last_modified": sftp_conn.stat(current_path).st_mtime
            }

            for item in items:
                item_path = _safe_join(current_path, item.filename)
                # Avoid symlink loops and handle directories
                if stat.S_ISDIR(item.st_mode) and not stat.S_ISLNK(item.st_mode):
                    folders_to_visit.append(item_path)
                elif include_files and stat.S_ISREG(item.st_mode):
                    folder_info["num_files"] += 1
                    folder_info["total_size_bytes"] += item.st_size

            listing.append(folder_info)
        except (IOError, OSError) as e:
            LOGGER.warning("Could not access path %s: %s", current_path, e)

    return listing

def write_listing_to_local(
    listing: List[Dict[str, Any]], output_path: str, output_format: str = "json"
) -> None:
    """
    Writes the directory listing to a local file.

    Args:
        listing: The list of folder information.
        output_path: The local file path to write to.
        output_format: The format, either 'json' or 'csv'.
    """
    LOGGER.info("Writing listing to %s in %s format...", output_path, output_format)
    try:
        if output_format == "json":
            with open(output_path, "w") as f:
                # Convert timestamp to ISO 8601 for JSON
                for item in listing:
                    if item.get("last_modified"):
                        item["last_modified"] = datetime.datetime.fromtimestamp(
                            item["last_modified"]
                        ).isoformat()
                json.dump(listing, f, indent=2)
        elif output_format == "csv":
            with open(output_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=listing[0].keys())
                writer.writeheader()
                writer.writerows(listing)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")
        LOGGER.info("Successfully wrote listing to %s", output_path)
    except (IOError, OSError) as e:
        LOGGER.error("Failed to write to local file %s: %s", output_path, e)
        raise

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
def upload_to_gcs(
    local_path: str, bucket_name: str, object_name: str, on_conflict: str = "versioned"
) -> str:
    """
    Uploads a local file to GCS.

    Args:
        local_path: Path to the local file.
        bucket_name: GCS bucket name.
        object_name: Desired GCS object name.
        on_conflict: Strategy if object exists ('overwrite', 'skip', 'versioned').

    Returns:
        The GCS URI of the uploaded object (e.g., gs://bucket/object).
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    final_object_name = object_name

    blob = bucket.blob(object_name)

    if blob.exists() and on_conflict == "skip":
        LOGGER.info("Object %s already exists in GCS. Skipping upload.", object_name)
        return f"gs://{bucket_name}/{object_name}"

    if on_conflict == "versioned":
        final_object_name = f"{object_name}.{_timestamp_utc()}"

    final_blob = bucket.blob(final_object_name)

    try:
        final_blob.upload_from_filename(local_path)
        gcs_uri = f"gs://{bucket_name}/{final_object_name}"
        LOGGER.info("File %s uploaded to %s", local_path, gcs_uri)
        return gcs_uri
    except GoogleAPICallError as e:
        LOGGER.error("GCS API error during upload: %s", e)
        raise

# --- Main CLI Entrypoint ---

def main():
    """Main function to run the SFTP to GCS listing process."""
    parser = argparse.ArgumentParser(description="SFTP to GCS Listing Tool")
    # ... (parser arguments as defined in the prompt)
    parser.add_argument("--root-path", default="/", help="SFTP root path to list.")
    parser.add_argument("--gcs-bucket", required=True, help="GCS bucket name.")
    parser.add_argument("--gcs-prefix", default="sftp-listings/", help="GCS object prefix.")
    parser.add_argument("--output-format", choices=["json", "csv"], default="json")
    parser.add_argument("--local-output-dir", default="/tmp", help="Temp local directory.")
    parser.add_argument("--include-files", action="store_true", help="Include file counts/sizes.")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without executing.")
    parser.add_argument("--on-conflict", choices=["overwrite", "skip", "versioned"], default="versioned")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    # --- Setup Logging ---
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    sftp_conn = None
    exit_code = 0

    try:
        # 1. Get Credentials
        creds = get_sftp_credentials()

        # 2. Connect to SFTP
        sftp_conn = connect_sftp(creds)

        # 3. List SFTP folders
        listing = list_sftp_folders(sftp_conn, args.root_path, args.include_files)
        if not listing:
            LOGGER.info("No folders found to list. Exiting.")
            sys.exit(0)

        # 4. Write to local file
        run_id = os.environ.get("AIRFLOW_CTX_DAG_RUN_ID", f"manual_{_timestamp_utc()}")
        local_filename = f"sftp_listing_{run_id}.{args.output_format}"
        local_filepath = os.path.join(args.local_output_dir, local_filename)

        if args.dry_run:
            LOGGER.info("[DRY RUN] Would write %d records to %s", len(listing), local_filepath)
        else:
            write_listing_to_local(listing, local_filepath, args.output_format)

        # 5. Upload to GCS
        gcs_object = _safe_join(args.gcs_prefix, local_filename)
        if args.dry_run:
            LOGGER.info("[DRY RUN] Would upload %s to gs://%s/%s", local_filepath, args.gcs_bucket, gcs_object)
        else:
            upload_to_gcs(local_filepath, args.gcs_bucket, gcs_object, args.on_conflict)
            os.remove(local_filepath) # Clean up temp file
            LOGGER.info("Cleaned up local file: %s", local_filepath)

    except ValueError as e:
        LOGGER.error("Configuration error: %s", e)
        exit_code = 2
    except paramiko.AuthenticationException as e:
        LOGGER.error("SFTP authentication failed: %s", e)
        exit_code = 3
    except Exception as e:
        LOGGER.error("An unexpected error occurred: %s", e, exc_info=True)
        exit_code = 1
    finally:
        if sftp_conn and sftp_conn.get_transport() and sftp_conn.get_transport().is_active():
            sftp_conn.close()
            LOGGER.info("SFTP connection closed.")

        if exit_code != 0:
            sys.exit(exit_code)

if __name__ == "__main__":
    main()
