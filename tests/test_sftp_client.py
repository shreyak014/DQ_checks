
import os
import stat
import sys
import unittest
from unittest.mock import MagicMock, patch, mock_open

import pytest
from paramiko import SFTPAttributes

# Add the project root to the Python path to allow importing 'sftp_to_gcs'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sftp_to_gcs import sftp_client

# --- Fixtures for Pytest ---

@pytest.fixture
def mock_sftp_conn(mocker):
    """Fixture to provide a mocked SFTPClient instance."""
    mock_conn = MagicMock()

    # Mock a simple directory structure: /
    #  - file1.txt
    #  - empty_dir/
    #  - dir_with_files/
    #    - file2.txt

    # Mock attributes for listdir_attr
    root_attrs = []
    attr1 = SFTPAttributes()
    attr1.filename = 'file1.txt'
    attr1.st_mode = stat.S_IFREG | 0o644 # Regular file
    attr1.st_size = 1024
    root_attrs.append(attr1)

    attr2 = SFTPAttributes()
    attr2.filename = 'empty_dir'
    attr2.st_mode = stat.S_IFDIR | 0o755 # Directory
    root_attrs.append(attr2)

    attr3 = SFTPAttributes()
    attr3.filename = 'dir_with_files'
    attr3.st_mode = stat.S_IFDIR | 0o755
    root_attrs.append(attr3)

    dir_with_files_attrs = []
    attr4 = SFTPAttributes()
    attr4.filename = 'file2.txt'
    attr4.st_mode = stat.S_IFREG | 0o644
    attr4.st_size = 2048
    dir_with_files_attrs.append(attr4)

    # Mock stat for directories
    mock_stat = MagicMock()
    mock_stat.st_mtime = 1672531200 # 2023-01-01

    mock_conn.listdir_attr.side_effect = [
        root_attrs,
        [], # for empty_dir
        dir_with_files_attrs
    ]
    mock_conn.stat.return_value = mock_stat

    return mock_conn

@pytest.fixture
def mock_gcs_client(mocker):
    """Fixture to provide a mocked GCS Client."""
    mock_storage_client = mocker.patch('sftp_to_gcs.sftp_client.storage.Client')
    mock_bucket = MagicMock()
    mock_blob = MagicMock()

    mock_storage_client.return_value.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    # Return all mocks to allow assertions on them
    return {
        "client": mock_storage_client,
        "bucket": mock_bucket,
        "blob": mock_blob,
    }


# --- Test Cases ---

def test_get_sftp_credentials_from_env(mocker):
    """Tests successful credential loading from environment variables."""
    mocker.patch.dict(os.environ, {
        "SFTP_HOST": "sftp.test.com",
        "SFTP_USER": "testuser",
        "SFTP_PASSWORD": "password123"
    })
    creds = sftp_client.get_sftp_credentials()
    assert creds["host"] == "sftp.test.com"
    assert creds["username"] == "testuser"
    assert creds["password"] == "password123"

def test_get_sftp_credentials_missing_vars():
    """Tests that a ValueError is raised if required env vars are missing."""
    with pytest.raises(ValueError, match="Missing required SFTP env vars"):
        sftp_client.get_sftp_credentials()

def test_list_sftp_folders_basic(mock_sftp_conn):
    """Tests basic recursive folder listing."""
    result = sftp_client.list_sftp_folders(mock_sftp_conn, root_path="/", include_files=False)

    # Expecting 3 directories: /, /empty_dir, /dir_with_files
    assert len(result) == 3
    paths = {item['path'] for item in result}
    assert "/" in paths
    assert "/empty_dir" in paths
    assert "/dir_with_files" in paths

def test_list_sftp_folders_with_files(mock_sftp_conn):
    """Tests folder listing with file counts and sizes."""
    result = sftp_client.list_sftp_folders(mock_sftp_conn, root_path="/", include_files=True)

    assert len(result) == 3

    # Find the stats for the root and dir_with_files
    root_stats = next(item for item in result if item['path'] == '/')
    dir_with_files_stats = next(item for item in result if item['path'] == '/dir_with_files')

    assert root_stats['num_files'] == 1
    assert root_stats['total_size_bytes'] == 1024
    assert dir_with_files_stats['num_files'] == 1
    assert dir_with_files_stats['total_size_bytes'] == 2048


def test_write_listing_to_local_json(mocker):
    """Tests writing listing to a JSON file."""
    mocked_open = mock_open()
    mocker.patch("builtins.open", mocked_open)
    mock_json_dump = mocker.patch("json.dump")

    listing = [{"path": "/test", "num_files": 1, "last_modified": 1672531200}]
    sftp_client.write_listing_to_local(listing, "/tmp/output.json", "json")

    mocked_open.assert_called_once_with("/tmp/output.json", "w")
    # Verify timestamp was converted to ISO format
    assert mock_json_dump.call_args[0][0][0]['last_modified'] == "2023-01-01T00:00:00"

def test_upload_to_gcs_versioned(mock_gcs_client):
    """Tests GCS upload with versioning."""
    sftp_client.upload_to_gcs("local.txt", "my-bucket", "prefix/object", on_conflict="versioned")

    # Assert blob was created with a timestamped name
    final_object_name = mock_gcs_client["bucket"].blob.call_args[0][0]
    assert final_object_name.startswith("prefix/object.")

    # Assert upload was called
    mock_gcs_client["blob"].upload_from_filename.assert_called_once_with("local.txt")

def test_upload_to_gcs_skip_if_exists(mock_gcs_client):
    """Tests that upload is skipped if the object exists and on_conflict is 'skip'."""
    mock_gcs_client["blob"].exists.return_value = True # Simulate object exists

    result_uri = sftp_client.upload_to_gcs("local.txt", "my-bucket", "prefix/object", on_conflict="skip")

    # Assert upload was NOT called
    mock_gcs_client["blob"].upload_from_filename.assert_not_called()
    # Assert the original object URI is returned
    assert result_uri == "gs://my-bucket/prefix/object"

def test_main_dry_run(mocker):
    """Tests that a dry run logs actions but does not perform them."""
    # Mock all external interactions
    mocker.patch('sftp_to_gcs.sftp_client.get_sftp_credentials', return_value={})
    mocker.patch('sftp_to_gcs.sftp_client.connect_sftp')
    mocker.patch('sftp_to_gcs.sftp_client.list_sftp_folders', return_value=[{"path": "/"}])
    mock_write = mocker.patch('sftp_to_gcs.sftp_client.write_listing_to_local')
    mock_upload = mocker.patch('sftp_to_gcs.sftp_client.upload_to_gcs')

    # Simulate CLI arguments for a dry run
    mocker.patch('sys.argv', [
        'sftp_client.py',
        '--gcs-bucket', 'test-bucket',
        '--dry-run'
    ])

    # Run main, expecting it to exit cleanly (code 0)
    with pytest.raises(SystemExit) as e:
        sftp_client.main()

    assert e.type == SystemExit
    assert e.value.code in [0, None] # A clean exit

    # Assert that write and upload were NOT called
    mock_write.assert_not_called()
    mock_upload.assert_not_called()
