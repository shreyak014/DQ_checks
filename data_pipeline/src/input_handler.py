import os
import pandas as pd

def load_and_unify_data(input_path: str) -> pd.DataFrame:
    """
    Scans a directory for files, loads them into pandas DataFrames, and
    unifies them into a single DataFrame. It reads data from CSV/JSON/Excel
    as strings by default to prevent incorrect type inference.

    Args:
        input_path: The path to the directory containing the input files.

    Returns:
        A single pandas DataFrame containing the combined data from all files.
    """
    if not os.path.isdir(input_path):
        print(f"Error: Input path '{input_path}' is not a valid directory.")
        return pd.DataFrame()

    all_data = []
    # Instruct pandas to read all data as strings to avoid type inference issues
    # (e.g., phone numbers becoming floats). The validator will handle conversions.
    supported_formats = {
        '.csv': lambda path: pd.read_csv(path, dtype=str),
        '.json': lambda path: pd.read_json(path, dtype=str),
        '.xlsx': lambda path: pd.read_excel(path, dtype=str),
        '.parquet': pd.read_parquet # Parquet has its own schema, so we trust it.
    }

    print(f"Scanning for files in '{input_path}'...")
    for filename in os.listdir(input_path):
        file_path = os.path.join(input_path, filename)
        file_extension = os.path.splitext(filename)[1].lower()

        if file_extension in supported_formats:
            try:
                print(f"  - Reading file: {filename}")
                df = supported_formats[file_extension](file_path)
                all_data.append(df)
            except Exception as e:
                print(f"Error reading {filename}: {e}")
        else:
            print(f"  - Skipping unsupported file format: {filename}")

    if not all_data:
        print("No data files found or loaded.")
        return pd.DataFrame()

    unified_df = pd.concat(all_data, ignore_index=True)
    print(f"Successfully loaded and unified {len(all_data)} files. Total records: {len(unified_df)}")

    return unified_df
