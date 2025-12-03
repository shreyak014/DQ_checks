
"""
Airflow DAG to List SFTP Content and Upload to GCS

This DAG orchestrates the process of connecting to an SFTP server,
listing its contents, and uploading the listing to a GCS bucket using
the sftp_to_gcs.sftp_client module.
"""

import os
import sys
from datetime import datetime, timedelta

from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.models import Variable
from airflow.providers.sftp.hooks.sftp import SFTPHook

# --- Composer Deployment Notes ---
# To make the 'sftp_to_gcs' module importable in Composer, either:
# 1. Package the 'sftp_to_gcs' directory as a Python package and install it
#    in your Composer environment via PyPI.
# 2. Add the parent directory of 'dags' to the Python path. This is less
#    robust but simpler for small projects.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sftp_to_gcs import sftp_client

# --- DAG Configuration ---

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

def run_sftp_listing_for_airflow(**context):
    """
    Wrapper function for the PythonOperator to execute the SFTP listing.

    This function retrieves configuration from Airflow (Connections and Variables)
    and invokes the main function of the sftp_client module.
    """
    # 1. Set up SFTP credentials from an Airflow Connection
    sftp_hook = SFTPHook(ssh_conn_id='sftp_default')
    conn = sftp_hook.get_connection('sftp_default')

    os.environ['SFTP_HOST'] = conn.host
    os.environ['SFTP_USER'] = conn.login
    if conn.password:
        os.environ['SFTP_PASSWORD'] = conn.password
    # Assuming private key is stored in 'Extra' as a file path
    elif conn.extra_dejson.get('private_key_path'):
        os.environ['SFTP_PRIVATE_KEY_PATH'] = conn.extra_dejson['private_key_path']

    # 2. Get GCS and other parameters from Airflow Variables
    gcs_bucket = Variable.get("sftp_gcs_bucket")
    sftp_root = Variable.get("sftp_root_path", default_var="/")

    # 3. Build CLI arguments for the sftp_client
    # Use the DAG run's logical date for versioning the output file
    logical_date = context["ds_nodash"]
    gcs_prefix = f"sftp-listings/date={logical_date}/"

    sys.argv = [
        "sftp_client.py",
        "--root-path", sftp_root,
        "--gcs-bucket", gcs_bucket,
        "--gcs-prefix", gcs_prefix,
    ]

    # 4. Execute the client's main function
    sftp_client.main()


with DAG(
    dag_id="sftp_to_gcs_listing",
    default_args=default_args,
    description="Lists SFTP server content and uploads to GCS.",
    schedule_interval="@daily",
    start_date=datetime(2023, 1, 1),
    catchup=False,
    tags=["sftp", "gcs"],
) as dag:

    prepare = BashOperator(
        task_id="prepare",
        bash_command="echo 'Starting SFTP listing process for execution date: {{ ds }}...'",
    )

    run_sftp_listing = PythonOperator(
        task_id="run_sftp_listing",
        python_callable=run_sftp_listing_for_airflow,
    )

    notify = BashOperator(
        task_id="notify_success",
        bash_command="echo 'SFTP listing and upload completed successfully.'",
        # In a real scenario, this could be an email or Slack notification
    )

    prepare >> run_sftp_listing >> notify
