from flask import Flask, request, abort
import logging
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from threading import Lock
import optimizer_test as opt
import optimizer_header as opt_func
import config as cfg
import span as sp
import statistics
import time_stitching as tst
import pandas as pd
from sklearn.model_selection import train_test_split
import gen_trace
from IPython.display import display
from pprint import pprint
import random
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
import datetime
import os
import collections
import math
import matplotlib.pyplot as plt
import numpy as np
import time
import copy
import warnings
import json

# Filter specific FutureWarning related to pandas concatenation.

# import logging.config

logging.config.dictConfig(cfg.LOGGING_CONFIG)
# logging.basicConfig(level=logging.INFO)
# logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask(__name__)
logger = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)
logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.DEBUG)

warnings.filterwarnings("ignore", message="The behavior of DataFrame concatenation with empty or all-NA entries is deprecated")


'''runtime (optimizer)'''
endpoint_level_inflight = {}
# endpoint_level_rps = {}
aggregated_rps = {} # dict of region -> svcname -> endpoint -> rps
agg_root_node_rps = {}
endpoint_level_rps_mutex = Lock()
per_pod_ep_rps = {}
per_pod_ep_rps_mutex = Lock()
service_level_rps = {}
endpoint_to_cg_key = {}
ep_str_callgraph_table = {}
all_endpoints = {}
temp_counter = 0
prev_ts = time.time()
load_coef_flag = False
init_done = False
use_optimizer_output = False
jumping_towards_optimizer = False

endpoint_sizes = {}

placement = {}
coef_dict = {}
e2e_coef_dict = {}
degree = 0
endpoint_to_placement = dict()
svc_to_placement = dict()
percentage_df = pd.DataFrame()
jumping_df = pd.DataFrame()
prev_jumping_df = pd.DataFrame()
starting_df = pd.DataFrame()
desired_df = pd.DataFrame()
cur_convex_comb_value = 0 # between 0 and 1
convex_comb_step = 0.25
convex_comb_direction = 1 # 1 or -1
jumping_ruleset_num_iterations = 0
jumping_ruleset_convergence_iterations = 10
cur_jumping_ruleset = ""
completed_rulesets = set()
historical_svc_latencies = dict() # svc -> list of latencies
# optimizer_cnt = 0
endpoint_rps_cnt = 0
inter_cluster_latency = dict()
stats_mutex = Lock()
endpoint_rps_history = list()
traffic_segmentation = 1
objective = "avg_latency"
# objective = "multi_objective"
DOLLAR_PER_MS = 1
first_write_flag_for_profiled_trace=True
state = "empty"
# all_clusters = set() # not used for now
workload = dict()

# Target is checkoutcart request type
## checkoutcart + cart, shipping, payment, email

## checkout service only
exclude_svc = {}
# exclude_svc = {"us-central-1": ["paymentservice", 'emailservice', 'shippingservice']}
# exclude_svc = {"us-central-1": ['cartservice']}
# exclude_svc = {"us-central-1": ['checkoutservice']}
# exclude_svc = {"us-central-1": ['checkoutservice'], "us-east-1":['productcatalogservice']}

'''waterfall'''
region_pct_df = dict()

'''waterfall2'''
parent_of_bottleneck_service = ""
# bottleneck_service = "a"
bottleneck_service = ""

'''profiling (training)'''
list_of_span = list() # unorganized list of spanss
complete_traces = dict() # filtered traces
train_done = False
train_start = False
# trace_str_list = list() # internal data structure of traces before writing it to a file
profile_output_file="trace_string.csv" # traces_str_list -> profile_output_file in write_trace_str_to_file() function every 5s
latency_func = {}
trainig_input_trace_file="trace.csv" # NOTE: It should be updated when the app is changed
x_feature = "rps_dict" # "num_inflight_dict"
target_y = "xt"

'''config'''
mode = ""
MODE_SET = ["profile", "runtime", "before_start"]
benchmark_name = ""
# benchmark_set = ["metrics", "matmul-app", "hotelreservation", "spread-unavail-30bg"]
total_num_services = 0
ROUTING_RULE = "LOCAL" # It will be updated by read_config_file function.
ROUTING_RULE_SET = ["LOCAL", "SLATE", "SLATE-with-jumping-local","SLATE-with-jumping-global", "SLATE-without-jumping", "REMOTE", "MCLB", "WATERFALL", "WATERFALL2"]
CAPACITY = 0 # If it is runtime -> training_phase() -> max_capacity_per_service() -> set max_capacity_per_service[svc] = CAPACITY
max_capacity_per_service = dict() # max_capacity_per_service[svc][region] = CAPACITY
hillclimbing_distribution_history = list() #list(dict())
global_hillclimbing_distribution_history = list() #list(dict())
hillclimb_latency_lock = Lock()
prev_hillclimb_latency = dict() # svc -> region -> pod -> {latency_total, num_reqs}
cur_hillclimb_latency = dict()
next_hillclimb_latency = dict()
global_prev_ruleset_overperformance = dict()
currently_globally_oscillating = False
jumping_feature_enabled = False
hillclimb_interval = -1
hillclimb_enabled = "Unknown"
hillclimb_stepsize = -1
first_replica_sync_s = -1
first_replica_mutex = Lock()
first_replica_sync_counter = 1000 # arbitrary number
last_policy_request = dict() # svc -> time.time()
last_policy_request_mutex = Lock()
cur_hillclimbing = dict() # svc -> endpoint

jumping_last_seen_opt_output = pd.DataFrame() # the last seen routing rules from the jumping perspective


global_processing_latencies = dict() # svc -> region -> pod -> method@path -> {latency_avg, num_reqs}
global_prev_processing_latencies = dict()
processing_latencies_mutex = Lock()


@app.post('/hillclimbingLatency') # from wasm
def handleHillclimbLatency():
    global next_hillclimb_latency
    global hillclimb_latency_lock
    global cur_hillclimbing
    global global_processing_latencies
    global processing_latencies_mutex
    svc = request.headers.get('x-slate-servicename').split("-us-")[0]    
    region = request.headers.get('x-slate-region')
    podname = request.headers.get('x-slate-podname')[-5:]

    body = request.get_data().decode('utf-8')
    # logger.info(f"hillclimbingLatency for (svc {svc}, pod {podname}, region {region}): body:\n{body}")
    processing_latencies_mutex.acquire(blocking=True)
    if svc not in global_processing_latencies:
        global_processing_latencies[svc] = dict()
    if region not in global_processing_latencies[svc]:
        global_processing_latencies[svc][region] = dict()
    if podname not in global_processing_latencies[svc][region]:
        global_processing_latencies[svc][region][podname] = dict()

    lines = body.split("\n")
    parsingOutbound = False
    for line in lines:
        if not line:
            continue
        if line == "outbound":
            parsingOutbound = True
            continue
        if parsingOutbound:
            if line == "inbound":
                parsingOutbound = False
                continue
            parts = line.split(" ")
            if len(parts) != 5:
                # logger.info(f"hillclimbingLatency for (pod {podname}, svc {svc}): len(parts) != 5, skipping")
                continue
            for i in range(len(parts)):
                parts[i] = parts[i].strip()
            dstSvc, method, path, avgLatency, numReqs = parts[0], parts[1], parts[2], parts[3], parts[4]
            # todo parse these into a separate structure (probably for observability)
        else:
            parts = line.split(" ")
            if len(parts) != 4:
                # logger.info(f"hillclimbingLatency for (pod {podname}, svc {svc}): len(parts) != 4 for inbound, skipping")
                continue
            for i in range(len(parts)):
                parts[i] = parts[i].strip()
            method, path, avgLatency, numReqs = parts[0], parts[1], parts[2], parts[3]
            mp = f"{method}@{path}"
            if mp not in global_processing_latencies[svc][region][podname]:
                global_processing_latencies[svc][region][podname][mp] = {
                    "latency_total": float(avgLatency) * int(numReqs),
                    "num_reqs": int(numReqs)
                }
            else:
                global_processing_latencies[svc][region][podname][mp]["latency_total"] += float(avgLatency) * int(numReqs)
                global_processing_latencies[svc][region][podname][mp]["num_reqs"] += int(numReqs)
    processing_latencies_mutex.release()
    return ""


def perform_jumping():
    global percentage_df
    global jumping_df
    global prev_jumping_df
    global jumping_feature_enabled
    global jumping_last_seen_opt_output
    global starting_df
    global desired_df
    global cur_convex_comb_value
    global convex_comb_step
    global convex_comb_direction
    global use_optimizer_output
    global cur_jumping_ruleset
    global completed_rulesets
    global global_prev_ruleset_overperformance
    global currently_globally_oscillating
    
    global jumping_towards_optimizer
    global jumping_ruleset_num_iterations
    global jumping_ruleset_convergence_iterations
    global global_prev_processing_latencies
    global global_processing_latencies
    global processing_latencies_mutex
    global temp_counter
    """
    if use_optimizer_output is true, /proxyLoad will use percentage_df to route traffic.
    otherwise, it will use jumping_df.

    if jumping_last_seen_opt_output is a lot different from the current percentage_df, we need to fall back
        to the routing rules the optimizer suggested. set use_optimizer_output to True.
    otherwise, continue with the jumping we are doing. partition rulesets into underperformers and overperformers, and perform
        jumping in the disjoint rulesets.

    if jumping_last_seen_opt_output is a lot different from the current percentage_df, we need to start jumping towards the optimizer output.
        here, we don't pick rulesets, we just jump by some step towards the optimizer output as long as latency keeps improving. this is called defensive jumping.
        once the latency stops improving (oscillation), we start jumping in the disjoint rulesets (offensive jumping).
    otherwise, continue with the jumping we are doing. partition rulesets into underperformers and overperformers, and perform
        jumping in the disjoint rulesets.
    """

    # snapshot the current optimizer output and processing latencies
    cur_last_seen_opt_output = jumping_last_seen_opt_output.copy()
    jumping_last_seen_opt_output = percentage_df.copy()
    processing_latencies_mutex.acquire(blocking=True)
    cur_processing_latencies = global_processing_latencies.copy()
    prev_processing_latencies = global_prev_processing_latencies.copy()
    # make the prev processing latencies the current latencies and clear the current latencies
    global_prev_processing_latencies = global_processing_latencies.copy()
    global_processing_latencies.clear()
    processing_latencies_mutex.release()
    prev_processing_latency = calculate_avg_processing_latency(prev_processing_latencies, "sslateingress", "POST@/cart/checkout")
    cur_processing_latency = calculate_avg_processing_latency(cur_processing_latencies, "sslateingress", "POST@/cart/checkout")
    write_latency("sslateingress", cur_processing_latency, cur_processing_latencies)
    if not jumping_feature_enabled:
        return

    if len(cur_last_seen_opt_output) == 0:
        # we haven't seen the optimizer output yet just return
        return
    jumping_ruleset_num_iterations += 1
    logger.info(f"loghill temp_counter {temp_counter} (current ruleset {cur_jumping_ruleset} prev_processing_latency: {prev_processing_latency}, cur_processing_latency: {cur_processing_latency}")

    ruleset_overperformance = calculate_ruleset_overperformance(jumping_df.copy(), cur_processing_latencies)
    prev_ruleset_overperformance = global_prev_ruleset_overperformance.copy()
    global_prev_ruleset_overperformance = ruleset_overperformance.copy()
    logger.info(f"loghill ruleset_overperformance: {ruleset_overperformance}")


    if rules_are_different(cur_last_seen_opt_output, percentage_df, maxThreshold=0.1) and len(percentage_df) > 0:
        logger.info(f"loghill rules are different, stepping towards optimizer output, old rules:\n{compute_traffic_matrix(cur_last_seen_opt_output)}, new rules:\n{compute_traffic_matrix(percentage_df)}, cur jumping_df:\n{compute_traffic_matrix(jumping_df)}")
        # here, we want to start defensive jumping towards the optimizer output.
        # we want to jump from jumping_df (which is the current state) to percentage_df (which is the optimizer output).
        # use_optimizer_output = True
        jumping_towards_optimizer = True
        jumping_ruleset_num_iterations = 0
        currently_globally_oscillating = False
        # make jumping_df the same as percentage_df, because /proxyLoad will use percentage_df, so the latencies
        # in processing_latencies will be based on the percentage_df.
        # jumping_df = percentage_df.copy()
        if len(jumping_df) == 0:
            jumping_df = percentage_df.copy()
            # this means that the rules are different from what we last saw, but we haven't started jumping yet / don't have a state, so we can just return.
            return
        starting_df = jumping_df.copy()
        desired_df = percentage_df.copy()
        cur_convex_comb_value = 0
        convex_comb_direction = 1
        # clear the prev processing latencies, because we will be making a measurement based on the current rules, compared to the proposed (step) rules.
        global_prev_processing_latencies.clear()
        return
    
    if overperformances_are_different(prev_ruleset_overperformance, ruleset_overperformance, maxPctDiff=.4) and not jumping_towards_optimizer:
        # we are oscillating, but the overperformances are different, so we should restart jumping in the disjoint rulesets.
        currently_globally_oscillating = False
        jumping_towards_optimizer = False
        completed_rulesets.clear()
        cur_jumping_ruleset = pick_best_ruleset(ruleset_overperformance, completed_rulesets)
        logger.info(f"loghill detected overperformance change, picked new ruleset: {cur_jumping_ruleset}")
        jumping_ruleset_num_iterations = 0
        global_prev_processing_latencies.clear()

    if currently_globally_oscillating:
        # we are oscillating and the overperformances are the same, so we should stop jumping.
        logger.info(f"currently globally oscillating, exiting jumping iteration")
        return
    
    if latency_is_oscillating("sslateingress", 5, thresh_ms=3) and jumping_ruleset_num_iterations > jumping_ruleset_convergence_iterations:
        # change the ruleset or whether or not we jump towards the optimizer
        logger.info(f"loghill oscillation detected")
        if jumping_towards_optimizer:
            # we were jumping towards the optimizer, but we started oscillating, so we switch to offensive jumping.
            logger.info(f"loghill oscillation detected, switching to offensive jumping")
            jumping_towards_optimizer = False
            completed_rulesets.clear()
        else:
            # add the current ruleset to the completed rulesets (this one has converged).
            logger.info(f"loghill oscillation detected, adding ruleset {cur_jumping_ruleset} to completed rulesets")
            completed_rulesets.add(cur_jumping_ruleset)
        jumping_ruleset_num_iterations = 0
        cur_jumping_ruleset = pick_best_ruleset(ruleset_overperformance, completed_rulesets)
        logger.info(f"loghill picked new ruleset: {cur_jumping_ruleset}")
        if cur_jumping_ruleset == "": # no more rulesets to jump to
            currently_globally_oscillating = True
            logger.info(f"loghill no more rulesets to jump to, starting oscillation detection (currently_globally_oscillating=True)")
            return

    if jumping_towards_optimizer:
        # we perform the first jumping iteration here (this means there will be some delay between detecting rule changes and starting to jump)

        # compute the convex combination of the starting_df and desired_df for traffic matrix of regions between services sslateingress and frontend
        # the convex combination is based on cur_convex_comb_value, which is between 0 and 1.
        # current = (1 - t) * starting + t * desired
        # as long as latency gets better, increase t by convex_comb_step, otherwise decrease t by convex_comb_step.
        # if we start oscillating, we stop jumping towards the optimizer output and start jumping in the disjoint rulesets.
        # if we reach t = 1, we stop jumping towards the optimizer output and start jumping in the disjoint rulesets.
        
        # this means we took a that resulted in a worse latency, so we reverse direction.

        if cur_convex_comb_value == 1:
            # we have reached the optimizer output, stop jumping towards the optimizer output.
            logger.info(f"loghill reached optimizer output, switching to offensive jumping")
            jumping_towards_optimizer = False
            completed_rulesets.clear()
            cur_jumping_ruleset = pick_best_ruleset(ruleset_overperformance, completed_rulesets)
            logger.info(f"loghill picked new ruleset: {cur_jumping_ruleset}")
            prev_processing_latencies.clear()
            prev_jumping_df = jumping_df.copy()
            return
        if len(prev_processing_latencies) > 0 and prev_processing_latency < cur_processing_latency: # gangmuk: statistical model
            # reverse direction
            logger.info(f"loghill reversing direction from {convex_comb_direction} to {-convex_comb_direction}")
            convex_comb_direction = -convex_comb_direction
        logger.info(f"loghill old cur_convex_comb_value: {cur_convex_comb_value}")
        proposed = cur_convex_comb_value + convex_comb_direction * convex_comb_step
        if proposed < 0:
            proposed = 0
            convex_comb_direction = 1
        elif proposed > 1:
            proposed = 1
            convex_comb_direction = -1
        cur_convex_comb_value = proposed
        logger.info(f"loghill new cur_convex_comb_value: {cur_convex_comb_value}")
        if len(starting_df) == 0:
            starting_df = percentage_df.copy()
        jumping_df = jump_towards_optimizer_desired(starting_df, desired_df, cur_convex_comb_value).copy()
    else:
        # partition the rulesets into underperformers and overperformers
        # assumes routing rules exist only in the first layer (between sslateingress and frontend).
        """
        for each ruleset, direction is represented as two sets of regions, one for underperformers and one for overperformers.

        we measure the last latency and compare it with the current latency to verify we are moving in the right direction.
        - we have an expected direction (based on the over/underperformers with the current latency).
        - we stop moving in a direction for 2 reasons:
            1) we have started oscillating (latency-wise) with the current direction.
            2) we compute a new direction based on the current latency. in this case <what do we do?>, we can make that the current direction.
            - could the computed direction also oscillate?

        1) for each rule with source sslateingress and destination frontend, with more than 1 region in that set of rules, create a ruleset.
        2) for each ruleset, for each destination frontend service (across clusters), calculate the overperformance of each region.
            a) partition the regions into underperformers and overperformers, based on the average latency (in cur_processing_latencies)

        compare new computed direction with old direction, compare new latency with old latency.
        ideally, the direction will always be the same, and we just have to check latency...
        """

        if cur_jumping_ruleset == "":
            cur_jumping_ruleset = pick_best_ruleset(ruleset_overperformance, completed_rulesets)
            logger.info(f"loghill picked new ruleset: {cur_jumping_ruleset}")
        # first adjust jumping_df based on the current and previous latencies (accept the rule from prev_jumping_df to jumping_df)
        # if the latency has improved. if not, roll back to prev_jumping_df. this is where we detect oscillation.
        # todo aditya
        if len(prev_processing_latencies) > 0 and prev_processing_latency < cur_processing_latency: # gangmuk: statistical model
            # cases where prev_processing_latency < cur_processing_latency:
            # 1) we are oscillating between two rules -- this is fine. in this case, we just roll back and keep oscillating.
            # 2) we are somehow getting worse with each rule. in this case, rollback becomes a no-op (what are we rolling back to?).
            #    in this case, we probably want to clear the prev_processing_latencies and start over.
            if len(prev_jumping_df) == 0:
                logger.info(f"loghill no previous rule to roll back to, clearing prev_processing_latencies and starting over.")
                # to rule to rollback to, clear the prev_processing_latencies and start over.
                global_prev_processing_latencies.clear()
                return
            else:
                logger.info(f"loghill rolling back to prev_jumping_df")
                jumping_df = prev_jumping_df.copy()
        elif len(jumping_df) > 0:
            # the new rule is better than the previous rule, so we accept the new rule.
            # we now recompute the direction based on latencies
            # prev_jumping_df was the rule we used to route traffic in the previous iteration.
            prev_jumping_df = jumping_df.copy()
            # this is the new calculated direction / weights for that direction.
            # apply this overperformance to jumping_df, and then apply the jumping_df to the actual routing rules.
            adjusted_df, did_adjust = adjust_ruleset(prev_jumping_df, cur_jumping_ruleset, ruleset_overperformance.get(cur_jumping_ruleset, {}), step_size=0.1)
            jumping_df = adjusted_df.copy()
            if not did_adjust:
                # add this to completed rulesets
                logger.info(f"loghill ruleset did not adjust, adding ruleset {cur_jumping_ruleset} to completed rulesets")
                completed_rulesets.add(cur_jumping_ruleset)
        else:
            jumping_df = percentage_df.copy()
    return


