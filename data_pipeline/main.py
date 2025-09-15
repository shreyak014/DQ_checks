import yaml
from src.input_handler import load_and_unify_data
from src.validator import validate_data
from src.output_handler import write_outputs, generate_report

def run_pipeline(config_path='data_pipeline/config.yaml'):
    """
    Runs the full data ingestion and validation pipeline.

    Args:
        config_path: The path to the configuration YAML file.
    """
    print("--- Starting Data Validation Pipeline ---")

    # --- 1. Load Configuration ---
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        file_settings = config['file_settings']
        validation_rules = config['validation_rules']
        print("Configuration loaded successfully.")
    except FileNotFoundError:
        print(f"Error: Configuration file not found at '{config_path}'")
        return
    except yaml.YAMLError as e:
        print(f"Error parsing YAML configuration: {e}")
        return
    except KeyError as e:
        print(f"Error: Missing critical key in configuration: {e}")
        return

    # --- 2. Load and Unify Data ---
    unified_df = load_and_unify_data(file_settings['input_path'])

    if unified_df.empty:
        print("Pipeline halted as no data was loaded.")
        return

    total_records = len(unified_df)

    # --- 3. Validate Data ---
    print("\n--- Starting Data Validation ---")
    clean_df, junk_df = validate_data(unified_df, validation_rules)
    print("--- Validation Finished ---\n")

    # --- 4. Write Outputs and Report ---
    print("--- Starting Output Generation ---")
    write_outputs(clean_df, junk_df, file_settings)
    generate_report(total_records, clean_df, junk_df, file_settings)
    print("--- Output Generation Finished ---")

    print("\n--- Data Validation Pipeline Completed Successfully ---")

if __name__ == "__main__":
    # To run the pipeline, you would execute this script.
    # For now, we are just setting up the structure.
    # In the testing phase, we will call run_pipeline().
    print("Main script loaded. Call run_pipeline() to execute the process.")
    # Example of how to run it:
    # run_pipeline()
