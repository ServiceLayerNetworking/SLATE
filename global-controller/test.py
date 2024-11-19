import pandas as pd
import numpy as np
from math import sqrt
from scipy.stats import t

import logging
temp_counter=69
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def overperformances_are_different(op1: dict, op2: dict, maxPctDiff=0.5) -> bool:
    """
    overperformances_are_different compares two dictionaries of overperformances (source region -> destination region -> overperformance)
    and checks if any given
      overperformance is different by more than maxPctDiff percent. If so, it returns True.
    """
    for src_region in op1:
        if src_region not in op2:
            return True
        for dst_region in op1[src_region]:
            if dst_region not in op2[src_region]:
                return True
            op1_value = op1[src_region][dst_region]
            op2_value = op2[src_region][dst_region]
            print(f"{src_region} -> {dst_region}: {abs(abs(op1_value - op2_value) / max(abs(op1_value), abs(op2_value)))}")
            if abs(abs(op1_value - op2_value) / min(abs(op1_value), abs(op2_value))) > maxPctDiff:
                return True
    
    for src_region in op2:
        if src_region not in op1:
            return True
        for dst_region in op2[src_region]:
            if dst_region not in op1[src_region]:
                return True
    return False
    
    return False
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

# starting_df = pd.DataFrame(starting_data)
# desired_df = pd.DataFrame(desired_data)
# print("Starting DataFrame:")
# print(starting_df)
# print("\nDesired DataFrame:")
# print(desired_df)

# # Compute convex combination with cur_convex_comb_value = 0.5
# jumping_df = jump_towards_optimizer_desired(starting_df, desired_df, 0.5)

# print("Jumping DataFrame (Convex Combination):")
# print(jumping_df)


def latency_improved(prev_latency: tuple[float, int, float],
                     cur_latency: tuple[float, int, float],
                     threshold_ms: float = 5.0,
                     alpha: float = 0.05) -> bool:
    """
    Determines if the current latency has improved over the previous latency by at least
    a specified threshold using a one-tailed Welch's t-test.

    :param prev_latency: Tuple containing (average_latency, num_reqs, stddev) for previous latency.
    :param cur_latency: Tuple containing (average_latency, num_reqs, stddev) for current latency.
    :param threshold_ms: Minimum improvement in milliseconds to consider latency as improved.
    :param alpha: Significance level for the hypothesis test.
    :return: True if latency has improved by at least threshold_ms with statistical significance, else False.
    """
    # Validate input
    if prev_latency is None or cur_latency is None:
        logger.warning("Previous or current latency data is None.")
        return False
    
    try:
        prev_avg, prev_n, prev_stddev = prev_latency
        cur_avg, cur_n, cur_stddev = cur_latency
    except ValueError as e:
        logger.error(f"Invalid latency tuple format: {e}")
        return False
    
    # Ensure there are enough samples to perform the test
    if prev_n < 2 or cur_n < 2:
        logger.warning("Not enough data points to perform t-test. At least 2 requests are required for each latency measurement.")
        return False
    
    # Compute the difference in means
    # Since we're testing if current latency is better (lower) by at least threshold_ms,
    # the hypothesis is mu_1 - mu_2 > threshold_ms
    delta = (prev_avg - cur_avg) - threshold_ms  # Positive delta indicates improvement beyond threshold
    
    # Compute the standard error (SE) of the difference
    SE = sqrt((prev_stddev ** 2) / prev_n + (cur_stddev ** 2) / cur_n)
    
    if SE == 0:
        logger.warning("Standard error is zero. Cannot perform t-test.")
        return False
    
    # Compute the t-statistic
    t_stat = delta / SE
    
    # Compute degrees of freedom using Welch's formula
    numerator = ( (prev_stddev ** 2) / prev_n + (cur_stddev ** 2) / cur_n ) ** 2
    denominator = ( ((prev_stddev ** 2) / prev_n) ** 2 ) / (prev_n - 1) + ( ((cur_stddev ** 2) / cur_n) ** 2 ) / (cur_n - 1)
    
    if denominator == 0:
        logger.warning("Denominator for degrees of freedom is zero. Cannot compute degrees of freedom.")
        return False
    
    df = numerator / denominator
    
    # Compute the one-tailed p-value
    p_value = 1 - t.cdf(t_stat, df)
    
    logger.debug(f"T-Statistic: {t_stat}, Degrees of Freedom: {df}, P-Value: {p_value}")
    
    # Decision rule
    if p_value < alpha and delta > 0:
        logger.info(f"Latency improved by at least {threshold_ms}ms with p-value {p_value:.4f}.")
        return True
    else:
        logger.info(f"No significant latency improvement by at least {threshold_ms}ms (p-value: {p_value:.4f}).")
        return False
    