def rules_are_different(df1: pd.DataFrame, df2: pd.DataFrame, maxThreshold=0.1):
    """
    We compare the two dataframes based on the weight column. If, for the same src_svc, dst_svc, src_endpoint, dst_endpoint, src_cid, dst_cid, 
    the weight is different by more than maxThreshold, we return True. 
    If the rule does not exist in one of the dataframes or columns are missing, we return True.
    """

    required_columns = ["src_svc", "dst_svc", "src_endpoint", "dst_endpoint", "src_cid", "dst_cid", "weight"]

    # Check if all required columns exist in both dataframes
    for col in required_columns:
        if col not in df1.columns or col not in df2.columns:
            return False

    # Set index to compare based on specified columns
    df1 = df1.set_index(["src_svc", "dst_svc", "src_endpoint", "dst_endpoint", "src_cid", "dst_cid"])
    df2 = df2.set_index(["src_svc", "dst_svc", "src_endpoint", "dst_endpoint", "src_cid", "dst_cid"])

    # Check rules in df1
    for idx in df1.index:
        if idx in df2.index and abs(df1.loc[idx]["weight"] - df2.loc[idx]["weight"]) > maxThreshold:
            return True

    # # Check rules in df2
    # for idx in df2.index:
    #     if idx not in df1.index:
    #         return True

    return False

def processing_latencies_are_different(pl1: dict, pl2: dict, maxPctDiff=0.5) -> bool:
    pass

def overperformances_are_different(op1: dict, op2: dict, maxPctDiff=0.5) -> bool:
    """
    overperformances_are_different compares two dictionaries of overperformances (source region -> destination region -> overperformance)
    and checks if any given overperformance is different by more than maxPctDiff percent. If so, it returns True.
    """
    for src_region in op1:
        if src_region not in op2:
            return True
        for dst_region in op1[src_region]:
            if dst_region not in op2[src_region]:
                return True
            op1_value = op1[src_region][dst_region]
            op2_value = op2[src_region][dst_region]
            if abs(abs(op1_value - op2_value) / min(abs(op1_value), abs(op2_value))) > maxPctDiff:
                return True
    
    for src_region in op2:
        if src_region not in op1:
            return True
        for dst_region in op2[src_region]:
            if dst_region not in op1[src_region]:
                return True
    return False

# Function to compute traffic matrix from DataFrame
def compute_traffic_matrix(df):
    if 'src_svc' not in df.columns or 'dst_svc' not in df.columns:
        return pd.DataFrame()
    filtered = df[(df['src_svc'] == 'sslateingress') & (df['dst_svc'] == 'frontend')]
    traffic_matrix = filtered.pivot_table(
        index='src_cid',
        columns='dst_cid',
        values='weight',
        aggfunc='sum',
        fill_value=0
    )
    return traffic_matrix

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
            raise ValueError(f"{df_name} must contain columns: {required_columns} (has columns: {df.columns})")

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
    logger.info(f"loghill (defensive jumping) new traffic matrix:\n{combined_matrix}\nstarting_matrix:\n{starting_matrix}\ndesired_matrix:\n{desired_matrix}")
    
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
    

def latency_is_oscillating(svc: str, last_iters: int, thresh_ms=6) -> bool:
    global historical_svc_latencies
    """
    latency_is_oscillating will read the last last_iters latencies for a given service and determine if the latencies are oscillating.
    oscillating means the latencies tend to increase & decrease in a cycle, and that the difference between the the max and min is less than thresh_ms.
    """
    if svc not in historical_svc_latencies:
        return False
    if len(historical_svc_latencies[svc]) < last_iters:
        return False
    last_latencies = historical_svc_latencies[svc][-last_iters:]
    max_latency = max(last_latencies)
    min_latency = min(last_latencies)
    # todo check for cycles in the latencies
    return max_latency - min_latency < thresh_ms

def pick_best_ruleset(overperformance: dict, exclude_rulesets: set) -> str:
    """
    pick_best_ruleset will pick the best ruleset based on the max variance in overperformance of each ruleset.
    It will return the best ruleset which is not in the exclude_rulesets set.
    It expects overperformance to be a dictionary of source region -> destination region -> overperformance.
    returns an empty string if no ruleset is found.
    """
    best_ruleset = ""
    max_variance = float('-inf')

    for source_region, destinations in overperformance.items():
        if source_region in exclude_rulesets:
            continue

        # Get the overperformance values for the current source region
        overperformance_values = list(destinations.values())

        # Calculate variance if there are enough values
        if len(overperformance_values) > 1:
            variance = statistics.variance(overperformance_values)
        else:
            variance = 0  # If there's only one value, variance is 0

        # Update the best ruleset if the current variance is higher than the maximum found so far
        if variance > max_variance:
            max_variance = variance
            best_ruleset = source_region

    return best_ruleset

def calculate_avg_processing_latency(latencies: dict, svc: str, methodpath: str, region="") -> dict:
    """
    calculate_avg_processing_latency will calculate the average processing latency (across all pods and regions for a given method@path) for a given service.
    returns an int.
    """
    total_latency, total_reqs = 0, 0
    if svc not in latencies:
        return 0
    if region and region not in latencies[svc]:
        return 0
    
    if region:
        for pod in latencies[svc][region]:
            if methodpath not in latencies[svc][region][pod]:
                continue
            total_latency += latencies[svc][region][pod][methodpath]["latency_total"]
            total_reqs += latencies[svc][region][pod][methodpath]["num_reqs"]
    else:
        for region in latencies[svc]:
            for pod in latencies[svc][region]:
                if methodpath not in latencies[svc][region][pod]:
                    continue
                total_latency += latencies[svc][region][pod][methodpath]["latency_total"]
                total_reqs += latencies[svc][region][pod][methodpath]["num_reqs"]
    return total_latency / total_reqs if total_reqs > 0 else 0

def calculate_ruleset_overperformance(rules: pd.DataFrame, cur_latencies: dict) -> dict:
    """
    calculate_ruleset_overperformance will calculate the overperformance of all rulesets based on the current vs expected latencies.
    the only rulesets considered are between sslateingress and frontend.
    ruleset is defined as every set of rules originating from a source region to more than one destination region.
    it calculates overperfomance as (expected latency - actual latency) * requests affected.

    it returns a dictionary of destination region to overperformance. (source region -> destination region -> overperformance)
    example:
    {
        "us-west-1": {
            "us-west-1": 37,
            "us-east-1": 12,
            "us-central-1": 0,
            "us-south-1": -59   
        }
    }
    It needs access to the processing latencies, the current load conditions, and the processing latency function for frontend.
    """
    global aggregated_rps
    # first filter src_svc being sslateingress and dst_svc being frontend
    # then, for each of these entries, get the source regions that have more than one destination region
    # for each of these source regions, calculate the overperformance of the ruleset.
    # return the overperformance as a dictionary of destination region to overperformance.

    # todo aditya problem: latency is not being injected right...
    logger.info(f"calculate_ruleset_overperformance: rules:\n{rules.columns}")
    if "src_svc" not in rules.columns or "dst_svc" not in rules.columns or "src_cid" not in rules.columns or "dst_cid" not in rules.columns:
        return dict()
    filtered_rules = rules[(rules["src_svc"] == "sslateingress") & (rules["dst_svc"] == "frontend")]
    src_regions = filtered_rules["src_cid"].unique()
    logger.info(f"calculate_ruleset_overperformance: src_regions: {src_regions}")
    overperformance = dict()
    for src_region in src_regions:
        src_rules = filtered_rules[filtered_rules["src_cid"] == src_region]
        dst_regions = src_rules["dst_cid"].unique()
        if len(dst_regions) < 2:
            continue
        else:
            logger.info(f"calculate_ruleset_overperformance: src_region: {src_region}, dst_regions: {dst_regions}")
        overperformance[src_region] = dict()
        for dst_region in dst_regions:
            # calculate the overperformance for this rule
            # get the expected latency based on the current load conditions
            # get the actual latency from cur_latencies
            # calculate the overperformance as (expected - actual) * requests
            # requests is the total requests for a certain traffic class at a service in a region.
            actual_latency_in_dst_region = calculate_avg_processing_latency(cur_latencies, "frontend", "POST@/cart/checkout", region=dst_region)
            total_load_in_dst_region = aggregated_rps.get(dst_region, {}).get("frontend", {}).get("frontend@POST@/cart/checkout", 0)
            expected_latency_in_dst_region = get_expected_latency_for_rule(total_load_in_dst_region, "frontend", "POST@/cart/checkout")
            total_load_in_src_region = aggregated_rps.get(src_region, {}).get("frontend", {}).get("frontend@POST@/cart/checkout", 0)
            ruleset_rps_in_dst_region = total_load_in_src_region * src_rules[src_rules["dst_cid"] == dst_region]["weight"].values[0]
            overperformance[src_region][dst_region] = (expected_latency_in_dst_region - actual_latency_in_dst_region) * ruleset_rps_in_dst_region

            # actual_latency = calculate_avg_processing_latency(cur_latencies, "frontend", "POST@/cart/checkout", region=dst_region)
            # load = aggregated_rps.get(src_region, {}).get("frontend", {}).get("frontend@POST@/cart/checkout", 0)
            # load_in_dst_region = aggregated_rps.get(dst_region, {}).get("frontend", {}).get("frontend@POST@/cart/checkout", 0)
            # expected_latency = get_expected_latency_for_rule(load_in_dst_region, "frontend", "POST@/cart/checkout")
            logger.info(f"loghill calculate_ruleset_overperformance: src_region: {src_region}, dst_region: {dst_region}, expected_latency: {expected_latency_in_dst_region}, actual_latency: {actual_latency_in_dst_region}, load in {dst_region} for this ruleset: {ruleset_rps_in_dst_region}")
            # overperformance[src_region][dst_region] = (expected_latency - actual_latency) * load
    return overperformance


def adjust_ruleset(ruleset: pd.DataFrame, region: str, overperformance: dict, step_size=0.05) -> tuple[pd.DataFrame, bool]:
    """
    adjust_ruleset will adjust the (source region) ruleset based on the overperformance of the ruleset.
    overperformance is expected to be in the form of a dictionary of destination region to overperformance.
    it will find the average performance in the source region, partition the destination regions into underperformers and overperformers,
    and adjust the ruleset accordingly. second parameter is a boolean indicating if the ruleset was adjusted.
    """
    # first, get the average performance of the ruleset in the source region
    # then, partition the destination regions into underperformers and overperformers
    # adjust the ruleset based on the overperformance of the ruleset.
    # return the adjusted ruleset.
    if len(overperformance) == 0:
        logger.info(f"loghill no overperformance for ruleset [{region}]")
        return ruleset, False
    
    # get the destination regions, and the average performance of the ruleset (for those destination regions)
    src_svc, dst_svc, src_endpoint, dst_endpoint = "sslateingress", "frontend", "sslateingress@POST@/cart/checkout", "frontend@POST@/cart/checkout"
    dst_cids = list(overperformance.keys())
    avg_performance = sum([overperformance[dst_cid] for dst_cid in dst_cids]) / len(dst_cids)
    # partition the destination regions into underperformers and overperformers
    underperformers = [dst_cid for dst_cid in dst_cids if overperformance[dst_cid] < avg_performance]
    overperformers = [dst_cid for dst_cid in dst_cids if overperformance[dst_cid] >= avg_performance]
    logger.info(f"loghill for ruleset [{region}] underperformers: {underperformers}, overperformers: {overperformers}")

    # proportionally adjust underperformers and overperformers.
    # calculate the weight each underperformer/overperformer has wieh their respective set, and
    # add/subtract that weight * step_size to the weight of the rule.
    # todo do we need to normalize the weights? (weight based on distance from average performance)
    # also todo, we need to make sure the weights don't go below 0 or above 1 (globally) and that the weights always sum to 1.
    adjusted_ruleset = ruleset.copy()
    out_of_bounds = False
    for dst_cid in underperformers:
        total_underperformance = sum([overperformance[dst_cid] for dst_cid in underperformers])
        logger.info(f"loghill underperformer: {dst_cid}, total_underperformance: {total_underperformance}")
        weight = overperformance[dst_cid] / total_underperformance if total_underperformance != 0 else 0
        # make sure we dont go below 0
        mask = (
            (adjusted_ruleset["src_cid"] == region) &
            (adjusted_ruleset["dst_cid"] == dst_cid) &
            (adjusted_ruleset["src_svc"] == src_svc) &
            (adjusted_ruleset["dst_svc"] == dst_svc) &
            (adjusted_ruleset["src_endpoint"] == src_endpoint) &
            (adjusted_ruleset["dst_endpoint"] == dst_endpoint)
        )
        cur_weight = adjusted_ruleset.loc[mask, "weight"].values[0]
        step = weight * step_size
        if cur_weight - step < 0:
            out_of_bounds = True
        else:
            logger.info(f"loghill underperformer: {dst_cid}, cur_weight: {cur_weight}, step: {step}")
            adjusted_ruleset.loc[(adjusted_ruleset["src_cid"] == region) & (adjusted_ruleset["dst_cid"] == dst_cid) 
                             & (adjusted_ruleset["src_svc"] == src_svc) & (adjusted_ruleset["dst_svc"] == dst_svc) 
                             & (adjusted_ruleset["src_endpoint"] == src_endpoint) & (adjusted_ruleset["dst_endpoint"] == dst_endpoint), "weight"] -= weight * step_size
    for dst_cid in overperformers:
        total_overperformance = sum([overperformance[dst_cid] for dst_cid in overperformers])
        logger.info(f"loghill total_overperformance: {total_overperformance}")
        weight = overperformance[dst_cid] / total_overperformance if total_overperformance != 0 else 0
        # make sure we dont go above 1
        mask = (
            (adjusted_ruleset["src_cid"] == region) &
            (adjusted_ruleset["dst_cid"] == dst_cid) &
            (adjusted_ruleset["src_svc"] == src_svc) &
            (adjusted_ruleset["dst_svc"] == dst_svc) &
            (adjusted_ruleset["src_endpoint"] == src_endpoint) &
            (adjusted_ruleset["dst_endpoint"] == dst_endpoint)
        )
        cur_weight = adjusted_ruleset.loc[mask, "weight"].values[0]
        step = weight * step_size
        if cur_weight + step > 1:
            out_of_bounds = True
        else:
            logger.info(f"loghill overperformer: {dst_cid}, weight: {weight}, step: {step}")
            adjusted_ruleset.loc[(adjusted_ruleset["src_cid"] == region) & (adjusted_ruleset["dst_cid"] == dst_cid) 
                                & (adjusted_ruleset["src_svc"] == src_svc) & (adjusted_ruleset["dst_svc"] == dst_svc) 
                                & (adjusted_ruleset["src_endpoint"] == src_endpoint) & (adjusted_ruleset["dst_endpoint"] == dst_endpoint), "weight"] += weight * step_size
    # log the old and adjusted rulesets, with just the weights (something in the form of source region -> destination region -> weight for old and new.)
    # hold the dest service (frontend) and the source service (sslateingress) constant.
    logger.info(f"loghill old ruleset: {compute_traffic_matrix(ruleset)}\nadjusted ruleset: {compute_traffic_matrix(adjusted_ruleset)}")
    return adjusted_ruleset if not out_of_bounds else ruleset, not out_of_bounds


def get_expected_latency_for_rule(load: int, svc: str, methodpath: str) -> int:
    """
    get_expected_latency_for_rule will calculate the expected e2e latency for a given rule based on the current load conditions.
    """
    global e2e_coef_dict
    ep = svc + "@" + methodpath
    if svc not in e2e_coef_dict:
        return -1
    if ep not in e2e_coef_dict[svc]:
        return -1
    a = e2e_coef_dict[svc][ep][ep]
    c = e2e_coef_dict[svc][ep]["intercept"]
    # in form ax^2 + c
    return a * load * load + c


def write_latency(svc: str, avg_processing_latency: int, latency_dict: dict):
    global temp_counter
    global historical_svc_latencies
    # write processing latency in the form of temp_counter, avg_processing_latency
    with open("jumping_latency.csv", "a") as f:
        f.write(f"{temp_counter},{avg_processing_latency}\n")
    with open ("region_jumping_latency.csv", "a") as f:
        for region in ["us-west-1", "us-central-1", "us-south-1", "us-east-1"]:
            f.write(f"{temp_counter},{region},{calculate_avg_processing_latency(latency_dict, svc, 'POST@/cart/checkout', region)}\n")
    if svc not in historical_svc_latencies:
        historical_svc_latencies[svc] = list()
    historical_svc_latencies[svc].append(avg_processing_latency)

