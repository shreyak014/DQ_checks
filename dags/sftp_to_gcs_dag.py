
from __future__ import annotations

import pendulum
import os
import sys

from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.sftp.hooks.sftp import SFTPHook
from airflow.models import Variable

# This is a common pattern for Composer, where the dags folder is at the root.
# To make the 'sftp_to_gcs' module importable, we add its parent directory to the path.
# For this to work, the 'sftp_to_gcs' folder must be placed alongside the 'dags' folder
# in the GCS bucket.
# A more robust solution is to package 'sftp_to_gcs' and install it as a PyPI dependency
# in the Composer environment. This is explained in the README.md.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sftp_to_gcs import sftp_client

def sftp_listing_task(**context):
    """
    Wrapper function to be called by the PythonOperator.
    This function sets up credentials from an Airflow SFTP connection
    and calls the main logic from the sftp_client module.
    """
    # 1. Get SFTP credentials from Airflow connection
    # The connection ID 'sftp_default' should be created in the Airflow UI.
    sftp_hook = SFTPHook(ssh_conn_id='sftp_default')
    conn = sftp_hook.get_connection('sftp_default')

    # Set credentials as environment variables for sftp_client to consume
    os.environ['SFTP_HOST'] = conn.host
    os.environ['SFTP_PORT'] = str(conn.port or 22)
    os.environ['SFTP_USER'] = conn.login

    # sftp_client supports password or private key.
    if conn.password:
        os.environ['SFTP_PASSWORD'] = conn.password
    elif conn.extra_dejson.get('private_key_path'):
        os.environ['SFTP_PRIVATE_KEY_PATH'] = conn.extra_dejson.get('private_key_path')
    else:
        raise ValueError("SFTP Connection 'sftp_default' must have a password or a private_key_path in 'Extra'.")

    # 2. Get parameters from Airflow Variables
    gcs_bucket = Variable.get("sftp_gcs_bucket")
    sftp_root_path = Variable.get("sftp_root_path")

    # 3. Use execution date to create a versioned output path
    execution_date = context["ds"]
    gcs_prefix = f"sftp-listings/date={execution_date}"

    # 4. Mock command-line arguments and call the main function
    original_argv = sys.argv
    sys.argv = [
        'sftp_client.py',
        '--root-path', sftp_root_path,
        '--gcs-bucket', gcs_bucket,
        '--gcs-prefix', gcs_prefix,
        '--output-format', 'json',
    ]

    try:
        sftp_client.main()
    finally:
        # Restore original argv
        sys.argv = original_argv


with DAG(
    dag_id="sftp_to_gcs_listing",
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    schedule="@daily",
    catchup=False,
    tags=["sftp", "gcs"],
    doc_md="""
    ### SFTP to GCS Listing DAG

    This DAG connects to an SFTP server, lists files and folders,
    and uploads the listing to a GCS bucket.

    **Configuration:**
    - Requires an Airflow Connection with ID `sftp_default`.
    - Requires Airflow Variables:
      - `sftp_gcs_bucket`: The destination GCS bucket.
      - `sftp_root_path`: The root directory to list on the SFTP server.
    """,
) as dag:

    prepare_task = BashOperator(
        task_id="prepare",
        bash_command="echo 'Starting SFTP listing...'",
    )

    run_sftp_listing = PythonOperator(
        task_id="run_sftp_listing",
        python_callable=sftp_listing_task,
    )

    notify_success = BashOperator(
        task_id="notify_success",
        bash_command="echo 'SFTP listing completed successfully.'",
    )

    prepare_task >> run_sftp_listing >> notify_success
