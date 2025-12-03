
import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import sys

# Add the project root to the Python path to allow importing 'sftp_to_gcs'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sftp_to_gcs import sftp_client

class TestSftpClient(unittest.TestCase):

    @patch.dict(os.environ, {
        "SFTP_HOST": "testhost",
        "SFTP_PORT": "2222",
        "SFTP_USER": "testuser",
        "SFTP_PASSWORD": "testpassword"
    })
    def test_get_sftp_credentials_password(self):
        """Test that SFTP credentials are correctly loaded from environment variables (password auth)."""
        creds = sftp_client.get_sftp_credentials()
        self.assertEqual(creds['host'], 'testhost')
        self.assertEqual(creds['port'], 2222)
        self.assertEqual(creds['username'], 'testuser')
        self.assertEqual(creds['password'], 'testpassword')
        self.assertNotIn('pkey', creds)

    @patch('paramiko.RSAKey.from_private_key_file')
    @patch.dict(os.environ, {
        "SFTP_HOST": "testhost",
        "SFTP_USER": "testuser",
        "SFTP_PRIVATE_KEY_PATH": "/keys/id_rsa"
    })
    def test_get_sftp_credentials_private_key(self, mock_from_private_key_file):
        """Test that SFTP credentials are correctly loaded when using a private key."""
        mock_key = MagicMock()
        mock_from_private_key_file.return_value = mock_key

        creds = sftp_client.get_sftp_credentials()
        self.assertEqual(creds['host'], 'testhost')
        self.assertEqual(creds['username'], 'testuser')
        self.assertEqual(creds['pkey'], mock_key)
        self.assertNotIn('password', creds)
        mock_from_private_key_file.assert_called_once_with("/keys/id_rsa")

    def test_list_sftp_folders(self):
        """Test the recursive listing of SFTP folders and files."""
        mock_sftp_client = MagicMock()

        # Mock the directory structure
        mock_root_attrs = [MagicMock(), MagicMock()]
        mock_root_attrs[0].filename = 'dir1'
        mock_root_attrs[0].st_mode = 16877 # Directory
        mock_root_attrs[1].filename = 'file1.txt'
        mock_root_attrs[1].st_mode = 33188 # File

        mock_dir1_attrs = [MagicMock()]
        mock_dir1_attrs[0].filename = 'file2.txt'
        mock_dir1_attrs[0].st_mode = 33188 # File

        mock_sftp_client.listdir_attr.side_effect = [
            mock_root_attrs,
            mock_dir1_attrs
        ]

        result = sftp_client.list_sftp_folders(mock_sftp_client, "/")

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['path'], '/dir1')
        self.assertEqual(result[1]['path'], '/file1.txt')
        self.assertEqual(result[2]['path'], '/dir1/file2.txt')
        self.assertEqual(mock_sftp_client.listdir_attr.call_count, 2)


    @patch("builtins.open", new_callable=mock_open)
    def test_write_listing_to_local_json(self, mock_file):
        """Test writing the listing to a local JSON file."""
        listing = [{"path": "/file.txt", "type": "file"}]
        sftp_client.write_listing_to_local(listing, "output.json", "json")
        mock_file.assert_called_once_with("output.json", "w")
        # Check that json.dump was called with the correct data
        # Note: Accessing the write calls requires a bit more setup with mock_open,
        # but for this purpose, we just check if the file was opened for writing.

    @patch('google.cloud.storage.Client')
    def test_upload_to_gcs(self, mock_gcs_client):
        """Test that the file is uploaded to GCS with the correct parameters."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_gcs_client.return_value.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        sftp_client.upload_to_gcs("local/file.txt", "my-bucket", "gcs/prefix/file.txt")

        mock_gcs_client.return_value.bucket.assert_called_once_with("my-bucket")
        self.assertTrue(mock_bucket.blob.call_args[0][0].startswith("gcs/prefix/file.txt"))
        mock_blob.upload_from_filename.assert_called_once_with("local/file.txt")


if __name__ == '__main__':
    unittest.main()