@app.post('/hillclimbingPolicy') # from wasm
def handleHillclimbPolicy():
    global cur_hillclimb_latency
    global prev_hillclimb_latency
    global next_hillclimb_latency
    global last_policy_request
    global hillclimb_latency_lock
    global hillclimb_interval
    global last_policy_request_mutex
    svc = request.headers.get('x-slate-servicename').split("-us-")[0]
    # svc_trunc: remove -us-west-1 or -us-east-1 from the end
    podname = request.headers.get('x-slate-podname')[-5:]
    if hillclimb_interval == -1:
        logger.info(f"hillclimbingPolicy for (pod {podname}): hillclimb_interval is -1, doing nothing")
        return ""
    last_policy_request_mutex.acquire(blocking=True)
    if svc not in last_policy_request:
        last_policy_request[svc] = 0
    # logger.info(f"hillclimbingPolicy for (pod {podname}): svc: {svc}")
    hillclimb_latency_lock.acquire(blocking=True)
    if time.time() - last_policy_request[svc] > (hillclimb_interval - 2):
        # this is the first request after the interval
        # next to cur, and cur to prev, and clear next for the next interval
        # this basically "freezes" the current state, so subsequent requests in the same interval will be compared to this state
        # the reason we're doing this is because we don't know how many replicas are there for each service, 
        #  so we can't just copy states on the last request
        logger.info(f"hillclimbingPolicy for (pod {podname}, svc {svc}): INTERVAL EXPIRED (diff {time.time() - last_policy_request[svc]}), copying states, len(next_hillclimb_latency): {len(next_hillclimb_latency.get(svc, {})) or 0}, len(cur_hillclimb_latency): {len(cur_hillclimb_latency.get(svc, {})) or 0}")
        if svc in next_hillclimb_latency and svc in cur_hillclimb_latency and len(next_hillclimb_latency[svc]) >= 2 and len(cur_hillclimb_latency[svc]) >= 2:
            add_to_global_history(cur_hillclimb_latency, next_hillclimb_latency, svc)
        if svc in cur_hillclimb_latency:
            prev_hillclimb_latency[svc] = dict()
            prev_hillclimb_latency[svc] = copy.deepcopy(cur_hillclimb_latency[svc])
        if svc in next_hillclimb_latency:
            cur_hillclimb_latency[svc] = dict()
            cur_hillclimb_latency[svc] = copy.deepcopy(next_hillclimb_latency[svc])
        next_hillclimb_latency[svc] = dict()
        logger.info(f"new len(prev_hillclimb_latency): {len(prev_hillclimb_latency)}, new len(cur_hillclimb_latency): {len(cur_hillclimb_latency)}")
    last_policy_request[svc] = time.time()
    last_policy_request_mutex.release()
    if svc not in cur_hillclimb_latency or svc not in prev_hillclimb_latency:
        hillclimb_latency_lock.release()
        logger.info(f"hillclimbingPolicy for (pod {podname}): svc: {svc} not in one of cur or prev, SKIPPING (this could be the first iteration)")
        if svc in cur_hillclimb_latency:
            # svc is in cur, but not in prev
            logger.info(f"svc {svc} is in cur, but not in prev (first iteration) -- returning false") 
            # this is aritrary
            return "false"
        return ""
    cur_r2p = cur_hillclimb_latency[svc]
    prev_r2p = prev_hillclimb_latency[svc]
    # sum up the latency and num_reqs for both current and previous, across all pods and regions
    cur_latency_total = sum([cur_r2p[region][pod]["latency_total"] for region in cur_r2p for pod in cur_r2p[region]])
    cur_num_reqs = sum([cur_r2p[region][pod]["num_reqs"] for region in cur_r2p for pod in cur_r2p[region]])
    prev_latency_total = sum([prev_r2p[region][pod]["latency_total"] for region in prev_r2p for pod in prev_r2p[region]])
    prev_num_reqs = sum([prev_r2p[region][pod]["num_reqs"] for region in prev_r2p for pod in prev_r2p[region]])
    hillclimb_latency_lock.release()
    # calculate the average latency for both current and previous
    if cur_num_reqs == 0 or prev_num_reqs == 0:
        logger.info(f"hillclimbingPolicy for (pod {podname}, svc {svc}): cur_num_reqs: {cur_num_reqs}, prev_num_reqs: {prev_num_reqs}, dodging division by zero")
        return ""
    cur_avg_latency = cur_latency_total / cur_num_reqs
    prev_avg_latency = prev_latency_total / prev_num_reqs
    logger.info(f"hillclimbingPolicy for (pod {podname}, svc {svc}): cur_avg_latency: {cur_avg_latency} (latency total {cur_latency_total}, reqs {cur_num_reqs}), prev_avg_latency: {prev_avg_latency} (latency total {prev_latency_total}, reqs {prev_num_reqs})")

    if cur_avg_latency < prev_avg_latency:
        return "true"
    else:
        return "false"


@app.post('/hillclimbingReport') # from wasm
def handleHillclimbReport():
    global hillclimbing_distribution_history
    global temp_counter
    svc = request.headers.get('x-slate-servicename')
    region = request.headers.get('x-slate-region')
    podname = request.headers.get('x-slate-podname')[-5:]
    old_dist = request.headers.get('x-slate-old-dist')
    new_dist = request.headers.get('x-slate-new-dist')
    avg_latency = request.headers.get('x-slate-avg-latency')
    inbound_rps = request.headers.get('x-slate-inbound-rps')
    outbound_rps = request.headers.get('x-slate-outbound-rps')
    # 2 region specific stuff
    west_latency = request.headers.get('x-slate-us-west-1-latency')
    east_latency = request.headers.get('x-slate-us-east-1-latency')
    west_reqs = request.headers.get('x-slate-us-west-1-outboundreqs')
    east_reqs = request.headers.get('x-slate-us-east-1-outboundreqs')
    if svc == "sslateingress-us-west-1":
        logger.info(f"logadi all headers: {request.headers}")
        logger.info(f"hillclimbing svc: {svc}, region: {region}, podname: {podname}, old_dist: {old_dist}, new_dist: {new_dist}, avg_latency: {avg_latency}, inbound_rps: {inbound_rps}, outbound_rps: {outbound_rps}")
    
    old_dist_rules = old_dist.strip().split(" ")
    new_dist_rules = new_dist.strip().split(" ")
    if len(old_dist_rules) < 4 or len(new_dist_rules) < 4 or not old_dist.strip() or not new_dist.strip():
        return ""
    # old_dist_rules is in the format of [region1, rule1, region2, rule2, ...]
    # we want to convert it to dictionary of {region: rule}
    old_dist_dict = {f"old-{old_dist_rules[i]}": old_dist_rules[i+1] for i in range(0, len(old_dist_rules), 2)}
    new_dist_dict = {f"new-{new_dist_rules[i]}": new_dist_rules[i+1] for i in range(0, len(new_dist_rules), 2)}
    hist = {
        "svc": svc,
        "region": region,
        "podname": podname,
        "avg_latency": avg_latency,
        "inbound_rps": inbound_rps,
        "outbound_rps": outbound_rps,
        "time": str(datetime.datetime.now()),
        "time_millis": str(int(time.time()*1000)),
        "counter": str(temp_counter),
        "west_latency": west_latency or -1,
        "east_latency": east_latency or -1,
        "west_reqs": west_reqs or -1,
        "east_reqs": east_reqs or -1,
        **old_dist_dict,
        **new_dist_dict
    }
    # hist.update(old_dist_dict)
    # hist.update(new_dist_dict)
    hillclimbing_distribution_history.append(hist)
    return ""

def add_to_global_history(prev, cur, svc):
    global global_hillclimbing_distribution_history
    prevstats = get_latency_stats_for_svc(prev, svc, prefix="prev")
    curstats = get_latency_stats_for_svc(cur, svc, prefix="cur")
    hist = {
        "svc": svc,
        "time": str(datetime.datetime.now()),
        "time_millis": str(int(time.time()*1000)),
        "counter": str(temp_counter),
        **prevstats,
        **curstats
    }
    global_hillclimbing_distribution_history.append(hist)

def get_latency_stats_for_svc(latencyobj, svc, prefix=""):
    # latencyobj is a dictionary of svc : {region: {pod: {latency_total, num_reqs}}}
    # return dict in the form of {"<region>-latency": avg_latency, "<region>-reqs": total_reqs, ..., "total-latency": avg_latency, "total-reqs": total_reqs}
    if svc not in latencyobj:
        return {}
    stats = {}
    for region in latencyobj[svc]:
        total_latency = sum([latencyobj[svc][region][pod]["latency_total"] for pod in latencyobj[svc][region]])
        total_reqs = sum([latencyobj[svc][region][pod]["num_reqs"] for pod in latencyobj[svc][region]])
        if total_reqs == 0:
            avg_latency = 0
        else:
            avg_latency = total_latency / total_reqs
        stats[f"{prefix}-{region}-avg-latency"] = str(avg_latency)
        stats[f"{prefix}-{region}-reqs"] = str(total_reqs)
    
    total_latency = sum([sum([latencyobj[svc][region][pod]["latency_total"] for pod in latencyobj[svc][region]]) for region in latencyobj[svc]])
    total_reqs = sum([sum([latencyobj[svc][region][pod]["num_reqs"] for pod in latencyobj[svc][region]]) for region in latencyobj[svc]])
    if total_reqs == 0:
        avg_latency = 0
    else:
        avg_latency = total_latency / total_reqs
    stats[f"{prefix}-total-avg-latency"] = str(avg_latency)
    stats[f"{prefix}-total-reqs"] = str(total_reqs)
    return stats
    

def write_hillclimb_history_to_file():
    # write the entire hillclimbing history as a csv file.
    global hillclimbing_distribution_history
    if len(hillclimbing_distribution_history) > 0:
        # open in overwrite mode
        with open(f'hillclimbing_distribution_history.csv', 'w') as f:
            # write the header as all the keys in the first record
            entry0 = hillclimbing_distribution_history[0]
            f.write(",".join(entry0.keys()) + "\n")
            for record in hillclimbing_distribution_history:
                f.write(",".join(record.values()) + "\n")
        logger.info(f"write_hillclimb_history_to_file happened.")

def write_global_hillclimb_history_to_file():
    # write the entire hillclimbing history as a csv file.
    global global_hillclimbing_distribution_history
    logger.info(f"len(global_hillclimbing_distribution_history): {len(global_hillclimbing_distribution_history)}")
    if len(global_hillclimbing_distribution_history) > 0:
        # open in overwrite mode
        with open(f'global_hillclimbing_distribution_history.csv', 'w') as f:
            # write the header as all the keys in the first record
            entry0 = global_hillclimbing_distribution_history[0]
            f.write(",".join(entry0.keys()) + "\n")
            for record in global_hillclimbing_distribution_history:
                f.write(",".join(record.values()) + "\n")
        logger.info(f"write_global_hillclimb_history_to_file happened.")

def set_endpoint_to_placement(all_endpoints):
    endpoint_to_placement = dict()
    for cid in all_endpoints:
        for svc_name in all_endpoints[cid]:
            for ep in all_endpoints[cid][svc_name]:
                if ep not in endpoint_to_placement:
                    endpoint_to_placement[ep] = set()
                endpoint_to_placement[ep].add(cid)
    return endpoint_to_placement

def set_svc_to_placement(all_endpoints):
    svc_to_placement = dict()
    for cid in all_endpoints:
        for svc_name in all_endpoints[cid]:
            if svc_name not in svc_to_placement:
                svc_to_placement[svc_name] = set()
            svc_to_placement[svc_name].add(cid)
    logger.info('svc_to_placement')
    logger.info(f'{svc_to_placement}')
    return svc_to_placement


'''
metrics-fake-ingress@GET@/start,metrics-handler@GET@/detectAnomalies,us-east-1,us-east-1,1.0
metrics-fake-ingress@POST@/write,metrics-handler@POST@/update,us-east-1,us-east-1,1.0
-->
metrics-fake-ingress@GET@/start,metrics-handler@GET@/detectAnomalies,us-east-1,us-east-1,1.0
metrics-fake-ingress@GET@/start,metrics-handler@GET@/detectAnomalies,us-east-1,us-west-1,0.0 (should be added)
metrics-fake-ingress@POST@/write,metrics-handler@POST@/update,us-east-1,us-east-1,1.0
metrics-fake-ingress@POST@/write,metrics-handler@POST@/update,us-east-1,us-west-1,0.0 (should be added)

'''
def fill_remaining_routing_rule(df):
    return df

'''
For example
Service A has three destinations
Two go to B with different METHOD and PATH
One goes to C
- A@GET@/read -> B@GET@/read
- A@POST@/write -> B@POST@/write
- A@PUT@/update -> C@PUT@/update

Then, the local routing will look like this:

A@GET@/read, B@GET@/read, us-west-1, us-east-1, 1.0
A@GET@/read, B@GET@/read, us-west-1, us-west-1, 0.0
A@POST@/write, B@POST@/write, us-west-1, us-east-1, 1.0
A@POST@/write, B@POST@/write, us-west-1, us-west-1, 0.0
A@PUT@/update, C@PUT@/update, us-west-1, us-east-1, 1.0
A@PUT@/update, C@PUT@/update, us-west-1, us-west-1, 0.0
'''
def local_and_failover_routing_rule(src_svc, src_cid):
    global ep_str_callgraph_table
    global endpoint_to_placement
    if len(ep_str_callgraph_table) == 0:
        logger.debug(f"ERROR: ep_str_callgraph_table is empty.")
        return pd.DataFrame(), ""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        df = pd.DataFrame(columns=["src_endpoint", "dst_endpoint", "src_cid", "dst_cid", "weight"])
        for hashed_cg_key in ep_str_callgraph_table:
            for parent_ep_str in ep_str_callgraph_table[hashed_cg_key]:
                if parent_ep_str.split(cfg.ep_del)[0] != src_svc:
                    continue
                for child_ep_str in ep_str_callgraph_table[hashed_cg_key][parent_ep_str]:
                    dst_svc = child_ep_str.split(cfg.ep_del)[0]
                    # dst_cid_list = endpoint_to_placement[child_ep_str] # west only
                    dst_cid_list = svc_to_placement[dst_svc] # west only
                    if src_cid not in dst_cid_list: # src_cid: east, dst_cid_list: [west]
                        ''' FAILOVER to the closest region '''
                        closest_region_for_this_svc = find_the_closest_region_having_the_service(src_cid, dst_svc)
                        if closest_region_for_this_svc != src_cid:
                            logger.info(f"INTERESTING, src_region({src_cid}) does not have the dst_svc({dst_svc}). The closest available region is {closest_region_for_this_svc}")
                        new_row = {"src_endpoint": parent_ep_str, "dst_endpoint": child_ep_str, "src_cid": src_cid, "dst_cid": closest_region_for_this_svc, "weight": 1.0}
                    else:
                        new_row = {"src_endpoint": parent_ep_str, "dst_endpoint": child_ep_str, "src_cid": src_cid, "dst_cid": src_cid, "weight": 1.0}
                            # else:
                            #     new_row = {"src_endpoint": parent_ep_str, "dst_endpoint": child_ep_str, "src_cid": src_cid, "dst_cid": dst_cid, "weight": 0.0}
                    new_row_df = pd.DataFrame([new_row])
                    df = pd.concat([df, new_row_df], ignore_index=True)
        csv_string = df.to_csv(header=False, index=False)
        logger.debug(f"local_and_failover_routing_rule, LOCAL: {src_svc}, {src_cid}, {csv_string.strip()}")
        return df, csv_string

def always_remote_routing_rule(src_svc, src_cid):
    global ep_str_callgraph_table
    global endpoint_to_placement
    global placement
    num_cluster = len(placement)
    local_pct = 0.0001*num_cluster # 0.0001 to local
    remote_pct = 1 - local_pct # 0.9999 to remote
    if len(ep_str_callgraph_table) == 0:
        logger.error(f"ERROR: ep_str_callgraph_table is empty.")
        return
    df = pd.DataFrame(columns=["src_endpoint", "dst_endpoint", "src_cid", "dst_cid", "weight"])
    for hashed_cg_key in ep_str_callgraph_table:
        for parent_ep_str in ep_str_callgraph_table[hashed_cg_key]:
            if parent_ep_str.split(cfg.ep_del)[0] != src_svc:
                continue
            for child_ep_str in ep_str_callgraph_table[hashed_cg_key][parent_ep_str]:
                logger.debug(f"{parent_ep_str} -> {child_ep_str}")
                dst_cid_list = endpoint_to_placement[child_ep_str]
                for dst_cid in dst_cid_list:
                    if src_cid == dst_cid:
                        new_row = {"src_endpoint": parent_ep_str, "dst_endpoint": child_ep_str, "src_cid": src_cid, "dst_cid": dst_cid, "weight": local_pct}
                        new_row_df = pd.DataFrame([new_row])
                        df = pd.concat([df, new_row_df], ignore_index=True)
                    else:
                        new_row = {"src_endpoint": parent_ep_str, "dst_endpoint": child_ep_str, "src_cid": src_cid, "dst_cid": dst_cid, "weight": remote_pct}
                        new_row_df = pd.DataFrame([new_row])
                        df = pd.concat([df, new_row_df], ignore_index=True)
    csv_string = df.to_csv(header=False, index=False)
    logger.debug(f"routing rule, REMOTE: {src_svc}, {src_cid}, {csv_string.strip()}")
    return csv_string

def MCLB_routing_rule(src_svc, src_cid):
    global ep_str_callgraph_table
    global endpoint_to_placement
    global placement
    equal_distribution = 1/len(placement)
    if len(ep_str_callgraph_table) == 0:
        logger.error(f"ERROR: ep_str_callgraph_table is empty.")
        return
    df = pd.DataFrame(columns=["src_endpoint", "dst_endpoint", "src_cid", "dst_cid", "weight"])
    for hashed_cg_key in ep_str_callgraph_table:
        for parent_ep_str in ep_str_callgraph_table[hashed_cg_key]:
            if parent_ep_str.split(cfg.ep_del)[0] != src_svc:
                continue
            for child_ep_str in ep_str_callgraph_table[hashed_cg_key][parent_ep_str]:
                dst_cid_list = endpoint_to_placement[child_ep_str]
                for dst_cid in dst_cid_list:
                    if src_cid == dst_cid:
                        new_row = {"src_endpoint": parent_ep_str, "dst_endpoint": child_ep_str, "src_cid": src_cid, "dst_cid": dst_cid, "weight": equal_distribution}
                        new_row_df = pd.DataFrame([new_row])
                        df = pd.concat([df, new_row_df], ignore_index=True)
                    else:
                        new_row = {"src_endpoint": parent_ep_str, "dst_endpoint": child_ep_str, "src_cid": src_cid, "dst_cid": dst_cid, "weight": equal_distribution}
                        new_row_df = pd.DataFrame([new_row])
                        df = pd.concat([df, new_row_df], ignore_index=True)
    csv_string = df.to_csv(header=False, index=False)
    logger.debug(f"routing rule, MCLB: {src_svc}, {src_cid}, {csv_string.strip()}")
    return csv_string


def parse_inflight_stats(body):
    # logger.info(f"body: {body}")
    lines = body.split("\n")
    inflightStats = lines[1]
    return inflightStats


'''
body:
fmt.Sprintf("%d\n%s\n%s", reqCount, inflightStats, requestStatsStr)
'''
def parse_service_level_rps(body):
    lines = body.split("\n")
    rps = int(lines[0])
    return rps

def parse_stats_into_spans(body, given_svc_name):
    lines = body.split("\n")
    requestStats = lines[3:]
    spans = []
    for span_stat in requestStats:
        '''
        span_stat: "us-west-1 metrics-fake-ingress-us-west-1 GET /start 70904b1c08f35622387a6bb5c9141596 387a6bb5c9141596  1709763447436 1709763447540 0 GET@/start,0,18446744073709530962|"
        
        ss = ["us-west-1", "metrics-fake-ingress-us-west-1", "GET", "/start", "70904b1c08f35622387a6bb5c9141596", "387a6bb5c9141596", "1709763447436", "1709763447540", "0", "GET@/start,0,18446744073709530962|"]
        ss = [region, serviceName, method, path, traceId, spanId, startTime, endTime, bodySize, endpointInflightStats]
        '''
        ss = span_stat.split(" ")
        ## NOTE: THIS SHOUD BE UPDATED WHEN member fields in span class is updated.
        if len(ss) != 11:
            logger.debug(f"ERROR, len(ss) != 11, (len(ss):{len(ss)}, ss:{ss})")
            # assert False
            continue
        region = ss[0]
        serviceName = ss[1]
        if serviceName.find("-us-") != -1:
            serviceName = serviceName.split("-us-")[0]
        assert given_svc_name == serviceName
        method = ss[2]
        path = ss[3]
        traceId = ss[4]
        spanId = ss[5]
        parentSpanId = ss[6]
        startTime = int(ss[7])
        endTime = int(ss[8])
        bodySize = int(ss[9])
        # logger.info(f"serviceName: {serviceName}, method: {method}, path: {path}, bodySize: {bodySize}")
        # if serviceName.find("metrics-handler") != -1:
        #     bodySize = 5000
        #     logger.debug(f"Rewriting bodySize: {bodySize}, svc: {serviceName}, method: {method}, path: {path}")
        # else:
        #     bodySize = 50
        #     logger.debug(f"Rewriting bodySize: {bodySize}, svc: {serviceName}, method: {method}, path: {path}")
        # 'GET@/hotels,0,1|POST@/reservation,2,0|GET@/recommendations,2,1|'
        endpointInflightStats = ss[10].split("|")
        if endpointInflightStats[-1] == "":
            endpointInflightStats = endpointInflightStats[:-1]
        rps_dict = dict()
        inflight_dict = dict()
        for ep_load in endpointInflightStats:
            method_and_path = ep_load.split(",")[0]
            method = method_and_path.split("@")[0]
            path = method_and_path.split("@")[1]
            endpoint = sp.Endpoint(svc_name=serviceName, method=method, url=path)
            rps = ep_load.split(",")[1]
            inflight = ep_load.split(",")[2]
            rps_dict[str(endpoint)] = rps
            inflight_dict[str(endpoint)] = inflight
        response_time = endTime - startTime
        if response_time < 0:
            logger.info(f"response time is negative")
            logger.info(f"Skip this span: {serviceName}, {method}, {path}, {response_time}")
            continue
        temp_span = sp.Span(method, path, serviceName, region, \
            traceId, spanId, parentSpanId, \
            startTime, endTime, bodySize, \
            rps_dict=rps_dict, \
            num_inflight_dict=inflight_dict)
        spans.append(temp_span)
        # logger.info(f"new span parsed. serviceName: {serviceName}, bodySize: {bodySize}")
    return spans


