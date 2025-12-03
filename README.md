
# SFTP to GCS Listing Project

This project contains a Python module and an Airflow DAG designed to connect to an SFTP server, list its files and folders, and upload the listing to a Google Cloud Storage (GCS) bucket.

## Project Structure

```
.
├── dags/
│   └── sftp_to_gcs_dag.py     # Airflow DAG for orchestration
├── sftp_to_gcs/
│   └── sftp_client.py         # Core Python module for SFTP and GCS logic
├── tests/
│   └── test_sftp_client.py    # Unit tests for the sftp_client module
├── examples/
│   └── config.example.yaml    # Example configuration (not used directly by the DAG)
├── requirements.txt           # Python dependencies
└── README.md                  # This documentation file
```

## Deployment to GCP Composer

### 1. Uploading Files to the Composer Bucket

Only the `dags/` and `sftp_to_gcs/` directories need to be uploaded to your GCP Composer environment's GCS bucket.

Use `gsutil` to sync the directories:
```bash
# Replace <YOUR_COMPOSER_BUCKET> with your environment's bucket name
gsutil -m rsync -r dags/ gs://<YOUR_COMPOSER_BUCKET>/dags/
gsutil -m rsync -r sftp_to_gcs/ gs://<YOUR_COMPOSER_BUCKET>/dags/sftp_to_gcs/
```

### 2. Installing Python Dependencies

The `sftp_client.py` module has dependencies that need to be installed in your Composer environment. You can do this by updating the "PyPI Packages" section in your Composer environment's configuration in the GCP Console.

Add the following packages from `requirements.txt`:
- `paramiko`
- `google-cloud-storage`
- `apache-airflow` (usually already present in Composer)

### 3. Configuring Airflow Connections and Variables

**a. SFTP Connection:**

Create an Airflow Connection with the ID `sftp_default`:
- **Conn Type:** `SFTP`
- **Host:** Your SFTP server's hostname or IP
- **Port:** Your SFTP server's port (e.g., 22)
- **Login:** Your SFTP username
- **Password:** Your SFTP password (if using password authentication)
- **Extra:** (for private key authentication) `{"private_key_path": "/path/to/your/keyfile"}`
  (Note: The key file must be accessible from the Composer worker nodes)

**b. Airflow Variables:**

Create the following Airflow Variables:
- `sftp_gcs_bucket`: The name of the GCS bucket where the listings will be stored (e.g., `my-sftp-listings`).
- `sftp_root_path`: The root directory on the SFTP server to start listing from (e.g., `/`).

## Local Testing

### 1. Set up a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set Environment Variables

```bash
export SFTP_HOST="your_sftp_host"
export SFTP_PORT="22"
export SFTP_USER="your_sftp_user"
export SFTP_PASSWORD="your_sftp_password" # or SFTP_PRIVATE_KEY_PATH
```

### 3. Run the SFTP Client Script

```bash
python -m sftp_to_gcs.sftp_client \
    --root-path "/" \
    --gcs-bucket "your-gcs-bucket" \
    --dry-run
```

### 4. Run Unit Tests

```bash
pytest tests/
```

## Troubleshooting

- **SFTP Authentication Errors:** Double-check your SFTP credentials in the Airflow Connection. Ensure that the Composer worker nodes can access the SFTP server (firewall rules).
- **GCS Permissions:** The service account used by your Composer environment needs the `roles/storage.objectCreator` role on the destination GCS bucket.
- **Composer DAG Sync Delays:** It can take a few minutes for new or updated DAGs to appear in the Airflow UI.
- **Module Not Found Errors:** Make sure you have uploaded the `sftp_to_gcs` directory correctly and that the dependencies are installed in your Composer environment.
