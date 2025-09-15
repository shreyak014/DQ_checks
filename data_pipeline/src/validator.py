import pandas as pd
import re

def _log_error(df: pd.DataFrame, mask: pd.Series, error_message: str) -> pd.DataFrame:
    """Appends an error message to the 'error_reason' column for rows where the mask is True."""
    if 'error_reason' not in df.columns:
        df['error_reason'] = pd.Series(dtype='object')
    df.loc[mask, 'error_reason'] = df.loc[mask, 'error_reason'].fillna('') + error_message + '; '
    return df

def validate_data(df: pd.DataFrame, rules: dict) -> (pd.DataFrame, pd.DataFrame):
    """
    Validates a DataFrame against a set of rules defined in a config dictionary.

    Args:
        df: The input DataFrame to validate.
        rules: A dictionary containing the validation rules.

    Returns:
        A tuple containing two DataFrames: (clean_df, junk_df).
    """
    # --- 1. Schema Conformance Check ---
    expected_columns = [col['name'] for col in rules['schema']]
    missing_columns = set(expected_columns) - set(df.columns)
    if missing_columns:
        df = _log_error(df, pd.Series([True] * len(df)), f"Missing critical columns: {', '.join(missing_columns)}")
        return pd.DataFrame(columns=df.columns), df

    # --- 2. Pre-emptive Data Type Conversion ---
    # This is crucial. Convert columns to their target types before any validation.
    for col_rule in rules['schema']:
        col_name = col_rule['name']
        if col_name in df.columns:
            target_dtype = col_rule['dtype']
            # Use astype for strings, converting everything first and then replacing 'nan'
            if target_dtype == 'str':
                df[col_name] = df[col_name].astype(str).replace('nan', pd.NA).replace('NaT', pd.NA)
            elif target_dtype == 'datetime':
                df[col_name] = pd.to_datetime(df[col_name], errors='coerce')
            elif target_dtype in ['int', 'float']:
                # For integers, we can't have NaNs. Let's convert to a float that allows NaNs first.
                df[col_name] = pd.to_numeric(df[col_name], errors='coerce')

    # --- 3. Row-level Validations ---
    for col_rule in rules['schema']:
        col_name = col_rule['name']

        # Nullable Check
        if not col_rule.get('nullable', True):
            mask = df[col_name].isnull()
            df = _log_error(df, mask, f"'{col_name}' cannot be null")

        # Format Check (for strings)
        if 'format' in col_rule and col_rule['dtype'] == 'str':
            # This check is now safe because the column is guaranteed to be of string type
            mask = ~df[col_name].str.match(f"^{col_rule['format']}$", na=True) & df[col_name].notna()
            df = _log_error(df, mask, f"Invalid format for '{col_name}'")

        # Range Check (for numerics)
        if 'range' in col_rule and col_rule['dtype'] in ['int', 'float']:
            min_val, max_val = col_rule['range'].get('min'), col_rule['range'].get('max')
            mask = ~df[col_name].between(min_val, max_val, inclusive='both') & df[col_name].notna()
            df = _log_error(df, mask, f"'{col_name}' out of range ({min_val}-{max_val})")

    # --- 4. Duplicate Record Check ---
    dup_cols = rules.get('duplicate_check_columns', [])
    if dup_cols:
        mask = df.duplicated(subset=dup_cols, keep=False)
        df = _log_error(df, mask, f"Duplicate record based on {', '.join(dup_cols)}")

    # --- 5. Split Data into Clean and Junk ---
    junk_mask = df['error_reason'].notna()
    junk_df = df[junk_mask].copy()
    clean_df = df[~junk_mask].drop(columns=['error_reason'])

    # Final type conversion for clean data to match schema (e.g., float -> int)
    for col_rule in rules['schema']:
        col_name = col_rule['name']
        if col_name in clean_df.columns and col_rule['dtype'] == 'int':
             # Convert to nullable integer type
            clean_df[col_name] = clean_df[col_name].astype('Int64')

    clean_df = clean_df[expected_columns]

    print(f"Validation complete. Clean records: {len(clean_df)}, Junk records: {len(junk_df)}")

    return clean_df, junk_df