def write_spans_to_file():
    global mode
    global profile_output_file
    global list_of_span
    global first_write_flag_for_profiled_trace
    if mode == "profile":
        # if first_write_flag_for_profiled_trace == True:
        #     with open(profile_output_file, "w") as file:
        #         columns = sp.get_columns()
        #         file.write("{columns}\n")
        #     first_write_flag_for_profiled_trace = False
        if len(list_of_span) > 0:
            with stats_mutex:
                with open(profile_output_file, "w") as file:
                    for span in list_of_span:
                        file.write(str(span)+"\n")
            logger.debug(f"write_trace_str_to_file happened.")

def verify_return_df(return_df, src_region):
    global aggregated_rps
    for index, row in return_df.iterrows():
        if row['weight'] < 0 or row['weight'] > 1:
            logger.error(f"ERROR: weight is out of range. {row['weight']}")
            logger.error(f"row: {row}")
            assert False
            
        ## For partial replication scenario, this assertion does not function as its original role
        # assert row['src_endpoint'] in aggregated_rps[row['src_cid']][row['src_svc']]
        # assert row['dst_endpoint'] in aggregated_rps[row['dst_cid']][row['dst_svc']]
        # assert row['src_endpoint'].split(cfg.ep_del)[0] == row['src_svc']
        # assert row['dst_endpoint'].split(cfg.ep_del)[0] == row['dst_svc']
        # assert row['src_cid'] == src_region
        
    return_df = return_df.drop(columns=['src_svc', "dst_svc", "flow", "total"])
    desired_order_of_columns = ['src_endpoint', 'dst_endpoint', 'src_cid', 'dst_cid', 'weight']
    # Select only the columns to keep from the DataFrame
    return_df = return_df.loc[:, desired_order_of_columns] 
    # make sure it has CORRECT order of columns to comply with wasm api
    return_df = return_df[desired_order_of_columns]
    assert list(return_df.columns) == desired_order_of_columns
    return return_df

defaultresponse = """sslateingress@POST@/cart,frontend@POST@/cart,us-west-1,us-west-1,1.0
sslateingress@POST@/cart,frontend@POST@/cart,us-west-1,us-east-1,0.0
"""

# @app.route("/clusterLoad", methods=["POST"]) # from cluster-controller
@app.post('/proxyLoad') # from wasm
def handleProxyLoad():
    # logger.info("handleProxyLoad")
    # return ""
    global aggregated_rps
    global endpoint_level_inflight
    global percentage_df
    # global trace_str_list
    global jumping_df
    global ROUTING_RULE
    global mode
    global list_of_span
    global stats_mutex
    global endpoint_level_rps_mutex
    global per_pod_ep_rps
    # global optimizer_cnt
    global use_optimizer_output
    global temp_counter
    global jumping_feature_enabled
    
    ''' * HEADER in request from WASM * 
    {":method", "POST"},
    {":path", "/proxyLoad"},
    {":authority", "slate-controller.default.svc.cluster.local"},
    {"x-slate-podname", p.podName},
    {"x-slate-servicename", p.serviceName},
    {"x-slate-region", p.region},
    '''
    
    svc = request.headers.get('x-slate-servicename')
    region = request.headers.get('x-slate-region')
    full_podname = request.headers.get('x-slate-podname')
    podname = request.headers.get('x-slate-podname')[-5:]
    
    # if svc == "sslateingress-us-west-1":
    #     logger.info("returning default response to sslateingress-us-west-1")
    #     return defaultresponse
        
    if svc.find("-us-") != -1:
            svc = svc.split("-us-")[0]
            
    if svc == "slate-controller":
        logger.debug(f"WARNING: skip slate-controller in handleproxy")
        return ""
    
    if svc == "consul":
        logger.debug(f"WARNING: skip consul in handleproxy")
        return ""
    
    if region == "SLATE_UNKNOWN_REGION":
        logger.debug(f"skip SLATE_UNKNOWN_REGION, svc: {svc}, region: {region}")
        return "your region is SLATE_UNKNOWN_REGION. It is wrong"
    
    body = request.get_data().decode('utf-8')
    #logger.info(body)
    '''
    * REQUEST BODY FORMAT:
    ------------------------------------------------------------------
    service_level_rps at OnTick time
    endpoint,endpoint_level_rps,endpoint_level_rps|...| at OnTick time
    requestStat-1
    requestStat-2
    requestStat-3
    ------------------------------------------------------------------
    
    * EXAMPLE:
    ------------------------------------------------------------------
    54 
    GET@/start,0,12|POST@/upload,0,34|
    us-west-1 metrics-fake-ingress-us-west-1 GET /start 70904b1c08f35622387a6bb5c9141596 387a6bb5c9141596  1709763447436 1709763447540 0 GET@/start,0,18446744073709530962|
    us-west-1 metrics-fake-ingress-us-west-1 GET /start 8b869b12bba09c5e3843e396eeab84b5 3843e396eeab84b5  1709763447465 1709763447512 0 GET@/start,0,18446744073709530962|
    us-west-1 metrics-fake-ingress-us-west-1 GET /start 4d098d189169f0f7e07e75c587d4c608 e07e75c587d4c608  1709763447751 1709763447814 0 GET@/start,0,18446744073709530944|
    us-west-1 metrics-fake-ingress-us-west-1 GET /start d3c0c9e72a315edce2e118bb2d7be53d e2e118bb2d7be53d  1709763447856 1709763447929 0 GET@/start,0,18446744073709530939|
    ------------------------------------------------------------------
    '''
    logger.debug(f"svc: {svc}, region: {region}")
    if region not in inter_cluster_latency:
        logger.debug(f"Ignore the request from {region} since there is no inter_cluster_latency info for {region}")
        return ""
    
    # this initialization part will not be reached because they should be already initialized in training_phase function by trace.csv files
    with endpoint_level_rps_mutex:
        if region not in aggregated_rps:
            aggregated_rps[region] = dict()
        if svc not in aggregated_rps[region]:
            aggregated_rps[region][svc] = dict()
            
        if region not in endpoint_level_inflight:
            endpoint_level_inflight[region] = dict()
        if svc not in endpoint_level_inflight[region]:
            endpoint_level_inflight[region][svc] = dict()
        
        if region not in per_pod_ep_rps:
            per_pod_ep_rps[region] = dict()
        if svc not in per_pod_ep_rps[region]:
            per_pod_ep_rps[region][svc] = dict()
        
        inflightStats = parse_inflight_stats(body)
        if inflightStats == "":
            logger.debug(f"No inflightStats in {full_podname}")
            # for endpoint in aggregated_rps[region][svc]:
            #     aggregated_rps[region][svc][endpoint] = 0
            for endpoint in endpoint_level_inflight[region][svc]:
                endpoint_level_inflight[region][svc][endpoint] = 0
            for endpoint in per_pod_ep_rps[region][svc]:
                per_pod_ep_rps[region][svc][endpoint][podname] = 0
                
    
    # inflightStats: "GET@/start,4,1|POST@/start,4,1|"
    # METHOD1@URL1,RPS,INFLIGHT|METHOD2@URL2,RPS,INFLIGHT|...|
    logger.debug(f"inflightStats: {inflightStats}")
    
    # endpoints of this service which has load now
    # E.g., there could be three endpoints(GET,POST,PUT) in the Service A and only GET,POST have load now. Then, active_endpoint_stats will be "GET,4,1|POST,10,2|"
    active_endpoint_stats = inflightStats.split("|")[:-1]
    logger.debug(f"active_endpoint_stats: {active_endpoint_stats}")
    
    '''
    TODO: parse_service_level_rps should be updated to ontick per endpoint level rps
    '''
    ##############################################
    svc_level_rps = parse_service_level_rps(body)
    if region not in service_level_rps:
        service_level_rps[region] = dict()
    service_level_rps[region][svc] = svc_level_rps
    
    for endpoint_stat in active_endpoint_stats:
        # E.g., endpoint_stat: GET@/start,4,1
        logger.debug(f"endpoint_stats: {endpoint_stat}")
        method_and_url = endpoint_stat.split(",")[0] # GET@/start
        method = method_and_url.split("@")[0] # GET
        url = method_and_url.split("@")[1] # /start
        active_ep_ontick_rps = int(endpoint_stat.split(",")[1]) # 4
        ontick_inflight = int(endpoint_stat.split(",")[2]) # 1
        endpoint = svc + cfg.ep_del + method_and_url
        
        if endpoint == "slateingress@GET@/":
            logger.error(f"active_ep_ontick_rps: {active_ep_ontick_rps}")
            logger.error(f"svc_level_rps: {svc_level_rps}")
            logger.error(f"ERROR: endpoint: {endpoint}, path, {url}, {region}")
            logger.error(f"ERROR: endpoint: {endpoint}, path, {url}, {region}")
            logger.error(f"ERROR: endpoint: {endpoint}, path, {url}, {region}")
            logger.error(f"inflightStats: {inflightStats}")
            
        endpoint_level_inflight[region][svc][endpoint] = ontick_inflight # not used
        with endpoint_level_rps_mutex:
            if endpoint not in endpoint_to_placement:
                logger.debug(f"ERROR: Skip per_pod_ep_rps, {endpoint}. this endpoint is not in stitched trace.")
            else:
                if endpoint not in per_pod_ep_rps[region][svc]:
                    per_pod_ep_rps[region][svc][endpoint] = dict()
                per_pod_ep_rps[region][svc][endpoint][podname] = active_ep_ontick_rps
                logger.debug(f"per_pod_ep_rps, {region}, {svc}, {endpoint}, {active_ep_ontick_rps}")
            
    if mode == "profile":
        spans = parse_stats_into_spans(body, svc)
        for span in spans:
            list_of_span.append(span) # it will be written into a file in write_spans_to_file() function
        _, csv_string = local_and_failover_routing_rule(svc, region) # response to wasm
        return csv_string
        
        # ''' It is necessary to initialize endpoint rps and endpoint inflight since it is not guaranteed that all endpoints are in the stats. In the current ontick, it shouldn't use previous rps or inflight. If there is stats for endpoint A, it doesn't mean that there is stats for endpoint B. '''
        # all_ep_for_rps_so_far = endpoint_level_rps[region][svc]
        # for ep in all_ep_for_rps_so_far:
        #     endpoint_level_rps[region][svc][ep] = 0
        # all_ep_for_inflight_so_far = endpoint_level_inflight[region][svc]
        # This code is for debugging purpose. for performance, comment it out.
        # for ep in all_ep_for_inflight_so_far:
        #     endpoint_level_inflight[region][svc][ep] = 0
        # for i in len(all_ep_for_rps_so_far):
        #     assert all_ep_for_inflight_so_far[i] == all_ep_for_rps_so_far[i]
        ''' end of if mode == "profile" '''
    
        
    elif mode == "runtime":
        '''
        API from Global Controller ---> WASM
        
        API format:
        src_endpoint, dst_endpoint, src_cid, dst_cid, weight
        
        It is raw text. It should be parsed in wasm.
        example:
        
        routing rule to ingress in west cluster:
        metrics-fake-ingress@GET@/start, us-west-1, us-west-1, 0.6
        metrics-fake-ingress@GET@/start, us-west-1, us-east-1, 0.4
        metrics-fake-ingress@POST@/start, us-west-1, us-west-1, 0.9
        metrics-fake-ingress@POST@/start, us-west-1, us-east-1, 0.1
        
        routing rule to ingress in east cluster:
        metrics-fake-ingress@GET@/start, us-east-1, us-west-1, 1.0
        metrics-fake-ingress@GET@/start, us-east-1, us-east-1, 0.0
        metrics-fake-ingress@POST@/start, us-east-1, us-west-1, 0.8
        metrics-fake-ingress@POST@/start, us-east-1, us-east-1, 0.2
        '''
        logger.debug(f'ROUTING_RULE: {ROUTING_RULE}')
        if ROUTING_RULE == "LOCAL":
            _, csv_string =  local_and_failover_routing_rule(svc, region)
            return csv_string
        elif ROUTING_RULE == "REMOTE":
            return always_remote_routing_rule(svc, region)
        elif ROUTING_RULE == "MCLB":
            return MCLB_routing_rule(svc, region)
        elif ROUTING_RULE == "WATERFALL2":
            # TODO: waterfall result conversion
            # if svc == "frontend" and not percentage_df.empty:
            if not percentage_df.empty:
                logger.debug(f"{svc}, {region}, percentage_df is not empty")
                temp_df = percentage_df.loc[(percentage_df['src_svc'] == svc) & (percentage_df['src_cid'] == region)].copy()
                if len(temp_df) == 0:
                    logger.warning(f"WARNING, Rollback to local routing. {region}, {svc}. percentage_df becomes empty after filtering.")
                    _, csv_string = local_and_failover_routing_rule(svc, region)
                    return csv_string
                temp_df = verify_return_df(temp_df, region)
                temp_df = temp_df.reset_index(drop=True)
                adjusted_df: pd.DataFrame = adjustForHillclimbing(svc, region, temp_df)
                csv_string = temp_df.to_csv(header=False, index=False)
                assert csv_string != ""
                logger.debug(f"Enforcement, {ROUTING_RULE}, temp_counter-{temp_counter}, {full_podname} in {region}\n{csv_string.strip()}")
            else:
                _, csv_string = local_and_failover_routing_rule(svc, region)
                
            # logger.info(f"Enforcement, {ROUTING_RULE}, temp_counter-{temp_counter}, {full_podname} in {region}, {csv_string.strip()}")
            with open(f'percentage_df-{svc}.csv', 'a') as f:
                f.write(csv_string)
            return csv_string
        elif "SLATE" in ROUTING_RULE or ROUTING_RULE == "WATERFALL":
            # NOTE: remember percentage_df is set by 'optimizer_entrypoint' async function
            if type(percentage_df) == type(None):
                logger.warning(f"optimizer never succeeds yet. Rollback to local routing. {full_podname}, {region}")
                _, csv_string = local_and_failover_routing_rule(svc, region)
                return csv_string
            global train_done
            if train_done == False:
                _, csv_string = local_and_failover_routing_rule(svc, region)
                return csv_string
            if percentage_df.empty or (not use_optimizer_output and jumping_df.empty and jumping_feature_enabled):
                logger.debug(f"WARNING, Rollback to local routing. {region}, {full_podname}, percentage_df is empty.")
                ############################################################
                _, csv_string = local_and_failover_routing_rule(svc, region)
                ############################################################
                return csv_string
            else:
                temp_df: pd.DataFrame = None
                if use_optimizer_output or not jumping_feature_enabled:
                    temp_df = percentage_df.loc[(percentage_df['src_svc'] == svc) & (percentage_df['src_cid'] == region)].copy()
                else:
                    temp_df = jumping_df.loc[(jumping_df['src_svc'] == svc) & (jumping_df['src_cid'] == region)].copy()
                if len(temp_df) == 0:
                    logger.debug(f"WARNING, Rollback to local routing. {region}, {full_podname}. percentage_df becomes empty after filtering.")
                    _, csv_string = local_and_failover_routing_rule(svc, region)
                    return csv_string
                with open(f'percentage_df-{svc}.csv', 'a') as f:
                    f.write(temp_df.to_csv(header=False))
                temp_df = verify_return_df(temp_df, region)
                temp_df = temp_df.reset_index(drop=True)
                csv_string = temp_df.to_csv(header=False, index=False)
                assert csv_string != ""
                for index, row in temp_df.iterrows():
                    if row['weight'] < 1.0:
                        # print service having remote routing rule only
                        logger.debug(f"Enforcement,{ROUTING_RULE}, temp_counter-{temp_counter}, {full_podname} in {region}\n{csv_string.strip()}")
                        break
                return csv_string
        else: # Invalid routing rule
            logger.error(f"ERROR: ROUTING_RULE is not supported yet. ROUTING_RULE: {ROUTING_RULE}")
            assert False
        ''' end of if mode == runtime '''
    else: # Invalid mode
        _, csv_string = local_and_failover_routing_rule(svc, region)
        return csv_string
    assert False # This line shouldn't be reached

def print_endpoint_level_inflight():
    global endpoint_level_inflight
    logger.info("endpoint_level_inflight")
    for region in endpoint_level_inflight:
        for svc in endpoint_level_inflight[region]:
            for ep in endpoint_level_inflight[region][svc]:
                logger.info(f"{region}, {svc} {ep} {endpoint_level_inflight[region][svc][ep]}")

def print_aggregated_rps():
    global aggregated_rps
    logger.info("aggregated_rps")
    for region in aggregated_rps:
        for svc in aggregated_rps[region]:
            for endpoint in aggregated_rps[region][svc]:
                logger.info(f"endpoint_rps: {region}, {svc}, {endpoint}, {aggregated_rps[region][svc][endpoint]}")
                
def print_service_level_rps():
    global service_level_rps
    logger.info("service_level_rps")
    for region in service_level_rps:
        for svc in service_level_rps[region]:
            logger.info(f"service_rps: {service_level_rps[region][svc]}, {region}, {svc}")

def print_ep_str_callgraph_table():
    global ep_str_callgraph_table
    logger.info("ep_str_callgraph_table")
    idx = 0
    for hashed_cg_key in ep_str_callgraph_table:
        logger.info("*"*60)
        logger.info(f"hashed_cg_key-{idx}: {hashed_cg_key}")
        for ep_str in ep_str_callgraph_table[hashed_cg_key]:
            logger.info(f"{ep_str} -> {ep_str_callgraph_table[hashed_cg_key][ep_str]}")
        logger.info("")
        # logger.info("*"*60)
        idx += 1
        
def file_write_ep_str_callgraph_table():
    global ep_str_callgraph_table
    with open("ep_str_callgraph_table.txt", "w") as file:
        idx = 0
        for hashed_cg_key in ep_str_callgraph_table:
            file.write("*"*60+"\n")
            file.write(f"hashed_cg_key-{idx}: {hashed_cg_key}\n")
            for ep_str in ep_str_callgraph_table[hashed_cg_key]:
                file.write(f"{ep_str} -> {ep_str_callgraph_table[hashed_cg_key][ep_str]}\n")
            file.write("\n")
            idx += 1

