# SFTP to GCS Listing Project

This project provides a reusable solution for listing the contents of an SFTP server and uploading the listing to a Google Cloud Storage (GCS) bucket. It includes a core Python module and an Airflow DAG for orchestration.

## Project Structure

-   `sftp_to_gcs/sftp_client.py`: The main Python module containing all logic for SFTP connection, file listing, and GCS upload. It can be run as a standalone CLI script.
-   `dags/sftp_to_gcs_dag.py`: The Airflow 2.x DAG that orchestrates the execution of the `sftp_client` on a schedule.
-   `requirements.txt`: A list of all Python dependencies required for this project.
-   `tests/test_sftp_client.py`: Unit tests for the core `sftp_client` module, using `pytest`.
-   `examples/config.example.yaml`: An example configuration file showing the expected structure (for reference, not used by the DAG).
-   `README.md`: This documentation file.

## Local Testing and Development

### 1. Setup Environment

First, create and activate a Python virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Then, install the required dependencies:

```bash
pip install -r requirements.txt
```

### 2. Configure Credentials

Export the necessary SFTP credentials as environment variables.

**Using Password Authentication:**

```bash
export SFTP_HOST="your-sftp-host.com"
export SFTP_PORT="22"
export SFTP_USER="your-username"
export SFTP_PASSWORD="your-password"
```

**Using Private Key Authentication:**

```bash
export SFTP_HOST="your-sftp-host.com"
export SFTP_USER="your-username"
export SFTP_PRIVATE_KEY_PATH="/path/to/your/id_rsa"
```

### 3. Run the Client Script

You can run the script directly for testing. Use the `--dry-run` flag to prevent any actual file writes or uploads.

```bash
python -m sftp_to_gcs.sftp_client \
    --root-path "/remote/path" \
    --gcs-bucket "your-gcs-bucket-name" \
    --gcs-prefix "sftp-listings/" \
    --dry-run
```

### 4. Run Unit Tests

To ensure the core logic is working correctly, run the unit tests:

```bash
pytest tests/
```

## Deployment to GCP Composer

### 1. Deploying the Code

You need to sync both the `dags/` and the `sftp_to_gcs/` directories to your Composer environment's GCS bucket.

```bash
# Replace <YOUR_COMPOSER_BUCKET> with your environment's bucket name
# Sync the DAG file
gsutil -m rsync -r dags/ gs://<YOUR_COMPOSER_BUCKET>/dags/

# Sync the sftp_to_gcs module
gsutil -m rsync -r sftp_to_gcs/ gs://<YOUR_COMPOSER_BUCKET>/dags/sftp_to_gcs/
```

### 2. Installing Dependencies

The Python packages listed in `requirements.txt` must be installed in your Composer environment. You can do this via the GCP Console under your Composer environment's "PyPI Packages" tab.

**Required Packages:**
-   `paramiko`
-   `google-cloud-storage`
-   `tenacity`

### 3. Configuring Airflow

**a. Airflow Connection:**

Create an Airflow Connection with the ID `sftp_default`.
-   **Conn Id:** `sftp_default`
-   **Conn Type:** `SFTP`
-   **Host:** Your SFTP server's hostname
-   **Port:** `22`
-   **Login:** Your SFTP username
-   **Password:** Your SFTP password (if using password auth)
-   **Extra:** `{"private_key_path": "/path/to/private_key_in_worker"}` (if using key auth)

**b. Airflow Variables:**

Create the following Airflow Variables:
-   `sftp_gcs_bucket`: The name of the GCS bucket for uploads (e.g., `my-sftp-data`).
-   `sftp_root_path`: The root directory to list on the SFTP server (e.g., `/`).

## Troubleshooting

-   **SFTP Authentication Errors:**
    -   Verify credentials in the `sftp_default` Airflow Connection.
    -   Ensure Composer's network has access to the SFTP server (check firewall rules).
-   **GCS Permission Errors:**
    -   The service account for your Composer environment needs the `Storage Object Creator` (`roles/storage.objectCreator`) role on the target GCS bucket.
-   **DAG Not Appearing in UI:**
    -   It can take a few minutes for Composer to sync and parse new DAGs. Check the logs for parsing errors.
-   **`ModuleNotFoundError: No module named 'sftp_to_gcs'`:**
    -   Ensure you have correctly uploaded the `sftp_to_gcs` directory to `gs://<BUCKET>/dags/sftp_to_gcs/`.

## `sftp_client.py` Exit Codes

The script uses the following exit codes to indicate outcomes:
-   `0`: Success.
-   `1`: An unexpected or general error occurred.
-   `2`: Configuration error (e.g., missing environment variables).
-   `3`: SFTP connection or authentication error.
-   `4`: GCS upload error.