def latency_worsened(prev_latency: tuple[float, int, float],
                     cur_latency: tuple[float, int, float],
                     threshold_ms: float = 5.0,
                     alpha: float = 0.05) -> bool:
    """
    Determines if the current latency has worsened over the previous latency by at least
    a specified threshold using a one-tailed Welch's t-test.

    :param prev_latency: Tuple containing (average_latency, num_reqs, stddev) for previous latency.
    :param cur_latency: Tuple containing (average_latency, num_reqs, stddev) for current latency.
    :param threshold_ms: Minimum worsening in milliseconds to consider latency as worsened.
    :param alpha: Significance level for the hypothesis test.
    :return: True if latency has worsened by at least threshold_ms with statistical significance, else False.
    """
    # Validate input
    if prev_latency is None or cur_latency is None:
        logger.warning("Previous or current latency data is None.")
        return False
    
    try:
        prev_avg, prev_n, prev_stddev = prev_latency
        cur_avg, cur_n, cur_stddev = cur_latency
    except ValueError as e:
        logger.error(f"Invalid latency tuple format: {e}")
        return False
    
    # Ensure there are enough samples to perform the test
    if prev_n < 2 or cur_n < 2:
        logger.warning("Not enough data points to perform t-test. At least 2 requests are required for each latency measurement.")
        return False
    
    # Compute the difference in means
    # Since we're testing if current latency is worse (higher) by at least threshold_ms,
    # the hypothesis is mu_2 - mu_1 > threshold_ms
    delta = (cur_avg - prev_avg) - threshold_ms  # Positive delta indicates worsening beyond threshold
    
    # Compute the standard error (SE) of the difference
    SE = sqrt((prev_stddev ** 2) / prev_n + (cur_stddev ** 2) / cur_n)
    
    if SE == 0:
        logger.warning("Standard error is zero. Cannot perform t-test.")
        return False
    
    # Compute the t-statistic
    t_stat = delta / SE
    
    # Compute degrees of freedom using Welch's formula
    numerator = ( (prev_stddev ** 2) / prev_n + (cur_stddev ** 2) / cur_n ) ** 2
    denominator = ( ((prev_stddev ** 2) / prev_n) ** 2 ) / (prev_n - 1) + ( ((cur_stddev ** 2) / cur_n) ** 2 ) / (cur_n - 1)
    
    if denominator == 0:
        logger.warning("Denominator for degrees of freedom is zero. Cannot compute degrees of freedom.")
        return False
    
    df = numerator / denominator
    
    # Compute the one-tailed p-value
    p_value = 1 - t.cdf(t_stat, df)
    
    logger.debug(f"T-Statistic: {t_stat}, Degrees of Freedom: {df}, P-Value: {p_value}")
    
    # Decision rule
    if p_value < alpha and delta > 0:
        logger.info(f"Latency worsened by at least {threshold_ms}ms with p-value {p_value:.4f}.")
        return True
    else:
        logger.info(f"No significant latency worsening by at least {threshold_ms}ms (p-value: {p_value:.4f}).")
        return False


prev = (29.109933106146663, 79023, 62.868883964647495)
cur = (27.620539291014882, 76137, 58.95973003283683)
print(f"Latency improved: {latency_improved(prev, cur, threshold_ms=1, alpha=0.05)}")
print(f"Latency worsened: {latency_worsened(prev, cur, threshold_ms=1, alpha=0.05)}")