def get_total_rps_for_service_in_region(target_svc, target_region, aggregated_rps):
    total_svc_level_rps_in_region = 0
    if target_region in aggregated_rps and target_svc in aggregated_rps[target_region]:
        for ep in aggregated_rps[target_region][target_svc]:
            total_svc_level_rps_in_region += aggregated_rps[target_region][target_svc][ep]
    return total_svc_level_rps_in_region

def get_total_rps_for_service(target_svc, aggregated_rps):
    total_svc_level_rps = 0
    for region in aggregated_rps:
        if target_svc in aggregated_rps[region]:
            logger.debug(f"get_total_rps_for_service: {region}, {target_svc}")
            for ep in aggregated_rps[region][target_svc]:
                total_svc_level_rps += aggregated_rps[region][target_svc][ep]
    return total_svc_level_rps

def get_total_cap_for_service(target_svc):
    global max_capacity_per_service
    total_cap = 0
    for svc in max_capacity_per_service:
        for region in max_capacity_per_service[svc]:
            if svc == target_svc:
                total_cap += max_capacity_per_service[svc][region]
    return total_cap

def check_total_demand_less_than_total_capacity(svc, aggregated_rps):
    total_demand = get_total_rps_for_service(svc, aggregated_rps)
    total_cap = get_total_cap_for_service(svc)
    logger.debug(f"Total capacity: {total_cap}, total demand: {total_demand}, svc,{svc}")
    if total_demand > total_cap:
        return False, total_demand, total_cap
    return True, total_demand, total_cap

def get_root_node_rps(ep_str_callgraph_table, aggregated_rps):
    root_ep = dict()
    for hashed_cg_key in ep_str_callgraph_table:
        root_ep[hashed_cg_key] = opt_func.find_root_node(ep_str_callgraph_table[hashed_cg_key])
    root_node_rps = dict()
    if len(root_ep) != 0:
        logger.debug('root_node_rps,hashed_cg_key,region,svc_name,endpoint,rps')
        for hashed_cg_key in root_ep:
            for cid in aggregated_rps:
                for svc_name in aggregated_rps[cid]:
                    for ep in aggregated_rps[cid][svc_name]:
                        if ep == root_ep[hashed_cg_key]:
                            if cid not in root_node_rps:
                                root_node_rps[cid] = dict()
                            if svc_name not in root_node_rps[cid]:
                                root_node_rps[cid][svc_name] = dict()
                            root_node_rps[cid][svc_name][ep] = aggregated_rps[cid][svc_name][ep]
                            logger.debug(f'root_node_rps,{hashed_cg_key},{cid},{svc_name},{ep},{root_node_rps[cid][svc_name][ep]}')
    return root_node_rps


def check_root_node_rps_condition(agg_root_node_rps):
    agg_root_node_rps_exists = False
    for cid in agg_root_node_rps:
        for svc in agg_root_node_rps[cid]:
            for ep in agg_root_node_rps[cid][svc]:
                if agg_root_node_rps[cid][svc][ep] != 0:
                    agg_root_node_rps_exists = True
    return agg_root_node_rps_exists

def sort_region_by_ingressgw_rps(ingress_gw_svc_name, aggregated_rps):
    region_rps_list = list()
    for region in aggregated_rps:
        for svc in aggregated_rps[region]:
            for endpoint in aggregated_rps[region][svc]:
                if svc == ingress_gw_svc_name:
                    region_rps_list.append([region, aggregated_rps[region][svc][endpoint]])
    region_rps_list.sort(key=lambda x: x[1], reverse=False) # reverse=False: ascending
    order_of_optimization = [elem[0] for elem in region_rps_list]
    return order_of_optimization

def find_the_closest_region_having_the_service(src_region, target_svc):
    global inter_cluster_latency
    global placement
    sorted_region_list = sort_region_by_network_latency(src_region)
    for dst_region in sorted_region_list:
        if dst_region in placement and target_svc in placement[dst_region]:
            return dst_region
    logger.error(f"ERROR: target_svc({target_svc}) doesn't exist in any region.")
    assert False

def sort_region_by_network_latency(src_region):
    global inter_cluster_latency
    # inter_cluster_latency[src_region][dst_region] = inter cluster latency
    region_latency_list = list()
    for dst_region in inter_cluster_latency[src_region]:
        # if dst_region != src_region: # exclude myself
        region_latency_list.append([dst_region, inter_cluster_latency[src_region][dst_region]])
    region_latency_list.sort(key=lambda x: x[1], reverse=False) # reverse=False: ascending
    sorted_region_list = [elem[0] for elem in region_latency_list]
    return sorted_region_list

def update_remaining_capacity(curr_remaining_capacity, percentage_df):
    for index, row in percentage_df.iterrows():
        dst_svc = row['dst_svc']
        dst_region = row['dst_cid']
        flow = row['flow']
        if flow == 0:
            continue
        curr_remaining_capacity[dst_svc][dst_region] -= flow 

def get_total_svc_level_rps(aggregated_rps):
    total_svc_level_rps = dict()
    for region in aggregated_rps:
        for svc in aggregated_rps[region]:
            if svc not in total_svc_level_rps:
                total_svc_level_rps[svc] = 0
            for endpoint in aggregated_rps[region][svc]:
                total_svc_level_rps[svc] += aggregated_rps[region][svc][endpoint]
    return total_svc_level_rps

def get_svc_level_rps(aggregated_rps):
    svc_level_rps = dict()
    for region in aggregated_rps:
        if region not in svc_level_rps:
            svc_level_rps[region] = dict()
        for svc in aggregated_rps[region]:
            if svc not in svc_level_rps[region]:
                svc_level_rps[region][svc] = 0
            for endpoint in aggregated_rps[region][svc]:
                svc_level_rps[region][svc] += aggregated_rps[region][svc][endpoint]
    return svc_level_rps


def get_svc_level_topology():
    global ep_str_callgraph_table
    for hashed_cg_key in ep_str_callgraph_table:
        for parent_ep_str in ep_str_callgraph_table[hashed_cg_key]:
            svc = parent_ep_str.split(cfg.ep_del)[0]
            if svc not in svc_to_placement:
                svc_to_placement[svc] = set()
            for child_ep_str in ep_str_callgraph_table[hashed_cg_key][parent_ep_str]:
                svc_to_placement[svc].add(child_ep_str.split(cfg.ep_del)[1])


def fill_local_first(src_region, remaining_src_region_src_svc_rps, waterfall_load_balance, src_svc="slate-ingress", dst_svc="frontend"):
    global max_capacity_per_service
    global temp_counter
    dst_region = src_region
    src_original_demand = remaining_src_region_src_svc_rps[src_region]
    dst_original_cap = max_capacity_per_service[dst_svc][dst_region]
    if max_capacity_per_service[dst_svc][dst_region] >= remaining_src_region_src_svc_rps[src_region]:
        max_capacity_per_service[dst_svc][dst_region] -= remaining_src_region_src_svc_rps[src_region]
        waterfall_load_balance[src_region][dst_region] = remaining_src_region_src_svc_rps[src_region]
        remaining_src_region_src_svc_rps[src_region] = 0
    else:
        remaining_src_region_src_svc_rps[src_region] -= max_capacity_per_service[dst_svc][dst_region]
        waterfall_load_balance[src_region][dst_region] = max_capacity_per_service[dst_svc][dst_region]
        max_capacity_per_service[dst_svc][dst_region] = 0
    logger.info(f"{temp_counter},waterfall2,{src_svc},{dst_svc},{src_region},{dst_region},{waterfall_load_balance[src_region][dst_region]}")
    logger.debug(f"{temp_counter},waterfall2,src remaining_src_region_src_svc_rps[{src_region}]: {src_original_demand},{remaining_src_region_src_svc_rps[src_region]}")
    logger.debug(f"{temp_counter},waterfall2,dst max_capacity_per_service[{dst_svc}][{dst_region}]: {dst_original_cap},{max_capacity_per_service[dst_svc][dst_region]}")
    return waterfall_load_balance
    
def waterfall_heurstic(src_region, remaining_src_region_src_svc_rps, waterfall_load_balance, src_svc="slate-ingress", dst_svc="frontend"):
    global max_capacity_per_service
    sorted_dst_region_list = sort_region_by_network_latency(src_region)
    for dst_region in sorted_dst_region_list:
        if dst_region in svc_to_placement[dst_svc]:
            assert max_capacity_per_service[dst_svc][dst_region] >= 0
            if max_capacity_per_service[dst_svc][dst_region] == 0:
                continue
            if max_capacity_per_service[dst_svc][dst_region] >= remaining_src_region_src_svc_rps[src_region]:
                # it will be last iteration
                original_cap = max_capacity_per_service[dst_svc][dst_region]
                max_capacity_per_service[dst_svc][dst_region] -= remaining_src_region_src_svc_rps[src_region]
                logger.info(f"{temp_counter},waterfall2,{src_svc},{dst_svc},{src_region},{dst_region},{remaining_src_region_src_svc_rps[src_region]}")
                if src_region not in waterfall_load_balance:
                    waterfall_load_balance[src_region] = dict()
                waterfall_load_balance[src_region][dst_region] = remaining_src_region_src_svc_rps[src_region]
                src_orignal_demand = remaining_src_region_src_svc_rps[src_region]
                remaining_src_region_src_svc_rps[src_region] = 0
                logger.debug(f"{temp_counter},waterfall2,src remaining_src_region_src_svc_rps[{src_region}]: {src_orignal_demand},{remaining_src_region_src_svc_rps[src_region]}")
                logger.debug(f"{temp_counter},waterfall2,dst max_capacity_per_service[{dst_svc}][{dst_region}]: {original_cap},{max_capacity_per_service[dst_svc][dst_region]}")
                break
            else:
                logger.debug(f"{temp_counter},waterfall2,max_capacity_per_service[{dst_svc}][{dst_region}] < remaining_src_region_src_svc_rps[{src_region}]({remaining_src_region_src_svc_rps[src_region]})")
                if src_region not in waterfall_load_balance:
                    waterfall_load_balance[src_region] = dict()
                waterfall_load_balance[src_region][dst_region] = max_capacity_per_service[dst_svc][dst_region]
                src_original_demand = remaining_src_region_src_svc_rps[src_region]
                remaining_src_region_src_svc_rps[src_region] -= max_capacity_per_service[dst_svc][dst_region]
                dst_original_cap = max_capacity_per_service[dst_svc][dst_region]
                max_capacity_per_service[dst_svc][dst_region] = 0
                logger.info(f"{temp_counter},waterfall2,{src_region},{dst_region},{dst_original_cap},{max_capacity_per_service[dst_svc][dst_region]}")
                logger.debug(f"{temp_counter},waterfall2,src remaining_src_region_src_svc_rps[{src_region}]: {src_original_demand},{remaining_src_region_src_svc_rps[src_region]}")
                logger.debug(f"{temp_counter},waterfall2,dst max_capacity_per_service[{dst_svc}][{dst_region}]: {max_capacity_per_service[dst_svc][dst_region]}")
                if remaining_src_region_src_svc_rps[src_region] == 0:
                    logger.debug(f"{temp_counter},waterfall2 for {src_region}, {src_svc} is done. break and return")
                    break
    return waterfall_load_balance

def write_optimizer_output(temp_counter, percentage_df, desc, fn):
    if percentage_df.empty:
        if os.path.isfile(fn):
            with open(fn, "a") as f:
                f.write(f"idx,{temp_counter},fail,{desc}\n")
    else:
        sim_percentage_df = percentage_df.copy()
        # if benchmark_name != "usecase3-compute-diff" or benchmark_name != "hotelreservation":
        #     sim_percentage_df = sim_percentage_df.drop(columns=['src_endpoint', "dst_endpoint"]).reset_index(drop=True)
        
        sim_percentage_df.insert(loc=0, column="counter", value=temp_counter)
        sim_percentage_df = sim_percentage_df.reset_index(drop=True)
        sim_percentage_df.index = [''] * len(sim_percentage_df)
        
        if os.path.isfile(fn) == False:
            sim_percentage_df.to_csv(fn, mode="w")
        else:
            sim_percentage_df.to_csv(fn, mode="a")
        logger.info(f"sim_percentage_df:\n{sim_percentage_df.to_csv()}")
        


