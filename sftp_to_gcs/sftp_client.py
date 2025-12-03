
import argparse
import json
import logging
import os
import paramiko
import stat
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

from google.cloud import storage
from google.api_core.exceptions import NotFound

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

def get_sftp_credentials() -> Dict[str, Any]:
    """
    Retrieves SFTP credentials from environment variables.
    Supports both password and private key authentication.
    """
    host = os.environ.get("SFTP_HOST")
    port = int(os.environ.get("SFTP_PORT", 22))
    user = os.environ.get("SFTP_USER")
    password = os.environ.get("SFTP_PASSWORD")
    private_key_path = os.environ.get("SFTP_PRIVATE_KEY_PATH")

    if not all([host, user, (password or private_key_path)]):
        raise ValueError("Missing required SFTP environment variables.")

    credentials = {
        "host": host,
        "port": port,
        "username": user,
    }
    if private_key_path:
        try:
            private_key = paramiko.RSAKey.from_private_key_file(private_key_path)
            credentials["pkey"] = private_key
        except Exception as e:
            logging.error(f"Failed to load private key from {private_key_path}: {e}")
            raise
    else:
        credentials["password"] = password

    return credentials

def list_sftp_folders(
    sftp_client: paramiko.SFTPClient, root_path: str
) -> List[Dict[str, Any]]:
    """
    Recursively lists all folders and files under a given root path on the SFTP server.
    """
    listing = []
    stack = [root_path]

    while stack:
        current_path = stack.pop()
        try:
            for item in sftp_client.listdir_attr(current_path):
                item_path = os.path.join(current_path, item.filename)
                if stat.S_ISDIR(item.st_mode):
                    stack.append(item_path)
                    listing.append({
                        "path": item_path,
                        "type": "directory",
                        "size": item.st_size,
                        "last_modified": item.st_mtime,
                    })
                else:
                    listing.append({
                        "path": item_path,
                        "type": "file",
                        "size": item.st_size,
                        "last_modified": item.st_mtime,
                    })
        except IOError as e:
            logging.warning(f"Could not access {current_path}: {e}")

    return listing

def write_listing_to_local(
    listing: List[Dict[str, Any]], output_path: str, format: str
) -> None:
    """
    Writes the file/folder listing to a local file in JSON or CSV format.
    """
    if format == "json":
        with open(output_path, "w") as f:
            json.dump(listing, f, indent=4)
    elif format == "csv":
        import csv
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=listing[0].keys())
            writer.writeheader()
            writer.writerows(listing)
    else:
        raise ValueError("Unsupported output format. Choose 'json' or 'csv'.")
    logging.info(f"Successfully wrote listing to {output_path}")

def upload_to_gcs(
    local_path: str, bucket_name: str, object_name: str, overwrite: bool = True
) -> None:
    """
    Uploads a local file to Google Cloud Storage.
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    if not overwrite:
        # Check if the object already exists
        blob = bucket.blob(object_name)
        if blob.exists():
            logging.info(f"Object {object_name} already exists in GCS. Skipping upload.")
            return

    # Add a timestamp to the object name for versioning
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    versioned_object_name = f"{object_name}_{timestamp}"

    blob = bucket.blob(versioned_object_name)
    blob.upload_from_filename(local_path)
    logging.info(f"File {local_path} uploaded to gs://{bucket_name}/{versioned_object_name}")

def main():
    parser = argparse.ArgumentParser(description="List SFTP folders and upload to GCS.")
    parser.add_argument("--root-path", required=True, help="Root path on the SFTP server.")
    parser.add_argument("--output-format", choices=["json", "csv"], default="json")
    parser.add_argument("--gcs-bucket", required=True, help="GCS bucket name.")
    parser.add_argument("--gcs-prefix", default="", help="GCS object prefix.")
    parser.add_argument("--dry-run", action="store_true", help="Run without uploading to GCS.")

    args = parser.parse_args()

    try:
        credentials = get_sftp_credentials()
        transport = paramiko.Transport((credentials["host"], credentials["port"]))
        transport.connect(
            username=credentials["username"],
            password=credentials.get("password"),
            pkey=credentials.get("pkey"),
        )
        sftp = paramiko.SFTPClient.from_transport(transport)

        logging.info(f"Connected to SFTP server: {credentials['host']}")

        listing = list_sftp_folders(sftp, args.root_path)

        if not listing:
            logging.info("No files or folders found.")
            return

        local_filename = f"sftp_listing_{datetime.utcnow().strftime('%Y%m%d')}.{args.output_format}"
        write_listing_to_local(listing, local_filename, args.output_format)

        if not args.dry_run:
            gcs_object_name = os.path.join(args.gcs_prefix, os.path.basename(local_filename))
            upload_to_gcs(local_filename, args.gcs_bucket, gcs_object_name)

    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
        exit(1)
    finally:
        if "transport" in locals() and transport.is_active():
            transport.close()
            logging.info("SFTP connection closed.")

if __name__ == "__main__":
    main()
