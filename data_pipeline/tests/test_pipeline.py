import os
import sys
import pandas as pd
import pytest

# Add the project root to the Python path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import run_pipeline

@pytest.fixture(scope="module")
def pipeline_output():
    """
    A pytest fixture to run the pipeline once and make its output
    paths available to all tests in this module.
    """
    # Define paths based on the config
    config = {
        'output_path': 'data_pipeline/data/output',
        'clean_filename': 'clean_data',
        'junk_filename': 'junk_data',
        'report_filename': 'validation_report.log',
        'output_format': 'parquet'
    }

    # Run the pipeline
    run_pipeline()

    # Provide the paths to the tests
    return {
        "clean_path": os.path.join(config['output_path'], f"{config['clean_filename']}.{config['output_format']}"),
        "junk_path": os.path.join(config['output_path'], f"{config['junk_filename']}.{config['output_format']}"),
        "report_path": os.path.join(config['output_path'], config['report_filename'])
    }

def test_output_files_exist(pipeline_output):
    """Test that the pipeline creates the expected output files."""
    assert os.path.exists(pipeline_output["clean_path"]), "Clean data file was not created."
    assert os.path.exists(pipeline_output["junk_path"]), "Junk data file was not created."
    assert os.path.exists(pipeline_output["report_path"]), "Report file was not created."

def test_record_counts(pipeline_output):
    """Test that the number of clean and junk records is correct."""
    clean_df = pd.read_parquet(pipeline_output["clean_path"])
    junk_df = pd.read_parquet(pipeline_output["junk_path"])

    # Total records = 7 from CSV + 3 from JSON = 10
    # Expected clean = Bob (102), David (104), Eve (201) = 3
    # Expected junk = 7
    assert len(clean_df) == 3, f"Expected 3 clean records, but found {len(clean_df)}"
    assert len(junk_df) == 7, f"Expected 7 junk records, but found {len(junk_df)}"

def test_clean_data_content(pipeline_output):
    """Test that the clean data file contains the correct, valid records."""
    clean_df = pd.read_parquet(pipeline_output["clean_path"])
    # Check that the correct user_ids are in the clean file
    expected_clean_ids = {102, 104, 201}
    assert set(clean_df['user_id']) == expected_clean_ids

def test_junk_data_reasons(pipeline_output):
    """Test that junk records have the correct error reasons."""
    junk_df = pd.read_parquet(pipeline_output["junk_path"])

    # Convert to a dictionary for easier lookup
    junk_records = junk_df.set_index('user_id')['error_reason'].to_dict()

    # Alice (101) - a duplicate
    assert "Duplicate record" in junk_records[101]

    # Charlie (103) - multiple errors
    assert "Invalid format for 'email'" in junk_records[103]
    assert "Invalid format for 'phone_number'" in junk_records[103]
    assert "'age' out of range" in junk_records[103]

    # Peter (202) - age out of range
    assert "'age' out of range" in junk_records[202]

    # John (203) - null email
    assert "'email' cannot be null" in junk_records[203]

    # Frank (null user_id) - special case, check by another field
    frank_record = junk_df[junk_df['user_name'] == 'Frank'].iloc[0]
    assert "'user_id' cannot be null" in frank_record['error_reason']

    # Ivy (204) - invalid email
    assert "Invalid format for 'email'" in junk_records[204]

def test_report_content(pipeline_output):
    """Test that the validation report contains accurate statistics."""
    with open(pipeline_output["report_path"], 'r') as f:
        report_content = f.read()

    assert "Total Records Processed: 10" in report_content
    assert "Clean Records: 3" in report_content
    assert "Junk Records: 7" in report_content
    assert "Duplicate record based on user_id, email: 2 records" in report_content
    assert "'age' out of range (18-120): 2 records" in report_content
    assert "'email' cannot be null: 1 records" in report_content
    assert "'user_id' cannot be null: 1 records" in report_content
    assert "Invalid format for 'email': 2 records" in report_content