## All variables are global variables
def optimizer_entrypoint():
    global coef_dict
    global endpoint_level_inflight
    # global endpoint_level_rps
    global placement
    # global all_endpoints
    global svc_to_placement
    global endpoint_to_placement
    global endpoint_to_cg_key
    global ep_str_callgraph_table
    global percentage_df
    global ROUTING_RULE
    global traffic_segmentation
    global objective
    global max_capacity_per_service
    global mode
    global temp_counter
    global degree
    global inter_cluster_latency
    global CAPACITY
    global train_done
    global benchmark_name
    global bottleneck_service
    global parent_of_bottleneck_service
    global aggregated_rps
    global agg_root_node_rps
    global use_optimizer_output
    global jumping_df
    global jumping_feature_enabled
    # aggregated_rps = aggregate_rps_by_region()
    # record_endpoint_rps(aggregated_rps)
    # agg_root_node_rps = get_root_node_rps(ep_str_callgraph_table, aggregated_rps)
    
    if mode != "runtime":
        logger.warning(f"run optimizer only in runtime mode. current mode: {mode}.")
        return
    if ROUTING_RULE != "SLATE" and ROUTING_RULE != "SLATE-with-jumping-local" and ROUTING_RULE != "SLATE-with-jumping-global" and ROUTING_RULE != "SLATE-without-jumping" and ROUTING_RULE != "WATERFALL" and ROUTING_RULE != "WATERFALL2":
        logger.warning(f"run optimizer only in SLATE, SLATE-with-jumping, SLATE-without-jumping or WATERFALL ROUTING_RULE. current ROUTING_RULE: {ROUTING_RULE}.")
        return
    if train_done == False:
        logger.warning(f"runtime True, {ROUTING_RULE}, BUT run optimizer only after training. train_done: {train_done}.")
        return
    if len(ep_str_callgraph_table) == 0:
        logger.error(f"!!! ERROR !!!: ep_str_callgraph_table is empty.")
        return
    
    '''partial replication'''
    global exclude_svc
    # aggregated_rps[cid][svc_name][ep] = rps
    for target_region in exclude_svc:
        for target_svc in exclude_svc[target_region]:
            del aggregated_rps[target_region][target_svc]
            logger.warning(f"NOTE: partial replication, exclude_svc, {target_region}, {target_svc}")
            logger.warning(f"NOTE: partial replication, exclude_svc, {target_region}, {target_svc}")
            logger.warning(f"NOTE: partial replication, exclude_svc, {target_region}, {target_svc}")
    
    ''' check '''
    init_max_capacity_per_service(CAPACITY)        
    with open('optimizer_input.txt', 'w') as f:
        f.write(f"coef_dict: {coef_dict}\n")
        f.write(f"endpoint_level_inflight: {endpoint_level_inflight}\n")
        f.write(f"aggregated_rps: {aggregated_rps}\n")
        f.write(f"placement: {placement}\n")
        f.write(f"all_endpoints: {all_endpoints}\n")
        # f.write(f"endpoint_to_cg_key: {endpoint_to_cg_key}\n")
        f.write(f"ep_str_callgraph_table: {ep_str_callgraph_table}\n")
        f.write(f"capacity: {CAPACITY}\n")
        f.write(f"traffic_segmentation: {traffic_segmentation}\n")
        f.write(f"objective: {objective}\n")
    if check_root_node_rps_condition(agg_root_node_rps) == False:
        logger.error(f'!!! Skip optimizer !!! all root_node_rps all regions are 0')
        return
    
    # for svc in max_capacity_per_service:
        # for region in max_capacity_per_service[svc]:
    # total_cap = get_total_cap_for_service(svc)
    
    assert parent_of_bottleneck_service != "not_init"
    assert parent_of_bottleneck_service != ""
    
    src_svc_total_demand = get_total_rps_for_service(parent_of_bottleneck_service, aggregated_rps) # frontend
    dst_svc_total_cap = get_total_cap_for_service(bottleneck_service) # a
    if src_svc_total_demand > dst_svc_total_cap: 
        logger.error(f"!!! ERROR !!! Total demand({src_svc_total_demand}) at {parent_of_bottleneck_service} > total capcity({dst_svc_total_cap}) at {bottleneck_service}")
        new_capacity_for_bottleneck_svc = int(src_svc_total_demand/len(max_capacity_per_service[bottleneck_service]))+1
        for dst_region in max_capacity_per_service[bottleneck_service]:
            max_capacity_per_service[bottleneck_service][dst_region] = new_capacity_for_bottleneck_svc
            logger.error(f"recalc capacity: {bottleneck_service}, old_capacity,{max_capacity_per_service[bottleneck_service][dst_region]} -> new_capacity, {new_capacity_for_bottleneck_svc}")
    ## Passed all the basic requirement
    logger.info(f"start run optimizer temp_counter-{temp_counter} ROUTING_RULE:{ROUTING_RULE}")
    logger.info(f"before run_optimizer temp_counter-{temp_counter}")
    # logger.info(f"inter_cluster_latency: {inter_cluster_latency}")
    
    
    if "SLATE" in ROUTING_RULE:
        if benchmark_name == "usecase1-cascading":
            logger.info(f"WARNING: Keep the capacity threshold for SLATE for usecase1-cascading")
        else:
            # NOTE: No capacity threshold for SLATE
            logger.info(f"WARNING: No capacity threshold in SLATE. latency curve will cover things")
            for svc in max_capacity_per_service:
                for region in max_capacity_per_service[svc]:
                    max_capacity_per_service[svc][region] = 100000
        ts = time.time()
        logger.info(f"run_optimizer starts")
        global endpoint_sizes
        global DOLLAR_PER_MS
        
        cur_percentage_df, desc = opt.run_optimizer(\
            coef_dict, \
            aggregated_rps, \
            placement, \
            svc_to_placement, \
            endpoint_to_placement, \
            ep_str_callgraph_table, \
            traffic_segmentation, \
            objective, \
            ROUTING_RULE, \
            max_capacity_per_service, \
            degree, \
            inter_cluster_latency, \
            endpoint_sizes, \
            DOLLAR_PER_MS)
        logger.info(f"run_optimizer done, runtime: {time.time()-ts} seconds")
        if not cur_percentage_df.empty:
            percentage_df = cur_percentage_df
    elif ROUTING_RULE == "WATERFALL2":
        waterfall_load_balance = dict()
        remaining_src_region_src_svc_rps = dict()
        # only do it for bottleneck service
        total_src_rps = get_total_rps_for_service(parent_of_bottleneck_service, aggregated_rps)
        total_dst_cap = get_total_cap_for_service(bottleneck_service)
        logger.info(f"parent_of_bottleneck_service: {parent_of_bottleneck_service}, total_src_rps: {total_src_rps}")
        logger.info(f"dst_svc: {bottleneck_service}, total_dst_cap: {total_dst_cap}")
        if total_dst_cap >= total_src_rps: # non-overload scenario
            logger.info(f"total_dst_cap({total_dst_cap}) > total_src_rps({total_src_rps})")
            
            for src_region in aggregated_rps:
                if parent_of_bottleneck_service in aggregated_rps[src_region]:
                    src_svc_total_rps = get_svc_level_rps(aggregated_rps)[src_region][parent_of_bottleneck_service]
                    remaining_src_region_src_svc_rps[src_region] = src_svc_total_rps
            
            # TODO: hardcoded
            if benchmark_name == "usecase1-cascading":
                logger.info(f"WARNING: Skip fill_local_first for usecase1-cascading")
            else:
                for src_region in aggregated_rps:
                    if parent_of_bottleneck_service in aggregated_rps[src_region]:
                        if src_region not in waterfall_load_balance:
                            waterfall_load_balance[src_region] = dict()
                        waterfall_load_balance = fill_local_first(src_region, remaining_src_region_src_svc_rps, waterfall_load_balance, parent_of_bottleneck_service, bottleneck_service)
            
            # order_of_optimization = ['us-central-1', 'us-south-1', 'us-east-1', 'us-west-1']
            order_of_optimization = list(aggregated_rps.keys())
            random.shuffle(order_of_optimization)
            # for src_region in aggregated_rps:
            for src_region in order_of_optimization:
                if parent_of_bottleneck_service in aggregated_rps[src_region]:
                    if src_region not in waterfall_load_balance:
                        waterfall_load_balance[src_region] = dict()
                    if remaining_src_region_src_svc_rps[src_region] > 0:
                        # logger.info(f"{src_region} cluster did not consume all rps locally. remaining_src_region_src_svc_rps[{src_region}]: {remaining_src_region_src_svc_rps[src_region]}")
                        logger.debug(f"Continue spill over")
                        waterfall_load_balance = waterfall_heurstic(src_region, remaining_src_region_src_svc_rps, waterfall_load_balance, parent_of_bottleneck_service, bottleneck_service)
                        logger.debug(f"waterfall_load_balance for {parent_of_bottleneck_service}: {waterfall_load_balance}")
            records = list()
            for src_region in waterfall_load_balance:
                for dst_region in waterfall_load_balance[src_region]:
                    # total = get_total_rps_for_service(parent_of_bottleneck_service, aggregated_rps) # THIS IS BUG
                    # apply the same svc level routing policy to all endpoints
                    for hashed_cg_key in ep_str_callgraph_table:
                        for parent_ep_str in ep_str_callgraph_table[hashed_cg_key]:
                            for child_ep_str in ep_str_callgraph_table[hashed_cg_key][parent_ep_str]:
                                src_svc = parent_ep_str.split(cfg.ep_del)[0]
                                dst_svc = child_ep_str.split(cfg.ep_del)[0]
                                logger.debug(f"waterfall2,src_svc: {src_svc}, dst_svc: {dst_svc}, pb, {parent_of_bottleneck_service}, b, {bottleneck_service}")
                                if src_svc == parent_of_bottleneck_service and dst_svc == bottleneck_service:
                                    flow = waterfall_load_balance[src_region][dst_region]
                                    total = get_total_rps_for_service_in_region(parent_of_bottleneck_service, src_region, aggregated_rps)
                                    weight = flow / total
                                    logger.debug(f"waterfall2,{parent_of_bottleneck_service},{bottleneck_service},{src_region},{dst_region},{flow},{total},{weight}")
                                    '''Find endpoint dependency belonging to this source svc and destination svc pair
                                    This is needed because wasm dataplane is not able to handle svc level routing policy...'''
                                    row = [parent_of_bottleneck_service, bottleneck_service, parent_ep_str, child_ep_str, src_region, dst_region, flow, total, weight]
                                    records.append(row)
            # waterfall_load_balance:
            # {'us-west-1': {'us-west-1': 100, 'us-east-1':0}, 
            #  'us-east-1': {'us-east-1': 400, 'us-west-1': 179}}
            for src_region in waterfall_load_balance:
                # for dst_region in waterfall_load_balance[src_region]:                        
                '''Fill rest of endpoint connection with local+failover routing'''
                for hashed_cg_key in ep_str_callgraph_table:
                    for parent_ep_str in ep_str_callgraph_table[hashed_cg_key]:
                        for child_ep_str in ep_str_callgraph_table[hashed_cg_key][parent_ep_str]:
                            src_svc = parent_ep_str.split(cfg.ep_del)[0]
                            dst_svc = child_ep_str.split(cfg.ep_del)[0]
                            if src_svc != parent_of_bottleneck_service and dst_svc != bottleneck_service:
                                # this endpoint pair does not appear in the waterfall result
                                # Enforce local+failover routing rule
                                # local_routing_df column: ["src_endpoint", "dst_endpoint", "src_cid", "dst_cid", "weight"]
                                local_routing_df, local_routing_csv_string = local_and_failover_routing_rule(src_svc, src_region)
                                # There must be only one row in local_routing_df
                                for index, row in local_routing_df.iterrows():
                                    weight_local_routing = row['weight']
                                    dst_svc_local_routing = row['dst_endpoint'].split(cfg.ep_del)[0] # dst_svc_local_routing could be different from dst_svc due to failover. dst_svc_local_routing is correct
                                    dst_ep_local_routing = row['dst_endpoint']
                                    flow_local_routing = -1 # NOTE: it is not important since this will not be used in local routing enforcement in proxyload for WATERFALL2
                                    total_local_routing = -1
                                    src_cid = row['src_cid']
                                    dst_cid = row['dst_cid']
                                    row = [src_svc, dst_svc_local_routing, parent_ep_str, dst_ep_local_routing, src_cid, dst_cid, flow_local_routing, total_local_routing, weight_local_routing]
                                    logger.debug(f"local_routing_df row: {row}")
                                    records.append(row)
            
            # add SOURCE to root node (i.e. slateingress)
            # for dst_cid in agg_root_node_rps:
            #     for dst_svc in agg_root_node_rps[dst_cid]:
            #         for dst_endpoint in agg_root_node_rps[dst_cid][dst_svc]:
            #             root_node_rps = agg_root_node_rps[dst_cid][dst_svc][dst_endpoint]
            #             src_endpoint = "SOURCE"
            #             src_svc = "SOURCE"
            #             src_cid = "XXXX"
            #             weight_local_routing = 1
            #             flow_local_routing = root_node_rps
            #             total_local_routing = root_node_rps
            #             row = [src_svc, dst_svc, src_endpoint, dst_endpoint, src_cid, dst_cid, flow_local_routing, total_local_routing, weight_local_routing]
            #             records.append(row)
                        
            # NOTE: row and columns MUST have the same order.
            col = ["src_svc", "dst_svc", "src_endpoint", "dst_endpoint", "src_cid", "dst_cid", "flow", "total", "weight"]
            percentage_df = pd.DataFrame(records, columns=col)
            
            
            waterfall_percentage_df_for_print = percentage_df.drop_duplicates(subset=["src_svc", "dst_svc", "src_cid", "dst_cid", "src_endpoint", "dst_endpoint", "flow", "total", "weight"], keep='last')
            logger.info(f"waterfall_percentage_df_for_print.to_csv(): {waterfall_percentage_df_for_print.to_csv()}")
            
                        
            desc = "waterfall2"
        else: # overload scenario
            logger.info(f"total_dst_cap({total_dst_cap}) < total_src_rps({total_src_rps})")
            overload_ratio = total_src_rps / total_dst_cap
            overload_cap = dict()
            for svc in max_capacity_per_service:
                for region in max_capacity_per_service[svc]:
                    overload_cap[region] = max_capacity_per_service[svc][region] * overload_ratio
            assert False # TODO: not implemented yet

    elif ROUTING_RULE == "WATERFALL":
        global region_pct_df
        '''Idea: running optimizer one region by one region. The order of regions running optimizer is important.'''
        curr_remaining_capacity = copy.deepcopy(max_capacity_per_service) # reset curr_remaining_capacity
        ## schedule lower rps first
        # order_of_optimization = sort_region_by_ingressgw_rps('metrics-fake-ingress')
        ## fixed optimization order
        # order_of_optimization = ['us-south-1', 'us-west-1', 'us-east-1', 'us-central-1']
        if benchmark_name == "metrics":
            order_of_optimization = ['us-central-1', 'us-east-1', 'us-south-1', 'us-west-1']
        elif benchmark_name == "spread-unavail-30bg":
            order_of_optimization = ['us-west-1', 'us-east-1']
        else:
            order_of_optimization = list(aggregated_rps.keys())
            random.shuffle(order_of_optimization)
        logger.info(f"order_of_optimization: {order_of_optimization}")
        for target_region in order_of_optimization:
            target_region_ingress_gw_rps = dict()
            # region_endpoint_level_rps = copy.deepcopy(endpoint_level_rps)
            region_endpoint_level_rps = copy.deepcopy(aggregated_rps)
            for region in region_endpoint_level_rps:
                if region == target_region:
                    if benchmark_name == "metrics":
                        endpoint_rps_at_frontend = region_endpoint_level_rps[target_region]['metrics-fake-ingress']
                    elif benchmark_name == "spread-unavail-30bg":
                        endpoint_rps_at_frontend = region_endpoint_level_rps[target_region]['frontend']
                    elif benchmark_name == "hotelreservation":
                        endpoint_rps_at_frontend = region_endpoint_level_rps[target_region]['slateingress']
                    elif benchmark_name == "alibaba" or benchmark_name == "onlineboutique":
                        endpoint_rps_at_frontend = region_endpoint_level_rps[target_region]['sslateingress']
                    else:
                        logger.error(f"!!! ERROR !!!: benchmark_name is not supported. benchmark_name: {benchmark_name}")
                        assert False
                    for frontend_ep in endpoint_rps_at_frontend:
                        target_region_ingress_gw_rps[frontend_ep] = endpoint_rps_at_frontend[frontend_ep]
                        logger.info(f"run_optimizer temp_counter-{temp_counter}, target_region: {target_region}, frontend endpoint: {frontend_ep}, rps: {endpoint_rps_at_frontend[frontend_ep]}")
                else:
                    for svc in region_endpoint_level_rps[region]:
                        for ep in region_endpoint_level_rps[region][svc]:
                            region_endpoint_level_rps[region][svc][ep] = 0
            logger.info(f"run_optimizer temp_counter-{temp_counter}, optimize region,{target_region}")
            logger.info(f"run_optimizer temp_counter-{temp_counter}, region_endpoint_level_rps: {region_endpoint_level_rps[target_region]}")
            frontend_ep_load_flag = False
            for frontend_ep in target_region_ingress_gw_rps:
                if target_region_ingress_gw_rps[frontend_ep] != 0:
                    logger.info(f"run_optimizer temp_counter-{temp_counter}, target_region: {target_region}, frontend endpoint: {frontend_ep}, rps: {target_region_ingress_gw_rps[frontend_ep]}")
                    frontend_ep_load_flag = True
                    break
            if frontend_ep_load_flag == False:
                logger.info(f"Skip optimizer temp_counter-{temp_counter} for {target_region}. all target_region_ingress_gw_rps == 0")
                for frontend_ep in target_region_ingress_gw_rps:
                    logger.info(f"run_optimizer temp_counter-{temp_counter}, target_region: {target_region}, frontend endpoint: {frontend_ep}, rps: {target_region_ingress_gw_rps[frontend_ep]}")
            else:
                logger.info(f"run_optimizer temp_counter-{temp_counter}, region: {target_region}, target_region_ingress_gw_rps: {target_region_ingress_gw_rps}")
                # region_endpoint_level_rps and curr_remaining_capacity are newly set
                ts = time.time()
                pct_df, desc = opt.run_optimizer(\
                        coef_dict, \
                        region_endpoint_level_rps, \
                        placement, \
                        svc_to_placement, \
                        endpoint_to_placement, \
                        ep_str_callgraph_table, \
                        traffic_segmentation, \
                        objective, \
                        ROUTING_RULE, \
                        curr_remaining_capacity, \
                        degree, \
                        inter_cluster_latency)
                logger.info(f"run_optimizer runtime, {time.time()-ts} seconds")
                
                if not pct_df.empty:
                    region_pct_df[target_region] = pct_df
                    # pct_df_columns = pct_df.columns
                    df_str = pct_df.to_csv(header=False, index=False)
                    logger.info(f"run_optimizer temp_counter-{temp_counter}, target_region: {target_region}")
                    logger.info(f"run_optimizer temp_counter-{temp_counter}, df_str: {df_str}")        
                    prev_remaining_capacity = copy.deepcopy(curr_remaining_capacity)
                    update_remaining_capacity(curr_remaining_capacity, pct_df)
                    for region in curr_remaining_capacity:
                        for svc in curr_remaining_capacity[region]:
                            if curr_remaining_capacity[region][svc] < 0:
                                logger.error(f"!!! ERROR !!!: curr_remaining_capacity[{region}][{svc}] < 0, {curr_remaining_capacity[region][svc]}")
                                assert False
                            # logger.info(f"run_optimizer temp_counter-{temp_counter}, region,{region}, svc,{svc}, remaining_capacity: {prev_remaining_capacity[region][svc]} ->  {curr_remaining_capacity[region][svc]}")
                else:
                    logger.info(f"pct_df: {pct_df}")
                    logger.error(f"!!! ERROR !!! FAIL. run_optimizer temp_counter-{temp_counter}, target_region: {target_region}. {desc}")
                    logger.error(f"use the previous pct_df for this region {target_region}")
                             
        '''merge all the optimizer output'''
        concat_pct_df_col = ["src_svc", "dst_svc", "src_endpoint", "dst_endpoint", "src_cid", "dst_cid", "flow"]
        concat_pct_df = pd.DataFrame(columns=concat_pct_df_col)
        for region in region_pct_df:
            concat_pct_df = pd.concat([concat_pct_df, region_pct_df[region]], ignore_index=True)
            
        # percentage_df = concat_pct_df.groupby(['src_svc', 'dst_svc', 'src_cid', 'dst_cid', 'src_endpoint', 'dst_endpoint']).agg({'flow': 'sum', 'total': 'max'}).reset_index()
        # percentage_df['weight'] = percentage_df['flow']/percentage_df['total']
        
        percentage_df = concat_pct_df.groupby(['src_svc', 'dst_svc', 'src_cid', 'dst_cid', 'src_endpoint', 'dst_endpoint']).agg({'flow': 'sum'}).reset_index()
        # transform is required to keep the original index. Otherwise, it will delete unique dst_endpoint rows
        percentage_df['total'] = percentage_df.groupby(['src_svc', 'src_cid', 'src_endpoint'])['flow'].transform('sum')
        percentage_df['weight'] = percentage_df['flow']/percentage_df['total']
        # write_optimizer_output(temp_counter, percentage_df, desc, "alternative_routing_history.csv")
        # write_optimizer_output(temp_counter, concat_pct_df, desc, "concat_pct_df.csv")
    logger.info(f"after run_optimizer temp_counter-{temp_counter}")
    logger.info(f"run_optimizer temp_counter-{temp_counter}, result: {desc}")
    if percentage_df.empty:
        logger.error(f"ERROR: run_optimizer FAIL (**{desc}**) return without updating percentage_df")
    write_optimizer_output(temp_counter, percentage_df, desc, "routing_history.csv")
    logger.info(f"loghill writing jumping_routing_history.csv {percentage_df if use_optimizer_output or not jumping_feature_enabled else jumping_df} and {jumping_df}")
    write_optimizer_output(temp_counter, percentage_df if use_optimizer_output or not jumping_feature_enabled else jumping_df, desc, "jumping_routing_history.csv")
    ''' end of optimizer_entrypoint '''

def fit_polynomial_regression(data, y_col_name, svc_name, ep_str, cid, degree):
    df = pd.DataFrame(data)
    x_colnames = [x for x in df.columns if x != y_col_name]
    X = df[x_colnames]
    y = df[y_col_name]
    X_transformed = np.hstack((X**degree, np.ones(X.shape)))
    model = LinearRegression(fit_intercept=False)  # Intercept is manually included in X_transformed
    model.fit(X_transformed, y)
    feature_names = x_colnames.copy() + ['intercept']
    coefficients = pd.Series(model.coef_, index=feature_names)
    #feature_names: ['metrics-db@GET@/dbcall', 'intercept']
    #coef_dict[metrics-db][metrics-db@GET@/dbcall]: {'metrics-db@GET@/dbcall': -1.3077803530123953e-17, 'intercept': 0.5702831840648688}
    plt.figure()
    plt.scatter(X, y, color='blue', alpha=0.1, label='Data')
    X_plot = np.linspace(X.min(), X.max(), 100).reshape(-1, 1)
    X_plot_transformed = np.hstack((X_plot**degree, np.ones(X_plot.shape)))
    y_plot = model.predict(X_plot_transformed)
    plt.plot(X_plot, y_plot, color='red', linewidth=2, label=f'Cubic Fit: $a \cdot x^{degree} + b$')
    plt.xlabel(x_feature)
    plt.ylabel(y_col_name)
    plt.title(f'{ep_str} in {cid}')
    plt.legend()
    plt.savefig(f"latency-{svc_name}.pdf")
    plt.show()
    return coefficients.to_dict()
    
def fit_linear_regression(data, y_col_name):
    df = pd.DataFrame(data)
    x_colnames = list()
    for colname in df.columns:
        if colname != y_col_name:
            x_colnames.append(colname)
    logger.debug(f"x_colnames: {x_colnames}")
    logger.debug(f"y_col_name: {y_col_name}")
    X = df[x_colnames]
    y = df[y_col_name]
    model = LinearRegression()
    model.fit(X, y)
    feature_names =  list(X.columns)+ ['intercept']
    coefficients_df = pd.DataFrame(\
            {'Feature': feature_names, \
            'Coefficient':  list(model.coef_)+[model.intercept_]}\
        )
    coef = dict()
    for index, row in coefficients_df.iterrows():
        coef[row['Feature']] = row['Coefficient']
    return coef

