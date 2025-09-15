import os
import pandas as pd
from collections import Counter

def write_outputs(clean_df: pd.DataFrame, junk_df: pd.DataFrame, config: dict):
    """
    Saves the clean and junk DataFrames to the specified output path and format.

    Args:
        clean_df: The DataFrame containing clean data.
        junk_df: The DataFrame containing junk data.
        config: The file settings dictionary from the config.
    """
    output_path = config['output_path']
    output_format = config.get('output_format', 'parquet') # Default to parquet

    # Ensure the output directory exists
    os.makedirs(output_path, exist_ok=True)

    try:
        # --- Write Clean Data ---
        clean_filepath = os.path.join(output_path, f"{config['clean_filename']}.{output_format}")
        print(f"Writing clean data to {clean_filepath}...")
        if output_format == 'csv':
            clean_df.to_csv(clean_filepath, index=False)
        else: # parquet is the default
            clean_df.to_parquet(clean_filepath, index=False)
        print("...Done.")

        # --- Write Junk Data ---
        if not junk_df.empty:
            junk_filepath = os.path.join(output_path, f"{config['junk_filename']}.{output_format}")
            print(f"Writing junk data to {junk_filepath}...")
            if output_format == 'csv':
                junk_df.to_csv(junk_filepath, index=False)
            else:
                junk_df.to_parquet(junk_filepath, index=False)
            print("...Done.")

    except Exception as e:
        print(f"Error writing output files: {e}")

def generate_report(total_records: int, clean_df: pd.DataFrame, junk_df: pd.DataFrame, config: dict):
    """
    Generates a summary report of the validation process.

    Args:
        total_records: The initial total number of records.
        clean_df: The DataFrame containing clean data.
        junk_df: The DataFrame containing junk data.
        config: The file settings dictionary from the config.
    """
    output_path = config['output_path']
    report_filepath = os.path.join(output_path, config['report_filename'])

    # --- Calculate Statistics ---
    clean_records = len(clean_df)
    junk_records = len(junk_df)

    report_lines = [
        "========================================",
        "      Data Validation Summary Report      ",
        "========================================",
        f"Total Records Processed: {total_records}",
        f"Clean Records: {clean_records}",
        f"Junk Records: {junk_records}",
        "----------------------------------------",
        "Error Distribution:",
    ]

    if not junk_df.empty:
        # Consolidate all error messages from the 'error_reason' column
        all_errors = '; '.join(junk_df['error_reason'].dropna())
        # Split by the semicolon and strip whitespace to get individual errors
        error_list = [error.strip() for error in all_errors.split(';') if error.strip()]
        error_counts = Counter(error_list)

        if error_counts:
            for error, count in error_counts.items():
                report_lines.append(f"  - {error}: {count} records")
        else:
            report_lines.append("  No specific errors found in junk records.")
    else:
        report_lines.append("  No junk records were generated.")

    report_lines.append("========================================")

    # --- Write Report to File ---
    try:
        print(f"Generating validation report at {report_filepath}...")
        with open(report_filepath, 'w') as f:
            f.write('\n'.join(report_lines))
        print("...Report generated successfully.")
    except Exception as e:
        print(f"Error writing report file: {e}")
