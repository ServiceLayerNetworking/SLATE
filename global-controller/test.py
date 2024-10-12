import pandas as pd
import numpy as np
temp_counter=69
def jump_towards_optimizer_desired(starting_df: pd.DataFrame, desired_df: pd.DataFrame, cur_convex_comb_value: float) -> pd.DataFrame:
    global temp_counter
    """
    jump_towards_optimizer_desired computes the convex combination of two traffic matrices
    represented by starting_df and desired_df based on cur_convex_comb_value.
    
    Args:
        starting_df (pd.DataFrame): The starting traffic matrix DataFrame.
        desired_df (pd.DataFrame): The desired traffic matrix DataFrame.
        cur_convex_comb_value (float): The convex combination factor (between 0 and 1).
        
    Returns:
        pd.DataFrame: The new traffic matrix as a DataFrame in the same format as the inputs.
    """
    # Validate cur_convex_comb_value
    if not (0 <= cur_convex_comb_value <= 1):
        raise ValueError("cur_convex_comb_value must be between 0 and 1.")
    

    required_columns = {'src_svc', 'dst_svc'}
    for df_name, df in zip(['starting_df', 'desired_df'], [starting_df, desired_df]):
        if not required_columns.issubset(df.columns):
            raise ValueError(f"{df_name} must contain columns: {required_columns}")
        
    # Function to compute traffic matrix from DataFrame
    def compute_traffic_matrix(df):
        filtered = df[(df['src_svc'] == 'sslateingress') & (df['dst_svc'] == 'frontend')]
        traffic_matrix = filtered.pivot_table(
            index='src_cid',
            columns='dst_cid',
            values='weight',
            aggfunc='sum',
            fill_value=0
        )
        return traffic_matrix

    # Compute traffic matrices for starting and desired DataFrames
    starting_matrix = compute_traffic_matrix(starting_df)
    desired_matrix = compute_traffic_matrix(desired_df)
    
    # Identify all unique regions across both matrices
    all_regions = sorted(set(starting_matrix.index).union(set(starting_matrix.columns))
                        .union(set(desired_matrix.index)).union(set(desired_matrix.columns)))
    
    starting_matrix = starting_matrix.reindex(index=all_regions, columns=all_regions, fill_value=0)
    desired_matrix = desired_matrix.reindex(index=all_regions, columns=all_regions, fill_value=0)
    
    # Compute the convex combination
    combined_matrix = (1 - cur_convex_comb_value) * starting_matrix + cur_convex_comb_value * desired_matrix
    combined_matrix = combined_matrix.round(6)
    # logger.info(f"loghill (defensive jumping) new traffic matrix:\n{combined_matrix}")
    
    # Transform the combined matrix back into a DataFrame
    combined_df = combined_matrix.reset_index().melt(id_vars='src_cid', var_name='dst_cid', value_name='weight')
    combined_df = combined_df[combined_df['weight'] > 0].reset_index(drop=True)
    
    # Merge with starting_df to get 'total' and 'counter' information
    # First, prepare a mapping from (src_cid, dst_cid) to 'total' and other columns
    # We'll prioritize starting_df's 'total'; if not present, use desired_df's 'total'
    
    # Create a helper DataFrame with 'total' from starting_df
    starting_totals = starting_df[(starting_df['src_svc'] == 'sslateingress') & (starting_df['dst_svc'] == 'frontend')][
        ['src_cid', 'dst_cid', 'total']
    ].drop_duplicates()
    
    # Similarly, from desired_df
    desired_totals = desired_df[(desired_df['src_svc'] == 'sslateingress') & (desired_df['dst_svc'] == 'frontend')][
        ['src_cid', 'dst_cid', 'total']
    ].drop_duplicates()
    
    # Merge combined_df with starting_totals
    combined_df = combined_df.merge(
        starting_totals,
        on=['src_cid', 'dst_cid'],
        how='left',
        suffixes=('', '_start')
    )
    
    # For rows where 'total' is NaN, fill from desired_totals
    combined_df = combined_df.merge(
        desired_totals,
        on=['src_cid', 'dst_cid'],
        how='left',
        suffixes=('', '_desired')
    )
    
    # Fill 'total' from starting_df; if missing, use desired_df's 'total'; else set to 1 to avoid division by zero
    combined_df['total'] = combined_df['total'].fillna(combined_df['total_desired']).fillna(1)
    
    # Compute 'flow' as weight * total
    combined_df['flow'] = combined_df['weight'] * combined_df['total']
    
    # Add 'src_svc' and 'dst_svc' columns
    combined_df['src_svc'] = 'sslateingress'
    combined_df['dst_svc'] = 'frontend'
    
    # Assuming endpoints are in the format: {svc}@POST@/cart/checkout
    combined_df['src_endpoint'] = combined_df['src_svc'] + '@POST@/cart/checkout'
    combined_df['dst_endpoint'] = combined_df['dst_svc'] + '@POST@/cart/checkout'
    
    # Reorder and select columns to match the original format
    final_df = combined_df[
        ['src_svc', 'dst_svc', 'src_endpoint', 'dst_endpoint',
         'src_cid', 'dst_cid', 'flow', 'total', 'weight']
    ]
    final_df = final_df.sort_values(by=['src_cid', 'dst_cid']).reset_index(drop=True)
    
    return final_df

# Example Usage:

# Sample starting DataFrame
starting_data = {
    'src_svc': ['sslateingress'] * 4,
    'dst_svc': ['frontend'] * 4,
    'src_endpoint': ['sslateingress@POST@/cart/checkout'] * 4,
    'dst_endpoint': ['frontend@POST@/cart/checkout'] * 4,
    'src_cid': ['us-central-1', 'us-central-1', 'us-east-1', 'us-west-1'],
    'dst_cid': ['us-central-1', 'us-west-1', 'us-east-1', 'us-west-1'],
    'flow': [293, 120, 313, 106],
    'total': [510, 510, 372, 106],
    'weight': [0.0, 0.530296, 0.841398, 1.0]
}

# Sample desired DataFrame
desired_data = {
    'src_svc': ['sslateingress'] * 4,
    'dst_svc': ['frontend'] * 4,
    'src_endpoint': ['sslateingress@POST@/cart/checkout'] * 4,
    'dst_endpoint': ['frontend@POST@/cart/checkout'] * 4,
    'src_cid': ['us-central-1', 'us-south-1', 'us-east-1', 'us-south-1'],
    'dst_cid': ['us-central-1', 'us-south-1', 'us-south-1', 'us-south-1'],
    'flow': [150, 95, 60, 80],
    'total': [500, 100, 350, 80],
    'weight': [0.3, 1.0, 0.171428, 1.0]
}

starting_df = pd.DataFrame(starting_data)
desired_df = pd.DataFrame(desired_data)
print("Starting DataFrame:")
print(starting_df)
print("\nDesired DataFrame:")
print(desired_df)

# Compute convex combination with cur_convex_comb_value = 0.5
jumping_df = jump_towards_optimizer_desired(starting_df, desired_df, 0.5)

print("Jumping DataFrame (Convex Combination):")
print(jumping_df)