def load_coef(coef_file="coef.csv"):
    loaded_coef = dict()
    
    ## Online boutique endpoint 
    checkoutcart_endpoints = ["frontend@POST@/cart/checkout", "recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations", "sslateingress@POST@/cart/checkout", "checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder", "cartservice@POST@/hipstershop.CartService/GetCart", "paymentservice@POST@/hipstershop.PaymentService/Charge", "currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies", "emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation", "shippingservice@POST@/hipstershop.ShippingService/ShipOrder"]
    
    addtocart_endpoints = ['frontend@POST@/cart', 'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct', 'sslateingress@POST@/cart', 'cartservice@POST@/hipstershop.CartService/AddItem']
    
    check_file_exist(coef_file)
    
    try:
        coef_csv_col = ["svc_name","endpoint","feature","value"]
        df = pd.read_csv(coef_file, names=coef_csv_col, header=None)
        for svc_name in df["svc_name"].unique():
            if svc_name not in loaded_coef:
                loaded_coef[svc_name] = dict()
            svc_df = df[df["svc_name"]==svc_name]
            for endpoint in svc_df["endpoint"].unique():
                if endpoint not in loaded_coef[svc_name]:
                    loaded_coef[svc_name][endpoint] = dict()
                ep_df = svc_df[svc_df["endpoint"]==endpoint]
                for index, row in ep_df.iterrows():
                    
                    ################################################
                    ## Here, you can modify the coefficient value ##
                    ## Originally, endpoints that are not in the checkoutcart_endpoints are doubled ##
                    ## Currently, it does not double with 'if False' statement ##
                    ################################################
                    # if endpoint not in checkoutcart_endpoints:
                    if False:
                        loaded_coef[svc_name][endpoint][row["feature"]] = float(row["value"])*2
                        logger.warning(f"!!! Double the coefficient for {svc_name} {endpoint} {row['feature']} {row['value']}\n"*10)
                    else:
                        logger.info(f"loaded_coef,{svc_name},{endpoint},{row['feature']},{row['value']}")
                        loaded_coef[svc_name][endpoint][row["feature"]] = float(row["value"])
                            
    except Exception as e:
        logger.error(f"!!! ERROR !!!: failed to read coef.csv with error: {e}")
        logger.error(f"!!! ERROR !!!: failed to read coef.csv with error: {e}")
        logger.error(f"!!! ERROR !!!: failed to read coef.csv with error: {e}")
        assert False
    '''
    NOTE: Simply combining different endpoints' coefficients into one service level coefficient
    It assumes that 
    '''
    ret_coef = copy.deepcopy(loaded_coef)
    ################################################################################
    # def get_service_coef(coef_dict, target_svc):
    #     ret = dict()
    #     for svc in coef_dict:
    #         if target_svc == svc:
    #             for ep in coef_dict[svc]:
    #                 for feature in coef_dict[svc][ep]:
    #                     ret[feature] = coef_dict[svc][ep][feature]
    #     return ret
    # for svc1 in loaded_coef:
    #     for ep1 in loaded_coef[svc1]:
    #         for feature1 in loaded_coef[svc1][ep1]: # feature is either 'intercept' or endpoint name
    #             if feature1 != "intercept":
    #                 ret = get_service_coef(loaded_coef, svc1)
    #                 for extra_feat in ret:
    #                     ret_coef[svc1][ep1][extra_feat] = ret[extra_feat]
    ################################################################################
    
    # logger.info("-"*80)
    # for svc in loaded_coef:
    #     for ep in loaded_coef[svc]:
    #         for feat in loaded_coef[svc][ep]:
    #             logger.info(f"loaded_coef,{svc},{ep},{feat},{loaded_coef[svc][ep][feat]}")
    logger.info("-"*80)
    for svc in ret_coef:
        for ep in ret_coef[svc]:
            for feat in ret_coef[svc][ep]:
                logger.info(f"ret_coef,{svc},{ep},{feat},{ret_coef[svc][ep][feat]}")
    logger.info("-"*80)
    return ret_coef


def train_latency_function_with_trace(traces, degree):
    global coef_dict
    df = tst.trace_to_df(traces)
    df.to_csv(f"trace_to_file.csv")
    for cid in df["cluster_id"].unique():
        cid_df = df[df["cluster_id"]==cid]
        for svc_name in cid_df["svc_name"].unique():
            cid_svc_df = cid_df[cid_df["svc_name"]==svc_name]
            if svc_name not in coef_dict:
                coef_dict[svc_name] = dict()
            for ep_str in cid_svc_df["endpoint_str"].unique():
                ep_df = cid_svc_df[cid_svc_df["endpoint_str"]==ep_str]
                data = dict()
                y_col = "latency"
                for index, row in ep_df.iterrows():
                    for key, val in row[x_feature].items():
                        if key not in data:
                            data[key] = list()
                        data[key].append(val)
                    if y_col not in data:
                        data[y_col] = list()
                    data[y_col].append(row[target_y])
                # coef_dict[svc_name][ep_str] = fit_linear_regression(data, y_col)
                coef_dict[svc_name][ep_str] = fit_polynomial_regression(data, y_col, svc_name, ep_str, cid, degree)
        logger.info(f"!!! BREAK !!! after {cid} for train_latency_function_with_trace.")
        logger.info(f"!!! BREAK !!! after {cid} for train_latency_function_with_trace.")
        logger.info(f"!!! BREAK !!! after {cid} for train_latency_function_with_trace.")
        break
    return coef_dict


'''
filter spans
- SLATE_UNKNOWN_REGION in cluster name (refer to the slate-plugin/main.go)
- consul in svc_name (hotel reservation)
string format of trace to span data structure
put unorganized spans into traces data structure 
filter incomplete traces
- ceil(avg_num_svc)
'''
def trace_string_file_to_trace_data_structure(load_coef_flag):
    global trainig_input_trace_file
    # us-east-1, # cluster_id
    # productcatalogservice, # svc_name
    # POST, # method
    # /hipstershop.ProductCatalogService/GetProduct, # path
    # 00fe690b10386fda9cb4e44a5757d64d, # trace_id
    # ba08309a92b83eb0, # span_id
    # e9ca143bab246ca6, # parent_span_id
    # 1725229156069, # st
    # 1725229156069, # et
    # 0, # rt
    # 0, # xt
    # 0, # ct
    # -1, # call_size
    # productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct:0|, # inflight_dict
    # productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct:131|,
    # productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct
    col = ["cluster_id","svc_name","method","path","trace_id","span_id","parent_span_id","st","et","rt","xt","ct","call_size","inflight_dict","rps_dict", "endpoint"]
    
    try:
        df = pd.read_csv(trainig_input_trace_file, names=col, header=None)
    except Exception as e:
        logger.error(f"!!! ERROR !!!: failed to read {trainig_input_trace_file} with error: {e}")
        assert False
    spans = list()
    for index, row in df.iterrows():
        if row["cluster_id"] == "SLATE_UNKNOWN_REGION" or row["svc_name"] == "consul":
            logger.debug(f"svc_name: {row['svc_name']}, cluster_id: {row['cluster_id']} is filtered out")
            continue
        # row: user-us-west-1@POST@/user.User/CheckUser:1|,user-us-west-1@POST@/user.User/CheckUser:14|
        # , is delimiter between rps_dict and inflight_dict
        # | is delimiter between two endpoints
        # @ is delimiter between svc_name @ method @ path
        num_inflight_dict = dict()
        rps_dict = dict()
        try:
            # row["inflight_dict"]: "user-us-west-1@POST@/user.User/CheckUser:1|user-us-west-1@POST@/user.User/CheckUser:1|"
            inflight_list = row["inflight_dict"].split("|")[:-1]
        except:
            logger.error(f"!!! ERROR !!! row['inflight_dict']: {row['inflight_dict']}")
            logger.error(f"!!! ERROR !!! row: {row}")
            assert False
        for ep_inflight in inflight_list:
            # ep_inflight: user-us-west-1@POST@/user.User/CheckUser:1
            temp = ep_inflight.split(":")
            if len(temp) != 2:
                logger.error(f"!!! ERROR !!! len(temp) != 2, ep_inflight: {ep_inflight}")
                logger.error(f"!!! ERROR !!! row: {row}")
                assert False
            ep = temp[0] # user-us-west-1@POST@/user.User/CheckUser
            inflight = int(temp[1]) # 1
            num_inflight_dict[ep] = inflight
            # svc_name = ep.split("@")[0] # user-us-west-1
            # method = ep.split("@")[1] # POST
            # path = ep.split("@")[2] # /user.User/CheckUser
        
        try:
            rps_list = row["rps_dict"].split("|")[:-1]
        except Exception as e:
            logger.error(f"!!! ERROR !!!: failed to split rps_dict with error: {e}")
            logger.error(f"!!! ERROR !!!: row: {row}")
            assert False
        for ep_rps in rps_list:
            temp = ep_rps.split(":")
            # logger.debug(f"len(temp): {len(temp)}")
            if len(temp) != 2:
                logger.error(f"!!! ERROR !!! len(temp) != 2, ep_rps: {ep_rps}")
                logger.error(f"!!! ERROR !!! row: {row}")
                assert False
            ep = temp[0] # user-us-west-1@POST@/user.User/CheckUser
            rps = int(temp[1]) # 1
            rps_dict[ep] = rps
            # svc_name = ep.split("@")[0]
            # method = ep.split("@")[1]
            # path = ep.split("@")[2]
        
        global endpoint_sizes
        endpoint_sizes = {
            "/cart": 520,
            "/cart/checkout": 520,
            "/cart/empty": 259,
            "/setCurrency": 275,
            
            "/cart": 200000,
            "/cart/checkout": 200000,
            "/cart/empty": 2000,
            "/setCurrency": 2000,
            
            "/cart/addItem": 520,\
            "/hipstershop.CartService/AddItem": 520,
            "/hipstershop.CartService/EmptyCart": 259,

            "/cart/getCart": 5483,
            "/hipstershop.CartService/GetCart": 5483,
            
            "/hipstershop.RecommendationService/ListRecommendations": 5442,
            "/recommendation/listRecommendations": 5442,
            
            "/hipstershop.ProductCatalogService/GetProduct": 124687,
            "/productCatalog/getProduct": 259,
            
            "/hipstershop.ShippingService/ShipOrder": 5485,
            "/shipping/shipOrder": 5485,
            
            
            "/currency/convert": 274,
            
            "/hipstershop.PaymentService/Charge": 1055,
            "/payment/charge": 1055,
            
            "/hipstershop.EmailService/SendOrderConfirmation": 6032,
            "/email/sendOrderConfirmation": 6032,
            
            "/checkout/placeOrder": 1832,
            "/hipstershop.CheckoutService/PlaceOrder": 1832,
            
            "/productCatalog/listProducts": 124687,
            "/ad/getAds": 6437,
            "/currency/getSupportedCurrencies": 5183,
            "/productCatalog/searchProducts": 124687,
            "/shipping/getQuote": 5485,
        }
        normalize = 0.01
        for key, value in endpoint_sizes.items():
            endpoint_sizes[key] = value * normalize
        if row["path"] in endpoint_sizes:
            call_size = endpoint_sizes[row["path"]]
        else:
            call_size = int(row["call_size"])
        
        try:
            if load_coef_flag:
                span = sp.Span(row["method"], row["path"], row["svc_name"], row["cluster_id"], \
                    row["trace_id"], row["span_id"], row["parent_span_id"], \
                        st=float(row["st"]), et=float(row["et"]), xt=int(row["xt"]), \
                            callsize=call_size, \
                                rps_dict=rps_dict, \
                                    num_inflight_dict=num_inflight_dict)
            else:
                span = sp.Span(row["method"], row["path"], row["svc_name"], row["cluster_id"], \
                    row["trace_id"], row["span_id"], row["parent_span_id"], \
                        st=float(row["st"]), et=float(row["et"]), xt=-1, \
                            callsize=call_size, \
                                rps_dict=rps_dict, \
                                    num_inflight_dict=num_inflight_dict)
        except Exception as e:
            logger.error(f"!!! ERROR !!!: failed to create span with error: {e}")
            logger.error(f"!!! ERROR !!!: row: {row}")
            assert False
        spans.append(span)
        
    # Convert list of span to traces data structure
    traces = dict()
    for span in spans:
        if span.cluster_id not in traces:
            traces[span.cluster_id] = dict()
        if span.trace_id not in traces[span.cluster_id]:
            traces[span.cluster_id][span.trace_id] = list()
        traces[span.cluster_id][span.trace_id].append(span)
    for cid in traces:
        logger.info(f"len(traces[{cid}]): {len(traces[cid])}")
    return traces
    
def filter_incomplete_traces(traces):
    ''' NOTE: using average num svc in a trace is shaky... '''
    # for cid in traces:
    #     tot_num_svc = 0
    #     for tid in traces[cid]:
    #         tot_num_svc += len(traces[cid][tid])
    #     avg_num_svc = tot_num_svc / len(traces[cid])
    # required_num_svc = math.ceil(avg_num_svc)
    # logger.info(f"avg_num_svc: {avg_num_svc}")
    # logger.info(f"required_num_svc: {required_num_svc}")
    global total_num_services
    required_num_svc = total_num_services # 4
    
    complete_traces = dict()
    for cid in traces:
        if cid not in complete_traces:
            complete_traces[cid] = dict()
    for cid in traces:
        for tid in traces[cid]:
            if len(traces[cid][tid]) == required_num_svc:
                complete_traces[cid][tid] = traces[cid][tid]
    for cid in complete_traces:
        logger.info(f"len(complete_traces[{cid}]): {len(complete_traces[cid])}")
        if len(complete_traces[cid]) == 0:
            logger.error(f"!!! ERROR: len(complete_traces[{cid}]) == 0")
    return complete_traces

def init_max_capacity_per_service(capacity):
    global max_capacity_per_service
    global svc_to_placement
    global bottleneck_service
    for svc in svc_to_placement:
        if svc not in max_capacity_per_service:
            max_capacity_per_service[svc] = dict()
    for svc in svc_to_placement:
        for region in svc_to_placement[svc]:
            if benchmark_name == "metrics":
                if svc != "metrics-handler":
                    max_capacity_per_service[svc][region] = 100000
                else:
                    max_capacity_per_service[svc][region] = capacity
            elif benchmark_name == "spread-unavail-30bg":
                if svc == "frontend" or svc == "c":
                    max_capacity_per_service[svc][region] = 1000
                else: # a, b
                    max_capacity_per_service[svc][region] = capacity
                # if  svc != "frontend":
                #     max_capacity_per_service[svc][region] = 100000
                # else:
                #     max_capacity_per_service[svc][region] = capacity
            elif benchmark_name == "bottleneckc":
                if svc == bottleneck_service:
                    max_capacity_per_service[svc][region] = capacity
                else:
                    max_capacity_per_service[svc][region] = 1000
            elif benchmark_name == "usecase1-howmuch" or "usecase1-whichcluster" or "usecase1-orderofevent" or "usecase1-cascading" or "usecase3-compute-diff":
                if svc == bottleneck_service:
                    max_capacity_per_service[svc][region] = capacity
                else:
                    max_capacity_per_service[svc][region] = 1000
            elif benchmark_name == "hotelreservation":
                max_capacity_per_service['slateingress'][region] = capacity
                max_capacity_per_service['frontend'][region] = capacity
                max_capacity_per_service['recommendation'][region] = capacity
                max_capacity_per_service['profile'][region] = capacity
                max_capacity_per_service['rate'][region] = capacity
                max_capacity_per_service['geo'][region] = capacity
                max_capacity_per_service['search'][region] = capacity
                max_capacity_per_service['reservation'][region] = capacity
                max_capacity_per_service['user'][region] = capacity
                
                # max_capacity_per_service['slateingress'][region] = 1000
                # max_capacity_per_service['frontend'][region] = 1000
                # max_capacity_per_service['recommendation'][region] = 1500
                # max_capacity_per_service['profile'][region] = 1000
                # max_capacity_per_service['rate'][region] = 1000
                # max_capacity_per_service['geo'][region] = 1000
                # max_capacity_per_service['search'][region] = 1000
                # max_capacity_per_service['reservation'][region] = 1000
                # max_capacity_per_service['user'][region] = 1200
            else:
                for region in all_endpoints:
                    for svc in all_endpoints[region]:
                        if svc not in max_capacity_per_service:
                            max_capacity_per_service[svc] = dict()
                        max_capacity_per_service[svc][region] = capacity
                        logger.debug(f"set max_capacity_per_service[{svc}][{region}] = {max_capacity_per_service[svc][region]}")

def check_file_exist(file_path):
    if file_path not in os.listdir() or os.path.getsize(file_path) == 0:
        if file_path not in os.listdir():
            logger.debug(f"ERROR: {profile_output_file} is not in the current directory.")
        if not os.path.exists(file_path):
            logger.error(f"ERROR: The file {file_path} does not exist.")
        logger.debug(f"Retry training again. return...")
        return False
    # file exists but empty
    if os.path.getsize(file_path) == 0:
        logger.error(f"ERROR: {profile_output_file} is empty.")
        return False
    return True

def initialize_global_datastructure(stitched_traces):
    global coef_dict
    global endpoint_level_inflight
    global placement
    global all_endpoints
    global svc_to_placement
    global endpoint_to_placement
    global endpoint_to_cg_key
    global ep_str_callgraph_table
    global mode
    global train_done
    global train_start
    global trainig_input_trace_file
    global max_capacity_per_service
    global degree
    global init_done
    assert init_done == False
    
    logger.info(f"Clusters in stitched_traces: {stitched_traces.keys()}")
    all_endpoints = tst.get_all_endpoints(stitched_traces)
    endpoint_to_placement = set_endpoint_to_placement(all_endpoints)
    svc_to_placement = set_svc_to_placement(all_endpoints)
    placement = tst.get_placement_from_trace(stitched_traces)
    
    '''partial replication'''
    global exclude_svc
    for target_region in exclude_svc:
        for target_svc in exclude_svc[target_region]:        # all_endpoints
            logger.info(f"Remove all_endpoints[{[target_region]}][{target_svc}]: {all_endpoints[target_region][target_svc]}")
            del all_endpoints[target_region][target_svc]
            
            # endpoint_to_placement
            for endpoint in endpoint_to_placement:
                if target_svc == endpoint.split("@")[0]:
                    logger.info(f"Remove endpoint_to_placement[{endpoint}].remove({target_region})")
                    endpoint_to_placement[endpoint].remove(target_region)
                
            # svc_to_placement
            logger.info(f"Remove svc_to_placement[{target_svc}].remove({target_region})")
            svc_to_placement[target_svc].remove(target_region)
            
            # placement
            logger.info(f"Remove placement[{target_region}].remove({target_svc})")
            placement[target_region].remove(target_svc)

    for region in all_endpoints:
        for svc_name in all_endpoints[region]:
            logger.info(f"Init all_endpoints[{region}][{svc_name}]: {all_endpoints[region][svc_name]}")
    for endpoint in endpoint_to_placement:
        logger.info(f"Init endpoint_to_placement[{endpoint}]: {endpoint_to_placement[endpoint]}")
    for svc_name in svc_to_placement:
        logger.info(f"Init svc_to_placement[{svc_name}]: {svc_to_placement[svc_name]}")
    for region in placement:
        logger.info(f"Init placement[{region}]: {placement[region]}")
        
    
    ##################### MOVE #######################
    '''endpoint_to_cg_key = tst.get_endpoint_to_cg_key_map(stitched_traces)
        ep_str_callgraph_table, key: hashed cg_key
        cg_key_hashmap, key: hashed_cg_key, value: cg_key (concat of all ep_str in sorted order)'''
    # ep_str_callgraph_table, cg_key_hashmap = tst.traces_to_endpoint_str_callgraph_table(stitched_traces)
    
    logger.info(f"len(ep_str_callgraph_table: {len(ep_str_callgraph_table)}")
    print_ep_str_callgraph_table()
    file_write_ep_str_callgraph_table()
    logger.info(f"num callgraph: {len(ep_str_callgraph_table)}")
    for cid in placement:
        logger.debug(f"placement[{cid}]: {placement[cid]}")
    # Initialize aggregated_rps, endpoint_level_inflight
    with endpoint_level_rps_mutex:
        for region in all_endpoints:
            if region not in endpoint_level_inflight:
                endpoint_level_inflight[region] = dict()
            for svc in all_endpoints[region]:
                if svc not in endpoint_level_inflight[region]:
                    endpoint_level_inflight[region][svc] = dict()
                for endpoint in all_endpoints[region][svc]:
                    endpoint_level_inflight[region][svc][endpoint] = 0
                    logger.debug(f"Init endpoint_level_inflight[{region}][{svc}][{endpoint}]: {endpoint_level_inflight[region][svc][endpoint]}")
                    
        for region in all_endpoints:
            if region not in aggregated_rps:
                aggregated_rps[region] = dict()
            for svc in all_endpoints[region]:
                if svc not in aggregated_rps[region]:
                    aggregated_rps[region][svc] = dict()
                for endpoint in all_endpoints[region][svc]:
                    aggregated_rps[region][svc][endpoint] = 0
                    logger.info(f"Init aggregated_rps[{region}][{svc}][{endpoint}]: {aggregated_rps[region][svc][endpoint]}")
                    
                    
def check_negative_coef(coef_dict):
    # NOTE: latency function should be strictly increasing function
    for svc_name in coef_dict: # svc_name: metrics-db
        for ep_str in coef_dict[svc_name]: # ep_str: metrics-db@GET@/dbcall
            for feature_ep in coef_dict[svc_name][ep_str]: # feature_ep: 'metrics-db@GET@/dbcall' or 'intercept'
                if feature_ep != "intercept": # a in a*(x^degree) + b
                    if coef_dict[svc_name][ep_str][feature_ep] < 0:
                        coef_dict[svc_name][ep_str][feature_ep] = 0
                        # coef_dict[svc_name][ep_str]['intercept'] = 1
                        print(f"WARNING!!!: coef_dict[{svc_name}][{ep_str}] coefficient is negative. Set it to 0.")
                    else: 
                        if coef_dict[svc_name][ep_str]['intercept'] < 0:
                            # a is positive but intercept is negative
                            coef_dict[svc_name][ep_str]['intercept'] = 1
                            print(f"WARNING: coef_dict[{svc_name}][{ep_str}], coefficient is positive.")
                            print(f"WARNING: But, coef_dict[{svc_name}][{ep_str}], intercept is negative. Set it to 0.")
                            
                            
def set_zero_coef(coef_dict):
    for svc_name in coef_dict:
        for ep_str in coef_dict[svc_name]:
            for feature_ep in coef_dict[svc_name][ep_str]:
                if feature_ep == "intercept":
                    coef_dict[svc_name][ep_str][feature_ep] = 0
                else:
                    coef_dict[svc_name][ep_str][feature_ep] = 0

def training_phase():
    global coef_dict
    global e2e_coef_dict
    global endpoint_level_inflight
    global placement
    global all_endpoints
    global svc_to_placement
    global endpoint_to_placement
    global endpoint_to_cg_key
    global ep_str_callgraph_table
    global mode
    global train_done
    global train_start
    global trainig_input_trace_file
    global max_capacity_per_service
    global degree
    global init_done
    global state
    # if not check_file_exist(trainig_input_trace_file):
    #     return

    if mode != "runtime":
        logger.info(f"mode: {mode}. Skip training.")
        return
    if os.path.isfile(trainig_input_trace_file) == False:
        logger.error(f"[ERROR] {trainig_input_trace_file} does not exist.\n"*10)
        return
    if init_done:
        logger.info(f"Training initialization is done.")
        return

    # We still need it to get the trace to get call graph info. coef.csv will have only the coefficient not the call graph info.
    if load_coef_flag: # load_coef_flag=True assumes that time stitching is done
        try:
            stitched_traces = trace_string_file_to_trace_data_structure(load_coef_flag)
        except Exception as e:
            logger.error(f"!!! ERROR !!!: failed to load trace with error: {e}")
            state = "[!!! PANIC !!!] FAILED trace_string_file_to_trace_data_structure() in training_phase()"
            assert False
    else:
        try:
            traces = trace_string_file_to_trace_data_structure(load_coef_flag)
        except Exception as e:
            logger.error(f"!!! ERROR !!!: failed to load trace with error: {e}")
            state = "[!!! PANIC !!!] FAILED trace_string_file_to_trace_data_structure() in training_phase()"
            assert False
            
        try:
            complete_traces = filter_incomplete_traces(traces)
        except Exception as e:
            logger.error(f"!!! ERROR !!!: failed to filter incomplete traces with error: {e}")
            state = "[!!! PANIC !!!] FAILED filter_incomplete_traces() in training_phase()"
            assert False
            
        try:
            stitched_traces = tst.stitch_time(complete_traces)
        except Exception as e:
            logger.error(f"!!! ERROR !!!: failed to stitch time with error: {e}")
            state = "[!!! PANIC !!!] FAILED stitch_time() in training_phase()"
            assert False
    
    try:
        ep_str_callgraph_table, cg_key_hashmap = tst.traces_to_endpoint_str_callgraph_table(stitched_traces)
    except Exception as e:
        logger.error(f"!!! ERROR !!!: failed to traces_to_endpoint_str_callgraph_table with error: {e}")
        state = "[!!! PANIC !!!] FAILED traces_to_endpoint_str_callgraph_table() in training_phase()"
        assert False
    
    ## Replicate trace for other regions in case they do not appear in the trace
    # for region in ["us-east-1", "us-south-1", "us-central-1"]:
    logger.info(f"REPLICATE trace: {inter_cluster_latency}")
    for region in inter_cluster_latency:
        if region not in stitched_traces:
            stitched_traces[region] = stitched_traces["us-west-1"].copy()
            logger.info(f"Replicate trace for {region}")
    
    try:
        initialize_global_datastructure(stitched_traces=stitched_traces)
        init_done = True
    except Exception as e:
        logger.error(f"!!! ERROR !!!: failed to initialize_global_datastructure with error: {e}")
        state = "[!!! PANIC !!!] FAILED initialize_global_datastructure() in training_phase()"
        assert False
    
    if mode != "runtime":
        logger.debug(f"It is not runtime mode. Skip training. current mode: {mode}")
        return
    
    if train_start:
        logger.debug(f"Training is already started. Skip training.")
        return
    
    if train_done:
        logger.debug(f"Training was done. Training is required only once")
        return
    
    train_start = True
    logger.info(f"Training starts.")
    ts = time.time()
    if degree <= 0:
        logger.error(f"ERROR: degree is not valid. degree: {degree}")
        assert False
    if load_coef_flag:
        try:
            coef_dict = load_coef(coef_file="coef.csv")
            e2e_coef_dict = load_coef(coef_file="e2e-coef.csv")
        except Exception as e:
            logger.error(f"!!! ERROR !!!: failed to load coef with error: {e}")
            state = "[!!! PANIC !!!] load_coef() in training_phase()"
            assert False
            
        for svc_name in coef_dict:
            for ep_str in coef_dict[svc_name]:
                for feature_ep in coef_dict[svc_name][ep_str]:
                    # if feature_ep in coef_dict[svc_name][ep_str]:
                    #     coef_dict[svc_name][ep_str][feature_ep] = coef_dict[svc_name][ep_str][feature_ep]
                    logger.info(f"coef_dict[{svc_name}][{ep_str}][{feature_ep}]: {coef_dict[svc_name][ep_str][feature_ep]}")
    else:
        try:
            coef_dict = train_latency_function_with_trace(stitched_traces, degree)
        except Exception as e:
            logger.error(f"!!! ERROR !!!: failed to train_latency_function_with_trace with error: {e}")
            state = "[!!! PANIC !!!] train_latency_function_with_trace() in training_phase()"
            assert False
    
    check_negative_coef(coef_dict)
    if e2e_coef_dict != None:
        check_negative_coef(e2e_coef_dict)
    
    if ROUTING_RULE == "WATERFALL" or ROUTING_RULE == "WATERFALL2":
        set_zero_coef(coef_dict)
    
    
    # This is just a file write for the final coef for debugging purpose
    with open("coefficient.csv", "w") as f:
        f.write("svc_name, endpoint, coef\n")
        for svc_name in coef_dict:
            for ep_str in coef_dict[svc_name]:
                logger.info(f'final coef_dict[{svc_name}][{ep_str}]: {coef_dict[svc_name][ep_str]}')
                f.write(f'{svc_name},{ep_str},{coef_dict[svc_name][ep_str]}\n')

    with open("e2e-coefficient.csv", "w") as f:
        f.write("svc_name, endpoint, coef\n")
        for svc_name in e2e_coef_dict:
            for ep_str in e2e_coef_dict[svc_name]:
                logger.info(f'final coef_dict[{svc_name}][{ep_str}]: {e2e_coef_dict[svc_name][ep_str]}')
                f.write(f'{svc_name},{ep_str},{e2e_coef_dict[svc_name][ep_str]}\n')
                        
    ''' It will be used as a constraint in the optimizer'''
    train_done = True # train done!
    duration = time.time() - ts
    with open("train_done.txt", "w") as f:
        f.write(f"duration,{duration}")
    logger.info(f"train_done. duration: {duration} sec")
    return


def read_config_file():
    global benchmark_name
    global total_num_services
    global mode
    global ROUTING_RULE
    global MODE_SET
    global CAPACITY
    global degree
    global inter_cluster_latency
    global train_done
    global parent_of_bottleneck_service
    global bottleneck_service
    global load_coef_flag
    global state
    global hillclimb_interval
    global hillclimb_enabled
    global jumping_feature_enabled
    global hillclimb_stepsize
    # global all_clusters
    global traffic_segmentation
    
    env_file = "env.txt"
    with open(env_file, "r") as file:
        lines = file.readlines()
        for line in lines:
            line = line.strip().split(",")
            if line[0] == "benchmark_name":
                if benchmark_name != line[1]:
                    logger.info(f'Update benchmark_name: {benchmark_name} -> {line[1]}')
                    benchmark_name = line[1]
                    ###################################################################
                    if benchmark_name == "usecase1-howmuch" or benchmark_name == "usecase1-whichcluster" or benchmark_name == "usecase1-orderofevent" or benchmark_name == "usecase1-cascading" or benchmark_name == "alibaba":
                        parent_of_bottleneck_service = "frontend"
                        bottleneck_service = "a"
                    elif benchmark_name == "usecase3-compute-diff":
                        bottleneck_service = "compute-node"
                    elif benchmark_name == "hotelreservation":
                        parent_of_bottleneck_service = "slateingress"
                        bottleneck_service = "frontend"
                    elif benchmark_name == "alibaba":
                        parent_of_bottleneck_service = "sslateingress"
                        bottleneck_service = "s6f83"
                    elif benchmark_name == "onlineboutique":
                        parent_of_bottleneck_service = "sslateingress"
                        bottleneck_service = "frontend"
                    elif benchmark_name == "not_init":
                        parent_of_bottleneck_service = "not_init"
                        bottleneck_service = "not_init"
                    else:
                        logger.error(f"!!! ERROR !!!: unknown benchmark_name: {benchmark_name}")
                        state = "[!!! PANIC !!!] unknown benchmark_name"
                        assert False
                        
                    logger.info(f"parent_of_bottleneck_service: {parent_of_bottleneck_service}, bottleneck_service: {bottleneck_service}")
                    ###################################################################
                    
            elif line[0] == "total_num_services":
                if total_num_services != int(line[1]):
                    logger.info(f'Update total_num_services: {total_num_services} -> {line[1]}')
                    total_num_services = int(line[1])
            elif line[0] == "mode":
                if mode != line[1]:
                    if line[1] not in MODE_SET:
                        logger.error(f"!!! ERROR !!!: unknown mode: {line[1]}")
                        assert False
                    if line[1] != mode:
                        logger.info(f'Update mode: {mode} -> {line[1]}')
                        mode = line[1]
            elif line[0] == "routing_rule":
                if ROUTING_RULE != line[1]:
                    if line[1] not in ROUTING_RULE_SET:
                        logger.error(f"ERROR: unknown routing_rule: {line[1]}")
                        assert False
                    if line[1] != ROUTING_RULE:
                        logger.info(f'Update mode: {ROUTING_RULE} -> {line[1]}')
                        ROUTING_RULE = line[1]
                        if ROUTING_RULE.startswith("SLATE-with-jumping"):
                            jumping_feature_enabled = True
                        train_done = False
            elif line[0] == "capacity":
                if CAPACITY != int(line[1]):
                    logger.info(f'Update CAPACITY: {CAPACITY} -> {line[1]}')
                    CAPACITY = int(line[1])
                    assert CAPACITY > 0
            elif line[0] == "degree":
                if degree != int(line[1]):
                    logger.info(f'Update degree: {degree} -> {line[1]}')
                    degree = int(line[1])
            elif line[0] == "inter_cluster_latency":
                # Format: inter_cluster_latency,us-west-1,us-west-1,0
                src = line[1]
                dst = line[2]
                oneway_latency = int(line[3])
                if src not in inter_cluster_latency:
                    inter_cluster_latency[src] = dict()
                if dst not in inter_cluster_latency:
                    inter_cluster_latency[dst] = dict()
                if dst not in inter_cluster_latency[src] or inter_cluster_latency[src][dst] != oneway_latency:
                    logger.info(f'Update inter_cluster_latency: {src} -> {dst}: {oneway_latency}')
                    inter_cluster_latency[src][dst] = oneway_latency
                    inter_cluster_latency[dst][src] = oneway_latency
                # all_clusters.add(src)
                # all_clusters.add(dst)
            elif line[0] == "load_coef_flag":
                if load_coef_flag != int(line[1]):
                    logger.info(f'Update load_coef_flag: {load_coef_flag} -> {int(line[1])}')
                    load_coef_flag = int(line[1])
            elif line[0] == "RPS":
                # format:  RPS,west,addtocart,200
                #          [0]  [1]    [2]    [3]
                region = line[1]
                req_type = line[2]
                rps = int(line[3])
                
                if region not in workload:
                    workload[region] = dict()
                if req_type not in workload[region] or workload[region][req_type] != rps:
                    workload[region][req_type] = rps
                    logger.info(f'Update workload: {line[1]}-{line[2]}: {line[3]}RPS')
            elif line[0] == "traffic_segmentation":
                traffic_segmentation = int(line[1])
            elif line[0] == "background_noise":
                background_noise = int(line[1])
            # elif line[0] == "duration":
            #     duration = int(line[1])
            elif line[0] == "connection":
                connection = int(line[1])
            elif line[0] == "distribution":
                distribution = line[1]
            elif line[0] == "thread":
                thread = int(line[1])
            elif line[0] == "hillclimb_interval":
                hillclimb_interval = int(line[1])
            elif line[0] == "hillclimb_enabled":
                hillclimb_enabled = int(line[1])
            elif line[0] == "hillclimb_stepsize":
                hillclimb_stepsize = int(line[1])
            else:
                logger.debug(f"SKIP parsing unknown config: {line}")
                # logger.error(f"ERROR: unknown config: {line}")
                # state = f"[!!! PANIC !!!] unknown config in {env_file}: {line[0]}"
                
    # logger.info(f"benchmark_name: {benchmark_name}, total_num_services: {total_num_services}, mode: {mode}, ROUTING_RULE: {ROUTING_RULE}")


def record_endpoint_rps(aggregated_rps, counter):
    endpoint_rps_fn = "endpoint_rps_history.csv"
    if os.path.isfile(endpoint_rps_fn) == False:
        with open(endpoint_rps_fn, "w") as f:
            f.write("counter,region,service,endpoint,rps\n")
    else:
        if mode == "runtime" and train_done == False:
            logger.info(f"Skip recording endpoint_rps_history.csv. aggregated_rps has not been initialized because training is not done yet.")
            return
        with open(endpoint_rps_fn, "a") as f:
            for region in aggregated_rps:
                for svc in aggregated_rps[region]:
                    for endpoint in aggregated_rps[region][svc]:
                        temp = f"{counter},{region},{svc},{endpoint},{aggregated_rps[region][svc][endpoint]}"
                        f.write(temp + "\n")
                        
def aggregate_rps_by_region_or_zero():
    global per_pod_ep_rps
    global aggregated_rps
    global temp_counter
    for region in all_endpoints:
        if region not in aggregated_rps: aggregated_rps[region] = dict()
        for svc_name in all_endpoints[region]:
            if svc_name not in aggregated_rps[region]: aggregated_rps[region][svc_name] = dict()
            for ep_str in all_endpoints[region][svc_name]:
                # if endpoint not in aggregated_rps[region][svc_name]: aggregated_rps[region][svc_name][endpoint] = 0
                aggregated_rps[region][svc_name][ep_str] = 0
                logger.debug(f"Set zero, aggregated_rps[{region}][{svc_name}][{ep_str}]: {aggregated_rps[region][svc_name][ep_str]}")
    
    for region in per_pod_ep_rps:
        for svc_name in per_pod_ep_rps[region]:
            for endpoint in per_pod_ep_rps[region][svc_name]:
                for podname in per_pod_ep_rps[region][svc_name][endpoint]:
                    aggregated_rps[region][svc_name][endpoint] += per_pod_ep_rps[region][svc_name][endpoint][podname]
                    
    # logger.info("-"*80)
    for region in per_pod_ep_rps:
        for svc in per_pod_ep_rps[region]:
            for endpoint in per_pod_ep_rps[region][svc]:
                for podname in per_pod_ep_rps[region][svc][endpoint]:
                    logger.debug(f"{temp_counter},per_pod_ep_rps,{region},{svc},{endpoint},{podname},{per_pod_ep_rps[region][svc][endpoint][podname]}")
    # logger.info("-"*80)
    # for region in aggregated_rps:
    #     for svc in aggregated_rps[region]:
    #         for endpoint in aggregated_rps[region][svc]:
    #             logger.info(f"aggregated_rps,{region},{svc},{endpoint},{aggregated_rps[region][svc][endpoint]}")
    # logger.info("-"*80)

def aggregated_rps_routine():
    global per_pod_ep_rps
    global aggregated_rps
    global agg_root_node_rps
    global temp_counter
    global prev_ts
    # aggregate_rps_by_region_or_zero(per_pod_ep_rps)
    aggregate_rps_by_region_or_zero()
    agg_root_node_rps = get_root_node_rps(ep_str_callgraph_table, aggregated_rps)
    if check_root_node_rps_condition(agg_root_node_rps) or temp_counter > 0:
        record_endpoint_rps(aggregated_rps, temp_counter)
        logger.info("-"*80)
        logger.info(f"aggregated_rps_routine, temp_counter-{temp_counter}, gap: {time.time()-prev_ts}")
        prev_ts = time.time()
        for region in agg_root_node_rps:
            for svc in agg_root_node_rps[region]:
                for endpoint in agg_root_node_rps[region][svc]:
                    logger.warning(f"agg_root_node_rps,{region},{svc},{endpoint},{agg_root_node_rps[region][svc][endpoint]}")
        logger.warning("-"*80)
    temp_counter += 1
        
def state_check():
    global state
    if state != "SUCCESS" and state != "empty":
        logger.error(f"state: {state}")
        logger.error(f"state: {state}")
        logger.error(f"state: {state}")
    
if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    
    ''' update mode '''
    scheduler.add_job(func=read_config_file, trigger="interval", seconds=1)
    
    ''' mode: profile '''
    scheduler.add_job(func=write_spans_to_file, trigger="interval", seconds=5)
    
    ''' mode: runtime '''
    time.sleep(3)
    scheduler.add_job(func=training_phase, trigger="interval", seconds=1)
    scheduler.add_job(func=aggregated_rps_routine, trigger="interval", seconds=1)
    scheduler.add_job(func=optimizer_entrypoint, trigger="interval", seconds=1)
    # scheduler.add_job(func=write_load_conditions, trigger="interval", seconds=10)
    scheduler.add_job(func=perform_jumping, trigger="interval", seconds=10)
    scheduler.add_job(func=state_check, trigger="interval", seconds=1)
    # scheduler.add_job(func=write_hillclimb_history_to_file, trigger="interval", seconds=15)
    # scheduler.add_job(func=write_global_hillclimb_history_to_file, trigger="interval", seconds=15)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
    app.run(host='0.0.0.0', port=8080)
