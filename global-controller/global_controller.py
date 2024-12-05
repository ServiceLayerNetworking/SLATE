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
from scipy.stats import t
import math
import matplotlib
matplotlib.use('Agg')  # Use a faster non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import time
import copy
import warnings
import json
import replicate_trace_to_diff_region as trace_parser
import heapq
from multiprocessing import Value
import re
from concurrent.futures import ThreadPoolExecutor

plot_executor = ThreadPoolExecutor(max_workers=1)

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
pd.set_option('display.max_columns', None)  # Show all columns
pd.set_option('display.width', 1000)    

'''runtime (optimizer)'''
# endpoint_level_rps = {}

df_incomplete_traces = {}
global_stitched_df = {} # it will be initialized as a dataframe

trace_locks = {}
aggregated_rps = {} # dict of region -> svcname -> endpoint -> rps
norm_aggregated_rps = {}
agg_root_node_rps = {}
endpoint_level_rps_mutex = Lock()
per_pod_ep_rps_mutex = Lock()
add_trace_mutex = Lock()
per_pod_ep_rps = {}
service_level_rps = {}
endpoint_to_cg_key = {}
ep_str_callgraph_table = {}
all_endpoints = {}
temp_counter = 0
load_coef_flag = False
init_done = False
use_optimizer_output = False
jumping_towards_optimizer = False
placement = {}
coef_dict = {}
normalization_dict = {}
model="poly"
poly_coef_dict = {}
mm1_coef_dict = {}
coef_dict_mutex = Lock()
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
convex_comb_step = 1
convex_comb_direction = 1 # 1 or -1
jumping_ruleset_num_iterations = 0
jumping_ruleset_convergence_iterations = 5
cur_jumping_ruleset = ("", "")
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
workload = dict()
frontend_coef_history = dict()
exclude_svc = {}
# exclude_svc = {"us-central-1": ["paymentservice", 'emailservice', 'shippingservice']}
# exclude_svc = {"us-central-1": ['cartservice']}
# exclude_svc = {"us-central-1": ['checkoutservice']}
# exclude_svc = {"us-central-1": ['checkoutservice'], "us-east-1":['productcatalogservice']}
region_pct_df = dict() # waterfall
parent_of_bottleneck_service = "" # waterfall2
bottleneck_service = "" # "a"
list_of_span = list() # unorganized list of spans
list_of_body = list() # unorganized list of bodies
list_of_body_mutex = Lock()
recent = 5 # in secondss
recent_respnose_time = dict() # region -> load_bucket -> svc -> method_path -> response_time
train_done = False
train_start = False
still_training = False
profile_output_file="trace_string.csv" # traces_str_list -> profile_output_file in write_trace_str_to_file() function every 5s
latency_func = {}
trainig_input_trace_file="trace.csv" # NOTE: It should be updated when the app is changed
x_feature = "rps_dict" # "num_inflightglobal norm_dict"
target_y = "xt"

'''config'''
mode = ""
MODE_SET = ["profile", "runtime", "before_start"]
benchmark_name = ""
# benchmark_set = ["metrics", "matmul-app", "hotelreservation", "spread-unavail-30bg"]
required_total_num_services = 0
ROUTING_RULE = "LOCAL" # It will be updated by read_config_file function.
ROUTING_RULE_SET = ["LOCAL", "SLATE", "SLATE-with-jumping-local","SLATE-with-jumping-global", "SLATE-without-jumping", "REMOTE", "MCLB", "WATERFALL", "WATERFALL2", "SLATE-with-jumping-global-continuous-profiling"]
CAPACITY = 0 # If it is runtime -> training_phase() -> max_capacity_per_service() -> set max_capacity_per_service[svc] = CAPACITY
max_capacity_per_service = dict() # max_capacity_per_service[svc][region] = CAPACITY
hillclimbing_distribution_history = list() #list(dict())
global_hillclimbing_distribution_history = list() #list(dict())
hillclimb_latency_lock = Lock()
prev_hillclimb_latency = dict() # svc -> region -> pod -> {latency_total, num_reqs}
cur_hillclimb_latency = dict()
next_hillclimb_latency = dict()
global_prev_ruleset_overperformance = dict()
global_prev_aggregated_rps = dict()
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
max_num_trace = 0
load_bucket_size = 0

should_we_rollback = True

endpoint_size = {
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
    parsingInboundLatencies = False
    for line in lines:
        if not line:
            continue
        if line == "outbound":
            parsingOutbound = True
            parsingInboundLatencies = False
            continue
        if line == "inboundLatencies":
            parsingInboundLatencies = True
            parsingOutbound = False
            continue
        if line == "inbound":
            parsingOutbound = False
            parsingInboundLatencies = False
            continue
        if parsingOutbound:
            parts = line.split(" ")
            if len(parts) != 5:
                # logger.info(f"hillclimbingLatency for (pod {podname}, svc {svc}): len(parts) != 5, skipping")
                continue
            for i in range(len(parts)):
                parts[i] = parts[i].strip()
            dstSvc, method, path, avgLatency, numReqs = parts[0], parts[1], parts[2], parts[3], parts[4]
            # todo parse these into a separate structure (probably for observability)
        elif parsingInboundLatencies:
            parts = line.split(" ")
            if len(parts) != 3:
                logger.info(f"hillclimbingLatency for (pod {podname}, svc {svc}): len(parts) != 3 for inbound latencies, skipping")
                continue
            for i in range(len(parts)):
                parts[i] = parts[i].strip()
            method, path, latency_list = parts[0], parts[1], parts[2]
            mp = f"{method}@{path}"
            if mp not in global_processing_latencies[svc][region][podname]:
                global_processing_latencies[svc][region][podname][mp] = {
                    "latency_list": latency_list.split(",")
                }
            else:
                if "latency_list" not in global_processing_latencies[svc][region][podname][mp]:
                    global_processing_latencies[svc][region][podname][mp]["latency_list"] = latency_list.split(",")
                else:
                    global_processing_latencies[svc][region][podname][mp]["latency_list"].extend(latency_list.split(","))
        else:
            parts = line.split(" ")
            if len(parts) != 5:
                logger.debug(f"hillclimbingLatency for (pod {podname}, svc {svc}): len(parts) != 5 for inbound, skipping")
                continue
            for i in range(len(parts)):
                parts[i] = parts[i].strip()
            method, path, avgLatency, numReqs, m2 = parts[0], parts[1], float(parts[2]), int(parts[3]), float(parts[4])
            mp = f"{method}@{path}"
            if mp not in global_processing_latencies[svc][region][podname]:
                global_processing_latencies[svc][region][podname][mp] = {
                    "latency_total": float(avgLatency) * int(numReqs),
                    "num_reqs": int(numReqs),
                    "m2": float(m2),
                }
            else:
                # update m2
                cur_num_reqs = global_processing_latencies[svc][region][podname][mp]["num_reqs"]
                mean_delta = float(avgLatency) - global_processing_latencies[svc][region][podname][mp]["latency_total"] / cur_num_reqs
                adjustment = (mean_delta ** 2) * ((numReqs * cur_num_reqs) / (numReqs + cur_num_reqs))
                m2_new = float(global_processing_latencies[svc][region][podname][mp]["m2"]) + float(m2) + adjustment 
                global_processing_latencies[svc][region][podname][mp]["latency_total"] += float(avgLatency) * int(numReqs)
                global_processing_latencies[svc][region][podname][mp]["num_reqs"] += int(numReqs)
                global_processing_latencies[svc][region][podname][mp]["m2"] = m2_new
                
    processing_latencies_mutex.release()
    return ""



def decide_rollback_or_not(svc, method_path):
    global should_we_rollback
    """
    * Problem: We need to apply statistical model not only for each traffic class but also for each unique routing path. For example, a request going through west-frontend and east-backend should not be statiscally modeled together with another request going through west-frontend and west-backend.
    
    input: raw latency(response time) of each endpoint in each region 
    output: True/False for endpoint in each region
    
    A subtle problem is that we are going to use /proxyload endpoint for telemetry pipeline since we need raw latency of individual requests. However, we are going to use it in /hillclimbing endpoint. The currenet function will be executed in perform_jumping routine.
    """
    pass


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

    global global_prev_aggregated_rps
    global jumping_towards_optimizer
    global jumping_ruleset_num_iterations
    global jumping_ruleset_convergence_iterations
    global global_prev_processing_latencies
    global global_processing_latencies
    global processing_latencies_mutex
    global mode
    global temp_counter

    if mode == "profile":
        return
    global should_we_rollback
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

    # jumping is performed between parent_svc and child_svc
    parent_svc = "sslateingress"
    child_svc = "frontend"

    logger.info(f"perform_jumping, jumping_feature_enabled: {jumping_feature_enabled}, jumping_towards_optimizer: {jumping_towards_optimizer}, currently_globally_oscillating: {currently_globally_oscillating}")
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
    prev_processing_latency = calculate_avg_processing_latency(prev_processing_latencies, "sslateingress")
    cur_processing_latency = calculate_avg_processing_latency(cur_processing_latencies, "sslateingress")
    prev_aggregated_rps = global_prev_aggregated_rps.copy()
    cur_aggregated_rps = aggregated_rps.copy()
    global_prev_aggregated_rps = aggregated_rps.copy()
    write_latency("sslateingress", cur_processing_latency[0], cur_processing_latencies)
    if not jumping_feature_enabled:
        return

    if len(cur_last_seen_opt_output) == 0:
        # we haven't seen the optimizer output yet just return
        return
    jumping_ruleset_num_iterations += 1
    logger.info(f"loghill temp_counter {temp_counter} (current ruleset {cur_jumping_ruleset} prev_processing_latency: {prev_processing_latency}, cur_processing_latency: {cur_processing_latency}")

    ruleset_overperformance = calculate_ruleset_overperformance(jumping_df.copy(), cur_processing_latencies, parent_svc=parent_svc, child_svc=child_svc)
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
    
    # if overperformances_are_different(prev_ruleset_overperformance, ruleset_overperformance, maxPctDiff=3) and not jumping_towards_optimizer:
    if processing_latencies_delta_are_different(cur_processing_latencies, prev_processing_latencies, cur_aggregated_rps, prev_aggregated_rps, maxPctDiff=1.5) and not jumping_towards_optimizer:
        # we are oscillating, but the overperformances are different, so we should restart jumping in the disjoint rulesets.
        currently_globally_oscillating = False
        jumping_towards_optimizer = False
        completed_rulesets.clear()
        cur_jumping_ruleset = pick_best_ruleset(ruleset_overperformance, completed_rulesets)
        logger.info(f"loghill detected overperformance change, picked new ruleset: {cur_jumping_ruleset}")
        jumping_ruleset_num_iterations = 0
        # global_prev_processing_latencies.clear()

    if currently_globally_oscillating:
        # we are oscillating and the overperformances are the same, so we should stop jumping.
        logger.info(f"currently globally oscillating, exiting jumping iteration")
        return
    
    if latency_is_oscillating("sslateingress", 5, thresh_ms=3) and jumping_ruleset_num_iterations > jumping_ruleset_convergence_iterations and False:
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
        if cur_jumping_ruleset == ("", "", ""): # no more rulesets to jump to
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
        if len(prev_processing_latencies) > 0:
            jumping_ruleset_num_iterations += 1
            if latency_worsened(prev_processing_latency, cur_processing_latency, threshold_ms=5, alpha=0.05): # gangmuk: statistical model
                # reverse direction
                logger.info(f"latency worsened, loghill reversing direction from {convex_comb_direction} to {-convex_comb_direction}")
                convex_comb_direction = -convex_comb_direction
            elif latency_improved(prev_processing_latency, cur_processing_latency, threshold_ms=1, alpha=0.05):
                # keep going in the same direction
                logger.info(f"latency improved, loghill continuing direction {convex_comb_direction}")
            else:
                # need more data
                logger.info(f"loghill need more data to determine if change worked (cur_convex_comb_value: {cur_convex_comb_value})")
                global_prev_processing_latencies = prev_processing_latencies.copy()
                global_processing_latencies = cur_processing_latencies.copy()
                return
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

        if cur_jumping_ruleset == ("", "", ""):
            cur_jumping_ruleset = pick_best_ruleset(ruleset_overperformance, completed_rulesets)
            logger.info(f"loghill picked new ruleset: {cur_jumping_ruleset}")
        # first adjust jumping_df based on the current and previous latencies (accept the rule from prev_jumping_df to jumping_df)
        # if the latency has improved. if not, roll back to prev_jumping_df. this is where we detect oscillation.
        # todo aditya
        
        should_we_rollback = len(prev_processing_latencies) > 0 and prev_processing_latency < cur_processing_latency and not jumping_df.equals(prev_jumping_df)
        if should_we_rollback: # gangmuk: statistical model
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
            if cur_jumping_ruleset != ("", "", ""):
                rs_overperformance = ruleset_overperformance.get(cur_jumping_ruleset[1], {}).get(cur_jumping_ruleset[2], {}).get(cur_jumping_ruleset[0], {})
                adjusted_df, did_adjust = adjust_ruleset(prev_jumping_df, cur_jumping_ruleset[0], cur_jumping_ruleset[1], cur_jumping_ruleset[2], rs_overperformance, step_size=0.05)
                if not did_adjust:
                    # add this to completed rulesets
                    logger.info(f"loghill ruleset did not adjust, adding ruleset {cur_jumping_ruleset} to completed rulesets")
                    completed_rulesets.add(cur_jumping_ruleset)
                    cur_jumping_ruleset = pick_best_ruleset(ruleset_overperformance, completed_rulesets)
                else:
                    jumping_df = adjusted_df.copy()
            else:
                logger.info(f"failing to adjust ruleset, no ruleset to adjust")
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
            return True

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
    SE = math.sqrt((prev_stddev ** 2) / prev_n + (cur_stddev ** 2) / cur_n)
    
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
    SE = math.sqrt((prev_stddev ** 2) / prev_n + (cur_stddev ** 2) / cur_n)
    
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

def processing_latencies_delta_are_different(
    cur_processing_latencies: dict,
    prev_processing_latencies: dict,
    cur_aggregated_rps: dict,
    prev_aggregated_rps: dict,
    maxPctDiff: float = 0.5  # Represents 50%
) -> bool:
    global bottleneck_service
    """
    Compare the percentage difference between the previous and current latency deltas for the "frontend" service.
    
    Args:
        cur_processing_latencies (dict): Current processing latencies.
        prev_processing_latencies (dict): Previous processing latencies.
        prev_aggregated_rps (dict): Previous aggregated requests per second (region -> service -> endpoint).
        cur_aggregated_rps (dict): Current aggregated requests per second (region -> service -> endpoint).
        maxPctDiff (float, optional): Maximum allowed percentage difference (0 to 1). Defaults to 0.005 (0.5%).
    
    Returns:
        bool: True if any latency delta percentage difference exceeds maxPctDiff, False otherwise.
    """

    if prev_processing_latencies is None or len(prev_processing_latencies) == 0:
        return False
    for region, services in cur_aggregated_rps.items():
        if bottleneck_service not in services:
            continue
        for endpoint, cur_load in services[bottleneck_service].items():
            if region not in prev_aggregated_rps or bottleneck_service not in prev_aggregated_rps[region] or endpoint not in prev_aggregated_rps[region][bottleneck_service]:
                continue
            prev_load = prev_aggregated_rps[region][bottleneck_service][endpoint]
            methodpath = endpoint.split("@")[1] + "@" + endpoint.split("@")[2]
            # Calculate expected latencies based on previous and current load levels
            expected_latency_prev = get_expected_latency_for_rule(prev_load, bottleneck_service, methodpath)
            expected_latency_cur = get_expected_latency_for_rule(cur_load, bottleneck_service, methodpath)
            
            # Skip comparison if expected latencies are zero to avoid division by zero
            if expected_latency_prev == 0 or expected_latency_cur == 0:
                logger.debug(
                    f"Skipping comparison for Region: {region}, Service: {bottleneck_service}, Endpoint: {endpoint} "
                    f"due to zero expected latency."
                )
                continue

            # Retrieve actual latencies; default to 0 if not present
            # methodpath is just method@path, e.g., GET@/cart/checkout, get it from endpoint which is of form svc@method@path
            actual_prev, _, _ = calculate_avg_processing_latency_for_traffic_class(
                prev_processing_latencies, endpoint, region
            )
            actual_cur, _, _ = calculate_avg_processing_latency_for_traffic_class(
                cur_processing_latencies, endpoint, region
            )

            # Calculate the deltas
            delta_prev = abs(expected_latency_prev - actual_prev)
            delta_cur = abs(expected_latency_cur - actual_cur)

            if True:
                # check if within 30ms
                if abs(delta_prev - delta_cur) > 30:
                    logger.info(
                        f"Latency delta difference exceeded: {abs(delta_prev - delta_cur)}ms > 30ms (abs({delta_prev} - {delta_cur})) "
                    f"for Region: {region}, Service: {bottleneck_service}, Endpoint: {endpoint}"
                    )
                    return True
            else:
                # Calculate the percentage difference between the two deltas
                if delta_prev == 0:
                    if delta_cur != 0:
                        # Previous delta was zero, current delta is non-zero: infinite percentage change
                        pct_diff = float('inf')
                    else:
                        # Both deltas are zero: no change
                        pct_diff = 0
                else:
                    pct_diff = abs(delta_cur - delta_prev) / delta_prev  # Fraction between 0 and inf

                # Debug logs (optional)
                logger.info(
                    f"Region: {region}, Service: frontend, Endpoint: {endpoint}, "
                    f"Expected Latency Prev: {expected_latency_prev}ms ({prev_load} rps), Expected Latency Cur: {expected_latency_cur}ms ({cur_load} rps), "
                    f"Prev Actual Latency: {actual_prev}ms, Cur Actual Latency: {actual_cur}ms, "
                    f"Delta Prev: {delta_prev}ms, Delta Cur: {delta_cur}ms, Pct Diff: {pct_diff:.4f}"
                )

                if pct_diff > maxPctDiff:
                    if pct_diff == float('inf'):
                        logger.debug(
                            f"Latency delta difference exceeded: Infinite > {maxPctDiff*100}% "
                            f"for Region: {region}, Service: frontend, Endpoint: {endpoint}"
                        )
                    else:
                        logger.info(
                            f"Latency delta difference exceeded: {pct_diff*100:.2f}% > {maxPctDiff*100}% "
                            f"for Region: {region}, Service: frontend, Endpoint: {endpoint}"
                        )
                    return True
                else:
                    logger.debug(
                        f"Latency delta difference within threshold: {pct_diff*100:.2f}% <= {maxPctDiff*100}% "
                        f"for Region: {region}, Service: frontend, Endpoint: {endpoint}"
                    )
    return False






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


def compute_traffic_matrix(df, src_service="sslateingress", dst_service=""):
    global bottleneck_service
    if dst_service == "":
        dst_service = bottleneck_service
    """
    Computes the traffic matrix for the specified source and destination services.

    Args:
        df (pd.DataFrame): Input DataFrame containing traffic data.
        src_service (str): Source service name to filter.
        dst_service (str): Destination service name to filter.

    Returns:
        pd.DataFrame: Pivot table representing the traffic matrix.
    """
    # Ensure necessary columns are present
    required_columns = {'src_svc', 'dst_svc', 'dst_cid', 'dst_endpoint', 'weight', 'src_cid'}
    if not required_columns.issubset(df.columns):
        raise ValueError(f"DataFrame must contain the following columns: {required_columns}, but has columns: {df.columns}")

    # Filter the DataFrame for the specified source and destination services
    filtered = df[
        (df['src_svc'] == src_service) & 
        (df['dst_svc'] == dst_service)
    ]

    # Create a MultiIndex for the columns using dst_cid and dst_endpoint
    traffic_matrix = filtered.pivot_table(
        index=['src_cid', 'src_endpoint'],    
        columns=['dst_cid', 'dst_endpoint'],
        values='weight',
        aggfunc='sum',
        fill_value=0
    )

    return traffic_matrix

def jump_towards_optimizer_desired(starting_df: pd.DataFrame, desired_df: pd.DataFrame,
                                   cur_convex_comb_value: float, src_service="sslateingress", dst_service="") -> pd.DataFrame:
    """
    Computes the convex combination of two traffic matrices based on the given combination value.

    Args:
        starting_df (pd.DataFrame): The starting traffic matrix DataFrame.
        desired_df (pd.DataFrame): The desired traffic matrix DataFrame.
        src_service (str): Source service name to filter.
        dst_service (str): Destination service name to filter.
        cur_convex_comb_value (float): The convex combination factor (between 0 and 1).

    Returns:
        pd.DataFrame: The new traffic matrix as a DataFrame in the same format as the inputs.
    """
    global bottleneck_service
    dst_service = bottleneck_service
    # Validate cur_convex_comb_value
    if not (0 <= cur_convex_comb_value <= 1):
        raise ValueError("cur_convex_comb_value must be between 0 and 1.")

    required_columns = {'src_svc', 'dst_svc'}
    for df_name, df in zip(['starting_df', 'desired_df'], [starting_df, desired_df]):
        if not required_columns.issubset(df.columns):
            raise ValueError(f"{df_name} must contain columns: {required_columns} (has columns: {df.columns})")

    # Compute traffic matrices for starting and desired DataFrames
    starting_matrix = compute_traffic_matrix(starting_df, src_service=src_service, dst_service=dst_service)
    desired_matrix = compute_traffic_matrix(desired_df, src_service=src_service, dst_service=dst_service)
    
    # Identify all unique (src_cid, src_endpoint) and (dst_cid, dst_endpoint) across both matrices
    all_src = starting_matrix.index.union(desired_matrix.index)
    all_dst = starting_matrix.columns.union(desired_matrix.columns)
    
    # Reindex both matrices to include all sources and destinations
    starting_matrix = starting_matrix.reindex(index=all_src, columns=all_dst, fill_value=0)
    desired_matrix = desired_matrix.reindex(index=all_src, columns=all_dst, fill_value=0)
    
    # Compute the convex combination
    combined_matrix = (1 - cur_convex_comb_value) * starting_matrix + cur_convex_comb_value * desired_matrix
    combined_matrix = combined_matrix.round(6)
    logger.info(f"Combined traffic matrix:\n{combined_matrix}\nStarting matrix:\n{starting_matrix}\nDesired matrix:\n{desired_matrix}")
    
    # Transform the combined matrix back into a DataFrame
    combined_df = combined_matrix.reset_index().melt(id_vars=['src_cid', 'src_endpoint'], 
                                                   var_name=['dst_cid', 'dst_endpoint'], 
                                                   value_name='weight')
    combined_df = combined_df[combined_df['weight'] > 0].reset_index(drop=True)
    
    # Merge with starting_df and desired_df to get 'total' and 'flow' information
    # **Important Correction**: Include 'src_endpoint' and 'dst_endpoint' in the merge keys
    starting_totals = starting_df[
        (starting_df['src_svc'] == src_service) & 
        (starting_df['dst_svc'] == dst_service)
    ][['src_cid', 'src_endpoint', 'dst_cid', 'dst_endpoint', 'total']].drop_duplicates()
    
    desired_totals = desired_df[
        (desired_df['src_svc'] == src_service) & 
        (desired_df['dst_svc'] == dst_service)
    ][['src_cid', 'src_endpoint', 'dst_cid', 'dst_endpoint', 'total']].drop_duplicates()
    
    # Merge combined_df with starting_totals
    combined_df = combined_df.merge(
        starting_totals,
        on=['src_cid', 'src_endpoint', 'dst_cid', 'dst_endpoint'],
        how='left',
        suffixes=('', '_start')
    )
    
    # Merge combined_df with desired_totals
    combined_df = combined_df.merge(
        desired_totals,
        on=['src_cid', 'src_endpoint', 'dst_cid', 'dst_endpoint'],
        how='left',
        suffixes=('', '_desired')
    )
    
    # Fill 'total' from starting_df; if missing, use desired_df's 'total'; else set to 1 to avoid division by zero
    combined_df['total'] = combined_df['total'].fillna(combined_df['total_desired']).fillna(1)
    
    # Compute 'flow' as weight * total
    combined_df['flow'] = combined_df['weight'] * combined_df['total']
    
    # Add 'src_svc' and 'dst_svc' columns
    combined_df['src_svc'] = src_service
    combined_df['dst_svc'] = dst_service
    
    # Optional: Enforce weight limits if necessary
    # Here, we clip weights to ensure they stay within [0, 1]
    combined_df['weight'] = combined_df['weight'].clip(lower=0, upper=1.0)
    
    # Reorder and select columns to match the original format
    final_df = combined_df[
        ['src_svc', 'dst_svc', 'src_endpoint', 'dst_endpoint',
         'src_cid', 'dst_cid', 'flow', 'total', 'weight']
    ]
    
    # Sort and reset index
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

def pick_best_ruleset(overperformance: dict, exclude_rulesets: set) -> tuple[str, str, str]:
    """
    pick_best_ruleset will pick the best ruleset based on the max variance in overperformance of each ruleset.
    It will return the best ruleset which is not in the exclude_rulesets set.
    It expects overperformance to be a dictionary of src traffic class -> dst traffic class -> source region -> destination region -> overperformance.
    returns a tuple of (source region, src traffic class, dst traffic class).
    returns an empty string if no ruleset is found.
    """
    best_ruleset = ("", "", "")
    max_variance = float('-inf')
    for src_traffic_class, dst_traffic_classes in overperformance.items():
        for dst_traffic_class, source_regions in dst_traffic_classes.items():
            for source_region, destinations in source_regions.items():
                if (source_region, src_traffic_class, dst_traffic_class) in exclude_rulesets:
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
                    best_ruleset = (source_region, src_traffic_class, dst_traffic_class)

    return best_ruleset


def calculate_avg_processing_latency_for_traffic_class(
    latencies: dict, traffic_class: str, region=""
) -> tuple[float, int, float]:
    """
    Calculates the average processing latency and combines m2 values across all pods and regions
    for a given traffic class. Returns a tuple of (average_latency, total_num_reqs, combined_m2).
    """
    svc = traffic_class.split("@")[0]
    methodpath = traffic_class.split("@")[1] + "@" + traffic_class.split("@")[2]
    
    total_num_reqs = 0
    combined_mean = 0.0
    combined_m2 = 0.0

    if svc not in latencies:
        return 0.0, 0, 0.0
    if region and region not in latencies[svc]:
        return 0.0, 0, 0.0

    # Determine which regions to iterate over
    regions_to_iterate = [region] if region else latencies[svc].keys()

    for reg in regions_to_iterate:
        for pod in latencies[svc][reg]:
            if methodpath not in latencies[svc][reg][pod]:
                continue
            pod_data = latencies[svc][reg][pod][methodpath]
            batch_latency_total = pod_data["latency_total"]
            batch_num_reqs = pod_data["num_reqs"]
            batch_m2 = pod_data["m2"]

            # Ensure there are requests to process
            if batch_num_reqs == 0:
                continue

            batch_mean = batch_latency_total / batch_num_reqs

            if total_num_reqs == 0:
                # Initialize with the first batch
                combined_mean = batch_mean
                combined_m2 = batch_m2
                total_num_reqs = batch_num_reqs
            else:
                # Compute delta between batch mean and combined mean
                delta = batch_mean - combined_mean
                total_n = total_num_reqs + batch_num_reqs

                # Update combined mean
                combined_mean_new = (combined_mean * total_num_reqs + batch_mean * batch_num_reqs) / total_n

                # Compute adjustment for m2
                adjustment = (delta ** 2) * (total_num_reqs * batch_num_reqs) / total_n

                # Update combined m2
                combined_m2_new = combined_m2 + batch_m2 + adjustment

                # Update combined statistics
                combined_mean = combined_mean_new
                combined_m2 = combined_m2_new
                total_num_reqs = total_n

    if total_num_reqs == 0:
        return 0.0, 0, 0.0

    return combined_mean, total_num_reqs, combined_m2

def calculate_avg_processing_latency(latencies: dict, svc: str, region="") -> tuple[float, int, float]:
    """
    Calculates the average processing latency, total number of requests, and combined stddev
    (sum of squared deviations from the mean) across all pods and regions for a given service.

    :param latencies: Nested dictionary containing latency data.
    :param svc: Service name to calculate latency for.
    :param region: Specific region to filter by. If empty, all regions are included.
    :return: A tuple containing (average_latency, total_num_reqs, combined_m2).
    """
    # Extract all unique method@path for the specified service
    method_paths = set()
    if svc in latencies:
        regions_to_iterate = [region] if region else latencies[svc].keys()
        for reg in regions_to_iterate:
            if reg not in latencies[svc]:
                continue
            for pod in latencies[svc][reg]:
                for mp in latencies[svc][reg][pod].keys():
                    method_paths.add(mp)
    else:
        # Service not found
        return 0.0, 0, 0.0

    combined_mean = 0.0
    combined_num_reqs = 0
    combined_m2 = 0.0

    for methodpath in method_paths:
        # Construct the traffic_class as "svc@method@path"
        traffic_class = f"{svc}@{methodpath}"
        
        # Retrieve the combined statistics for this traffic_class
        # Assuming calculate_avg_processing_latency_for_traffic_class returns (mean, num_reqs, m2)
        mean, num_reqs, m2 = calculate_avg_processing_latency_for_traffic_class(latencies, traffic_class, region)
        
        if num_reqs == 0:
            continue  # Skip if there are no requests for this traffic class
        
        if combined_num_reqs == 0:
            # Initialize with the first traffic class's statistics
            combined_mean = mean
            combined_num_reqs = num_reqs
            combined_m2 = m2
        else:
            # Compute the delta between the new mean and the current combined mean
            delta = mean - combined_mean
            
            # Update the combined mean using a weighted average
            total_n = combined_num_reqs + num_reqs
            combined_mean = (combined_mean * combined_num_reqs + mean * num_reqs) / total_n
            
            # Compute the adjustment for M2
            adjustment = (delta ** 2) * (combined_num_reqs * num_reqs) / total_n
            
            # Update the combined M2
            combined_m2 += m2 + adjustment
            
            # Update the total number of requests
            combined_num_reqs = total_n

    if combined_num_reqs == 0:
        # No requests found across all traffic classes
        return 0.0, 0, 0.0

    stddev = math.sqrt(combined_m2 / combined_num_reqs)

    return combined_mean, combined_num_reqs, stddev

def calculate_ruleset_overperformance(rules: pd.DataFrame, cur_latencies: dict, parent_svc: str, child_svc: str) -> dict:
    """
    calculate_ruleset_overperformance will calculate the overperformance of all rulesets based on the current vs expected latencies.
    the only rulesets considered are between sslateingress and frontend, but for all traffic classes.
    ruleset is defined as every set of rules (across traffic classes) originating from a source region to more than one destination region.
    it calculates overperfomance as (expected latency - actual latency) * requests affected.

    it returns a dictionary of destination region to overperformance. (src traffic class -> dst traffic class (svc@method@path) -> source region -> destination region -> overperformance)
    example:
    {
        "sslateingress@POST@/cart/checkout": {
            "frontend@POST@/cart/checkout": {
                "us-west-1": {
                    "us-west-1": 37,
                    "us-east-1": 12,
                    "us-central-1": 0,
                    "us-south-1": -59   
                }
            }
        }
    }
    It needs access to the processing latencies, the current load conditions, and the processing latency function for frontend.
    """
    global aggregated_rps
    global normalization_dict
    global bottleneck_service
    # first filter src_svc being sslateingress and dst_svc being frontend
    # then, for each of these entries, get the source regions that have more than one destination region
    # for each of these source regions, calculate the overperformance of the ruleset.
    # return the overperformance as a dictionary of destination region to overperformance.

    # todo aditya problem: latency is not being injected right...
    logger.info(f"calculate_ruleset_overperformance: rules:\n{rules.columns}")
    if "src_svc" not in rules.columns or "dst_svc" not in rules.columns or "src_cid" not in rules.columns or "dst_cid" not in rules.columns:
        return dict()
    filtered_rules = rules[(rules["src_svc"] == parent_svc) & (rules["dst_svc"] == child_svc)]
    dst_traffic_classes = filtered_rules["dst_endpoint"].unique()
    logger.info(f"calculate_ruleset_overperformance: traffic_classes: {dst_traffic_classes}")
    overperformance = dict()

    # ruleset: rules for a given traffic class from a source region to multiple destination regions.
    for dst_traffic_class in dst_traffic_classes:
        src_regions = filtered_rules[filtered_rules["dst_endpoint"] == dst_traffic_class]["src_cid"].unique()
        logger.info(f"calculate_ruleset_overperformance: traffic_class: {dst_traffic_class}, src_regions: {src_regions}")
        for src_region in src_regions:
            src_rules = filtered_rules[(filtered_rules["src_cid"] == src_region) & (filtered_rules["dst_endpoint"] == dst_traffic_class)]
            dst_regions = src_rules["dst_cid"].unique()
            if len(dst_regions) < 2:
                continue
            else:
                logger.info(f"calculate_ruleset_overperformance: src_region: {src_region}, dst_regions: {dst_regions}")
            overperformance[src_region] = dict()
            for dst_region in dst_regions:
                # src_traffic_class is src_endpoint
                src_traffic_class = src_rules[src_rules["dst_cid"] == dst_region]["src_endpoint"].values[0]
                # calculate the overperformance for this rule
                # get the expected latency based on the current load conditions
                # get the actual latency from cur_latencies
                # calculate the overperformance as (expected - actual) * requests
                # requests is the total requests for a certain traffic class at a service in a region.

                actual_latency_in_dst_region , _, m2 = calculate_avg_processing_latency_for_traffic_class(cur_latencies, dst_traffic_class, region=dst_region)
                expected_latency_in_dst_region = get_expected_latency_for_traffic_class(dst_region, bottleneck_service, dst_traffic_class)

                total_load_in_src_region = aggregated_rps.get(src_region, {}).get(parent_of_bottleneck_service, {}).get(src_traffic_class, 0)
                ruleset_rps_in_dst_region = total_load_in_src_region * src_rules[src_rules["dst_cid"] == dst_region]["weight"].values[0]
                if src_traffic_class not in overperformance:
                    overperformance[src_traffic_class] = dict()
                if dst_traffic_class not in overperformance[src_traffic_class]:
                    overperformance[src_traffic_class][dst_traffic_class] = dict()
                if src_region not in overperformance[src_traffic_class][dst_traffic_class]:
                    overperformance[src_traffic_class][dst_traffic_class][src_region] = dict()
                # overperformance[dst_traffic_class][src_region][dst_region] = (expected_latency_in_dst_region - actual_latency_in_dst_region) * ruleset_rps_in_dst_region
                overperformance[src_traffic_class][dst_traffic_class][src_region][dst_region] = (expected_latency_in_dst_region - actual_latency_in_dst_region) * ruleset_rps_in_dst_region

                total_load_in_dst_region = aggregated_rps.get(dst_region, {}).get(bottleneck_service, {}).get(dst_traffic_class, 0)
                logger.info(f"loghill calculate_ruleset_overperformance: src_region: {src_region}, src traffic class {src_traffic_class}, dst traffic class {dst_traffic_class}, dst_region: {dst_region}, expected_latency ({total_load_in_dst_region} rps): {expected_latency_in_dst_region}, actual_latency: {actual_latency_in_dst_region}, load in {dst_region} for this ruleset: {ruleset_rps_in_dst_region}, pct of ruleset: {src_rules[src_rules['dst_cid'] == dst_region]['weight'].values[0]}")
    return overperformance

def get_expected_latency_for_traffic_class(region: str, svc: str, traffic_class: str) -> int:
    """
    get_expected_latency_for_traffic_class will return the expected latency for a given traffic class based on the current load (in all traffic classes).
    The expected latency of a traffic class (given the current load of every traffic class) is the weighted, normalized sum of the expected latencies of every traffic class.
    For example, with two traffic classes M and S, the expected total average latency is (given m rps of M and s rps of S):
    L(m, s) = (m * L_m(m + s/n) + s * L_s(nm + s)) / (m + s)
    The expected average latency of the M type is:
    L_m(m, s) = L_m(m + s/n)
    The expected average latency of the S type is:
    L_s(m, s) = L_m(nm + s)
    """
    global aggregated_rps # dict of region -> svcname -> endpoint -> rps
    global normalization_dict # src endpoint -> dst endpoint -> normalization factor
    global bottleneck_service
    normalized_load = aggregated_rps.get(region, {}).get(svc, {}).get(traffic_class, 0)
    for dst_endpoint in normalization_dict.get(traffic_class, {}):
        normalized_load += aggregated_rps.get(region, {}).get(svc, {}).get(dst_endpoint, 0) * normalization_dict[traffic_class][dst_endpoint]
    svc = traffic_class.split("@")[0]
    methodpath = traffic_class.split("@")[1] + "@" + traffic_class.split("@")[2]
    return get_expected_latency_for_rule(normalized_load, svc, methodpath)


def adjust_ruleset(ruleset: pd.DataFrame, region: str, src_traffic_class: str, dst_traffic_class: str, overperformance: dict, step_size=0.05) -> tuple[pd.DataFrame, bool]:
    """
    adjust_ruleset will adjust the (source region, traffic_class) ruleset based on the overperformance of the ruleset.
    overperformance is expected to be in the form of a dictionary of destination region to overperformance.
    it will find the average performance in the source region, partition the destination regions into underperformers and overperformers,
    and adjust the ruleset accordingly. second parameter is a boolean indicating if the ruleset was adjusted.
    """
    global bottleneck_service
    # first, get the average performance of the ruleset in the source region
    # then, partition the destination regions into underperformers and overperformers
    # adjust the ruleset based on the overperformance of the ruleset.
    # return the adjusted ruleset.
    if len(overperformance) == 0:
        logger.debug(f"loghill no overperformance for ruleset [{region}]")
        return ruleset, False
    
    # get the destination regions, and the average performance of the ruleset (for those destination regions)
    src_svc, dst_svc, src_endpoint, dst_endpoint = src_traffic_class.split("@")[0], dst_traffic_class.split("@")[0], src_traffic_class, dst_traffic_class
    dst_cids = list(overperformance.keys())
    avg_performance = sum([overperformance[dst_cid] for dst_cid in dst_cids]) / len(dst_cids)
    # partition the destination regions into underperformers and overperformers
    underperformers = [dst_cid for dst_cid in dst_cids if overperformance[dst_cid] < avg_performance]
    overperformers = [dst_cid for dst_cid in dst_cids if overperformance[dst_cid] >= avg_performance]
    logger.info(f"loghill for ruleset [{region}, {src_traffic_class}, {dst_traffic_class}] underperformers: {underperformers}, overperformers: {overperformers}")

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
        if len(adjusted_ruleset.loc[mask]) == 0:
            logger.info(f"loghill underperformer: {dst_cid}, no rule found (mask: {mask}, ruleset: \n{adjusted_ruleset})")
            continue
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
        if len(adjusted_ruleset.loc[mask]) == 0:
            logger.info(f"loghill overperformer: {dst_cid}, no rule found (mask: {mask}, ruleset: \n{adjusted_ruleset})")
            continue
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
    logger.info(f"loghill (on {region} {src_traffic_class} {dst_traffic_class})\
                \nold ruleset: {compute_traffic_matrix(ruleset, src_service=src_svc, dst_service=dst_svc)}\nadjusted ruleset: {compute_traffic_matrix(adjusted_ruleset, src_service=src_svc, dst_service=dst_svc)}")
    return adjusted_ruleset if not out_of_bounds else ruleset, not out_of_bounds


def get_expected_latency_for_rule(load: int, svc: str, methodpath: str) -> int:
    """
    get_expected_latency_for_rule will calculate the expected e2e latency for a given rule based on the current load conditions.
    """
    global e2e_coef_dict
    ep = svc + "@" + methodpath
    if svc not in e2e_coef_dict["us-west-1"]:
        logger.info(f"get_expected_latency_for_rule: svc {svc} not found in e2e_coef_dict ({e2e_coef_dict['us-west-1'].keys()})")
        return -1
    if ep not in e2e_coef_dict["us-west-1"][svc]:
        logger.info(f"get_expected_latency_for_rule: ep {ep} not found in e2e_coef_dict ({e2e_coef_dict['us-west-1'][svc].keys()})")
        return -1
    a = e2e_coef_dict["us-west-1"][svc][ep][ep]
    c = e2e_coef_dict["us-west-1"][svc][ep]["intercept"]
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
            f.write(f"{temp_counter},{region},{calculate_avg_processing_latency(latency_dict, svc, region)[0]}\n")
            for tc in ["POST@/cart", "POST@/cart/checkout"]:
                l, _, m2 = calculate_avg_processing_latency_for_traffic_class(latency_dict, f"{svc}@{tc}", region)
                f.write(f"{temp_counter},{region},{tc},{l}\n")
    if svc not in historical_svc_latencies:
        historical_svc_latencies[svc] = list()
    historical_svc_latencies[svc].append(avg_processing_latency)

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
        logger.debug(f"logadi all headers: {request.headers}")
        logger.debug(f"hillclimbing svc: {svc}, region: {region}, podname: {podname}, old_dist: {old_dist}, new_dist: {new_dist}, avg_latency: {avg_latency}, inbound_rps: {inbound_rps}, outbound_rps: {outbound_rps}")
    
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
        'region': region,
        "podname": podname,
        "avg_latency": avg_latency,
        "inbound_rps": inbound_rps,
        "outbound_rps": outbound_rps,
        'time': str(datetime.datetime.now()),
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
        'time': str(datetime.datetime.now()),
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
    for region in all_endpoints:
        for svc_name in all_endpoints[region]:
            for ep in all_endpoints[region][svc_name]:
                if ep not in endpoint_to_placement:
                    endpoint_to_placement[ep] = set()
                endpoint_to_placement[ep].add(region)
    return endpoint_to_placement

def get_svc_to_placement(all_endpoints):
    temp = dict()
    for region in all_endpoints:
        for svc_name in all_endpoints[region]:
            if svc_name not in temp:
                temp[svc_name] = set()
            temp[svc_name].add(region)
    return temp

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
    global svc_to_placement
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
                    try:
                        dst_cid_list = svc_to_placement[dst_svc] # west only
                    except Exception as e:
                        logger.error(e)
                        logger.error(f"ERROR: svc_to_placement does not have {dst_svc}")
                        logger.error(f"svc_to_placement: {svc_to_placement}")
                        assert False
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



def parse_stats_into_spans(body, given_svc_name, given_region, podname):
    lines = body.split("\n")
    # requestStats = lines[3:]
    # requestStats = lines[2:]
    
    spans = []
    response_time_filtering = 0
    path_filtering = 0
    rps_filtering = 0
    if given_svc_name == "productcatalogservice":
        return []
    for line in lines:
        if line[:3] != "us-":
            logger.debug(f"Skip this span. line[:3] != 'us-', line: {line}")
            continue
    # for span_stat in requestStats:
        # span_stat: "us-west-1 metrics-fake-ingress-us-west-1 GET /start 70904b1c08f35622387a6bb5c9141596 387a6bb5c9141596  1709763447436 1709763447540 0 GET@/start,0,18446744073709530962|"
        # ss = ["us-west-1", "metrics-fake-ingress-us-west-1", "GET", "/start", "70904b1c08f35622387a6bb5c9141596", "387a6bb5c9141596", "1709763447436", "1709763447540", "0", "GET@/start,0,18446744073709530962|"]
        ss = line.split(" ")
        # if len(ss) != 11:
        #     logger.debug(f"ERROR, len(ss) != 11, (len(ss):{len(ss)}, ss:{ss})")
        #     continue
        region = ss[0]
        serviceName = ss[1]
        if serviceName.find("-us-") != -1:
            serviceName = serviceName.split("-us-")[0]
        assert given_svc_name == serviceName
        method = ss[2]
        path = ss[3]
        endpoint = f"{serviceName}@{method}@{path}"
        traceId = ss[4]
        spanId = ss[5]
        parentSpanId = ss[6]
        startTime = int(ss[7])
        endTime = int(ss[8])
        bodySize = int(ss[9])
        responseTime = endTime - startTime
        if responseTime < 0: # filtering condition 3 (negative response time)
            logger.error(f"Skip this span: non-positive response time {responseTime}")
            response_time_filtering += 1
            continue
        if "/hipstershop.CurrencyService/Convert" in path or "/hipstershop.ProductCatalogService/GetProduct" in path: # filtering condition 4 (specific path in onlineboutique app)
            logger.error(f"Skip this span: excluding some path(url): {path}")
            path_filtering += 1
            continue
        endpointInflightStats = ss[10].split("|")
        if endpointInflightStats[-1] == "":
            endpointInflightStats = endpointInflightStats[:-1]
        rps_dict = dict()
        inflight_dict = dict()
        negative_rps_flag = False
        wrong_endpointInflightStats = False
        for ep_load in endpointInflightStats:
            ep_load_method_and_path = ep_load.split(",")[0]
            ep_load_method = ep_load_method_and_path.split("@")[0]
            if len(ep_load_method_and_path.split("@")) != 2:
                # logger.error(f"ep_load_method_and_path.split('@')) != 2, {ep_load_method_and_path}")
                # logger.error(f"body: {body}")
                # assert False
                wrong_endpointInflightStats = True
                continue
            ep_load_path = ep_load_method_and_path.split("@")[1]
            ep_load_endpoint = f"{serviceName}@{ep_load_method}@{ep_load_path}"
            
            if "hipstershop.CurrencyService/Convert" in ep_load_method_and_path or "/hipstershop.ProductCatalogService/GetProduct" in ep_load_method_and_path:
                """ This is critical. ProductCatalogService receives two different endpoints. One is GetProduct, the other is ListProducts. And GetProduct endpoint receives more than 1:1 ratio of incoming requests. We will ignore GetProduct for now. Same for CurrencyService/Convert endpoint. """
                logger.error(f"Excluding {ep_load} in rps_dict")
                continue
            # endpoint = sp.Endpoint(svc_name=serviceName, method=method, url=path)
            rps_of_this_pod = int(ep_load.split(",")[1])
            try:
                num_pod_of_this_region = len(per_pod_ep_rps[region][serviceName][endpoint])
            except Exception as e:
                logger.error(e)
                logger.error(f"ERROR: per_pod_ep_rps does not have {region}, {serviceName}, {endpoint}")
                logger.error(f"per_pod_ep_rps: {per_pod_ep_rps}")
                assert False
            rps_of_all_pods = rps_of_this_pod*num_pod_of_this_region # NOTE: This is assuming the homogeneous nodes in each region and perfect roundrobin load balancing
            if rps_of_all_pods <= 0:
                logger.info(f"Skip this span: rps_of_all_pods is non-positive {rps_of_all_pods}") # filtering condition 5 (negative rps)
                negative_rps_flag = True
                rps_filtering += 1
                continue
            inflight = int(ep_load.split(",")[2])
            rps_dict[ep_load_endpoint] = rps_of_all_pods
            inflight_dict[ep_load_endpoint] = inflight
        if len(rps_dict) != 1:
            logger.info(f"Skip this span: len(rps_dict) != 1, {rps_dict}")
            continue
        if wrong_endpointInflightStats:
            logger.debug(f"Skip this span: wrong_endpointInflightStats")
            continue
        if negative_rps_flag:
            continue
        load_bucket = max(1, (rps_of_all_pods // load_bucket_size + 1))
        logger.debug(f"num_pod({region}, {serviceName}): {num_pod_of_this_region}, rps_of_all_pods: {rps_of_all_pods}, load_bucket:{load_bucket}")
        assert rps_of_all_pods > 0
        temp_span = sp.Span(method, path, serviceName, region, \
            traceId, spanId, parentSpanId, \
            startTime, endTime, bodySize, \
            rps_dict=rps_dict, \
            num_inflight_dict=inflight_dict, \
            reported_time=time.time(), \
            rps=rps_of_all_pods, \
            load_bucket=load_bucket) # 0-49: 0 50-149: 1, 150-249: 2, 250-349: 3, ...
        spans.append(temp_span)
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
            logger.error(f"row: \n{row}")
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


def add_span_to_traces(given_traces, span):
    region, load_bucket, trace_id = span.cluster_id, span.load_bucket, span.trace_id
    region_traces = given_traces.setdefault(region, {})
    bucket_traces = region_traces.setdefault(load_bucket, {})
    trace_data = bucket_traces.setdefault(trace_id, {"span": [], "time": []})
    if len(span.rps_dict) == 1:
        trace_data["span"].append(span)
        trace_data["time"].append(0)  # Consider replacing 0 with a relevant timestamp, if needed.
        # trace_data["time"].append(time.time())  # Uncomment if real timestamps are required
    else:
        logger.error(
            f"Skipping span: requires exactly one endpoint but has {len(span.rps_dict)}"
        )


def get_trace_lock(region, load_bucket, trace_id):
    global trace_locks
    """Get or create a lock for a specific trace."""
    key = (region, load_bucket, trace_id)
    if key not in trace_locks:
        trace_locks[key] = Lock()
    return trace_locks[key]

def get_num_trace(given_traces, region):
    num_trace = 0
    for load_bucket in given_traces[region]:
        num_trace += len(given_traces[region][load_bucket])
    return num_trace

@app.post('/proxyLoad') # from wasm
def handleProxyLoad():
    global aggregated_rps
    global percentage_df
    global jumping_df
    global ROUTING_RULE
    global mode
    global list_of_body
    global stats_mutex
    # global endpoint_level_rps_mutex
    global per_pod_ep_rps_mutex
    global per_pod_ep_rps
    global use_optimizer_output
    global temp_counter
    global jumping_feature_enabled
    global jumping_last_seen_opt_output
    global jumping_ruleset_num_iterations
    global currently_globally_oscillating
    global global_prev_processing_latencies
    
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
    if svc.find("-us-") != -1:
            svc = svc.split("-us-")[0]
    if svc == "slate-controller" or svc == "consul": # filtering condition 1 (service name)
        logger.debug(f"WARNING: skip {svc} in handleproxy")
        return ""
    if region == "SLATE_UNKNOWN_REGION": # filtering condition 2 (region name)
        logger.debug(f"skip {region}, svc: {svc}, region: {region}")
        return "your region is SLATE_UNKNOWN_REGION. It is wrong"
    if region not in inter_cluster_latency: # filtering condition 2 (region name)
        logger.debug(f"Ignore the request from {region} since there is no inter_cluster_latency info for {region}")
        return ""
    if svc == "productcatalogservice" or svc == "currencyservice": # filtering condition 6 (service name)
        logger.debug(f"skip {svc}, region: {region}")
        return ""
    body = request.get_data().decode('utf-8')
    lines = body.split("\n")
    svc_level_rps = int(lines[0])
    inflightStats = lines[1]
    if "sslateingress" in svc:
        logger.debug(f"inflightStats: {inflightStats}")
    if region not in service_level_rps:
        service_level_rps[region] = dict()
    service_level_rps[region][svc] = svc_level_rps
    active_endpoint_stats = inflightStats.split("|")[:-1] # ["POST@/cart/checkout,28,0"]
    if inflightStats == "":
        if region in per_pod_ep_rps:
            if svc in per_pod_ep_rps[region]:
                for ep in per_pod_ep_rps[region][svc]:
                    if podname in per_pod_ep_rps[region][svc][ep]:
                        per_pod_ep_rps[region][svc][ep][podname] = 0
                        
    for endpoint_stat in active_endpoint_stats: # ["POST@/cart/checkout,28,0"]
        # "POST@/cart/checkout,28,0"
        method = endpoint_stat.split(",")[0].split("@")[0] # POST
        path = endpoint_stat.split(",")[0].split("@")[1] # /cart/checkout
        active_ep_ontick_rps = int(endpoint_stat.split(",")[1]) # 28
        endpoint = svc + cfg.ep_del + method + cfg.ep_del + path # frontend@POST@/cart/checkout"        
        if region not in aggregated_rps:
            aggregated_rps[region] = dict()
        if svc not in aggregated_rps[region]:
            aggregated_rps[region][svc] = dict()
        if region not in per_pod_ep_rps:
            per_pod_ep_rps[region] = dict()
        if svc not in per_pod_ep_rps[region]:
            per_pod_ep_rps[region][svc] = dict()
        if endpoint not in per_pod_ep_rps[region][svc]:
            per_pod_ep_rps[region][svc][endpoint] = dict()
        per_pod_ep_rps[region][svc][endpoint][podname] = active_ep_ontick_rps
        logger.debug(f"per_pod_ep_rps, {region}, {svc}, {endpoint}, {podname}, {active_ep_ontick_rps}")
                    
            # with per_pod_ep_rps_mutex:
            # if endpoint in endpoint_to_placement: # BUG: endpoint_to_placement will be updated only after the initialize_global_datastructure. So, endpoint will not be initialized if we use this if condition before the initialize_global_datastructure. Hence, I commented it. But how did it work before!?
            # else:
            #     logger.info(f"ERROR: Skip per_pod_ep_rps, {endpoint}. this endpoint is not in stitched trace.")
    
    if svc_level_rps > 0:
        if ROUTING_RULE == "SLATE-with-jumping-global-continuous-profiling":
            with list_of_body_mutex: # option 4
                # with open("body.csv", "a") as f: # to avoid duplicated traces
                #     f.write(body)
                ## option 2
                list_of_body.append(body) 
        
    if mode == "profile":
        """
        At this point, spans should at least pass all the basic filtering condition (region, svc, path, response time, rps)
        The next set of filtering will happen during stitching (relative time, exclusive time, valid call graph, num endpoints)
        given_traces structure:
        given_traces[region][load_bucket][trace_id]['span'] = [span1, span2, ...]
        given_traces[region][load_bucket][trace_id]['time'] = [time1, time2, ...]
        """
        spans = parse_stats_into_spans(body, svc, region, podname)
        for span in spans:
            list_of_span.append(span) # part of continuous profiling
        _, csv_string = local_and_failover_routing_rule(svc, region) # response to wasm
        return csv_string
    elif mode == "runtime":
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
                # adjusted_df: pd.DataFrame = adjustForHillclimbing(svc, region, temp_df)
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
            if type(percentage_df) == type(None): # percentage_df is set by 'optimizer_entrypoint' async function
                logger.error(f"optimizer has never succeeded yet. Rollback to local routing. {full_podname}, {region}")
                _, csv_string = local_and_failover_routing_rule(svc, region)
                return csv_string
            global train_done
            if train_done == False:
                ## TODO
                # _, csv_string = local_and_failover_routing_rule(svc, region)
                return ""
            if percentage_df.empty or (not use_optimizer_output and jumping_df.empty and jumping_feature_enabled):
                logger.debug(f"WARNING, Rollback to local routing. {region}, {full_podname}, percentage_df is empty.")
                ## TODO
                # _, csv_string = local_and_failover_routing_rule(svc, region)
                return ""
            else:
                temp_df: pd.DataFrame = None
                if use_optimizer_output or not jumping_feature_enabled or jumping_df.empty:
                    temp_df = percentage_df.loc[(percentage_df['src_svc'] == svc) & (percentage_df['src_cid'] == region)].copy()
                else:
                    if rules_are_different(jumping_last_seen_opt_output, percentage_df, maxThreshold=0.3) and len(percentage_df) > 0 and False:
                        logger.info(f"(proxyLoad) loghill rules are different, changing jumping base rules, old rules:\n{compute_traffic_matrix(jumping_last_seen_opt_output)}, new rules:\n{compute_traffic_matrix(percentage_df)}, cur jumping_df:\n{compute_traffic_matrix(jumping_df)}")
                        # here, we want to start defensive jumping towards the optimizer output.
                        # we want to jump from jumping_df (which is the current state) to percentage_df (which is the optimizer output).
                        # use_optimizer_output = True
                        jumping_ruleset_num_iterations = 0
                        currently_globally_oscillating = False
                        # make jumping_df the same as percentage_df, because /proxyLoad will use percentage_df, so the latencies
                        # in processing_latencies will be based on the percentage_df.
                        # jumping_df = percentage_df.copy()
                        jumping_df = percentage_df.copy()
                        jumping_last_seen_opt_output = percentage_df.copy()
                        # clear the prev processing latencies, because we will be making a measurement based on the current rules, compared to the proposed (step) rules.
                        global_prev_processing_latencies.clear()
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
                return csv_string
        else: # Invalid ROUTING_RULE
            logger.error(f"ERROR: ROUTING_RULE is not supported yet. ROUTING_RULE: {ROUTING_RULE}")
            assert False
    else: # Invalid mode
        _, csv_string = local_and_failover_routing_rule(svc, region)
        return csv_string
    
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
        idx += 1
    logger.info("*"*60)
        
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

def get_root_node_rps(ep_str_callgraph_table):
    global aggregated_rps
    root_ep = dict()
    root_node_rps = dict()
    for hashed_cg_key in ep_str_callgraph_table:
        root_ep[hashed_cg_key] = opt_func.find_root_node(ep_str_callgraph_table[hashed_cg_key])
        logger.debug(f"root_ep[{hashed_cg_key}]: {root_ep}")
    if len(root_ep) != 0:
        logger.debug('root_node_rps,hashed_cg_key,region,svc_name,endpoint,rps')
        for hashed_cg_key in root_ep:
            for region in aggregated_rps:
                for svc_name in aggregated_rps[region]:
                    for endpoint in aggregated_rps[region][svc_name]:
                        if endpoint == root_ep[hashed_cg_key]:
                            if region not in root_node_rps:
                                root_node_rps[region] = dict()
                            if svc_name not in root_node_rps[region]:
                                root_node_rps[region][svc_name] = dict()
                            root_node_rps[region][svc_name][endpoint] = aggregated_rps[region][svc_name][endpoint]
                            logger.debug(f'root_node_rps,{hashed_cg_key},{region},{svc_name},{endpoint},{root_node_rps[region][svc_name][endpoint]}')
    return root_node_rps


def check_root_node_rps_condition(agg_root_node_rps):
    agg_root_node_rps_exists = False
    for cid in agg_root_node_rps:
        for svc in agg_root_node_rps[cid]:
            for ep in agg_root_node_rps[cid][svc]:
                if agg_root_node_rps[cid][svc][ep] != 0: # {'us-west-1': {'sslateingress': {'sslateingress@POST@/cart/checkout': 102}, 
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
        # sim_percentage_df.drop(columns=['src_endpoint', "dst_endpoint"], inplace=True)
        sim_percentage_df.insert(loc=0, column="counter", value=temp_counter)
        sim_percentage_df = sim_percentage_df.reset_index(drop=True)
        sim_percentage_df.index = [''] * len(sim_percentage_df)
        if os.path.isfile(fn) == False:
            sim_percentage_df.to_csv(fn, mode="w")
        else:
            sim_percentage_df.to_csv(fn, mode="a")
        '''
        column of sim_percentage_df dataframe: ['counter', 'src_svc', 'dst_svc', 'src_endpoint', 'dst_endpoint', 'src_cid', 'dst_cid', 'flow', 'total', 'weight']
        '''
        # logger.info(f"sim_percentage_df:\n{sim_percentage_df[sim_percentage_df['src_svc']=='sslateingress'].to_csv()}")
        logger.info(f"sim_percentage_df:\n{sim_percentage_df.to_csv()}")
        


## All variables are global variables
def optimizer_entrypoint():
    global coef_dict
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
    global normalization_dict
    # aggregated_rps = aggregate_rps_by_region()
    # record_endpoint_rps(aggregated_rps)
    # agg_root_node_rps = get_root_node_rps(ep_str_callgraph_table, aggregated_rps)
    global state

    global jumping_df
    global jumping_last_seen_opt_output
    global global_prev_processing_latencies
    global jumping_ruleset_num_iterations
    global prev_jumping_df
    global currently_globally_oscillating
    global global_processing_latencies
    
    if mode != "runtime":
        logger.warning(f"run optimizer only in runtime mode. current mode: {mode}.")
        return
    if "SLATE" not in ROUTING_RULE and "WATERFALL" not in ROUTING_RULE:
        logger.warning(f"run optimizer only in SLATE, SLATE-with-jumping, SLATE-without-jumping or WATERFALL ROUTING_RULE. current ROUTING_RULE: {ROUTING_RULE}.")
        return
    if train_done == False:
        logger.debug(f"runtime True, {ROUTING_RULE}, BUT run optimizer only after training. train_done: {train_done}, still_training: {still_training}.")
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
    
    ''' check '''
    init_max_capacity_per_service(CAPACITY)        
    with open('optimizer_input.txt', 'w') as f:
        f.write(f"coef_dict: {coef_dict}\n")
        f.write(f"poly_coef_dict: {poly_coef_dict}\n")
        f.write(f"mm1_coef_dict: {mm1_coef_dict}\n")
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
        logger.debug(f'aggreated_rps: {aggregated_rps}')
        return
    
    # for svc in max_capacity_per_service:
        # for region in max_capacity_per_service[svc]:
    # total_cap = get_total_cap_for_service(svc)
    
    assert parent_of_bottleneck_service != "not_init"
    assert parent_of_bottleneck_service != ""
    
    src_svc_total_demand = get_total_rps_for_service(parent_of_bottleneck_service, aggregated_rps) # frontend
    dst_svc_total_cap = get_total_cap_for_service(bottleneck_service) # a
    if src_svc_total_demand > dst_svc_total_cap: 
        logger.debug(f"Total demand({src_svc_total_demand}) at {parent_of_bottleneck_service} > total capcity({dst_svc_total_cap}) at {bottleneck_service}")
        new_capacity_for_bottleneck_svc = int(src_svc_total_demand/len(max_capacity_per_service[bottleneck_service]))+1
        for dst_region in max_capacity_per_service[bottleneck_service]:
            max_capacity_per_service[bottleneck_service][dst_region] = new_capacity_for_bottleneck_svc
            # logger.error(f"recalc capacity: {bottleneck_service}, old_capacity,{max_capacity_per_service[bottleneck_service][dst_region]} -> new_capacity, {new_capacity_for_bottleneck_svc}")
    ## Passed all the basic requirement
    logger.debug(f"start run optimizer temp_counter-{temp_counter} ROUTING_RULE:{ROUTING_RULE}")
    logger.debug(f"before run_optimizer temp_counter-{temp_counter}")
    # logger.info(f"inter_cluster_latency: {inter_cluster_latency}")
    
    
    if "SLATE" in ROUTING_RULE:
        if benchmark_name == "usecase1-cascading":
            logger.info(f"WARNING: Keep the capacity threshold for SLATE for usecase1-cascading")
        else:
            # NOTE: No capacity threshold for SLATE
            # logger.info(f"WARNING: No capacity threshold in SLATE. latency curve will cover things")
            for svc in max_capacity_per_service:
                for region in max_capacity_per_service[svc]:
                    max_capacity_per_service[svc][region] = 100000
        logger.debug(f"run_optimizer starts")
        global endpoint_size
        global DOLLAR_PER_MS
        state = f"{temp_counter}-Optimizer running"
        optimizer_start_ts = time.time()
        
        ############################################################################
        ############################################################################
        # def normalize(heavy_svc, heavy_endpoint, light_svc, light_endpoint, ratio):
        #     global aggregated_rps
        #     global norm_aggregated_rps
        #     norm_aggregated_rps = copy.deepcopy(aggregated_rps)
            
        #     def total_load_per_region():
        #         total_load = dict()
        #         for region in norm_aggregated_rps:
        #             total_load[region] = 0
        #             for svc in norm_aggregated_rps[region]:
        #                 for ep in norm_aggregated_rps[region][svc]:
        #                     total_load += norm_aggregated_rps[region][svc][ep]
        #         return total_load
            
        #     for region in norm_aggregated_rps:
        #         norm_aggregated_rps[region][heavy_svc][heavy_endpoint] += norm_aggregated_rps[region][light_svc][light_endpoint]/ratio
        #         norm_aggregated_rps[region][light_svc][light_endpoint] += norm_aggregated_rps[region][heavy_svc][light_endpoint]*ratio
                
        #     norm_total_load = total_load_per_region()
        #     return norm_total_load

        # norm_total_load = normalize()
        # for region in aggregated_rps:
        #     for svc in aggregated_rps[region]:
        #         for ep in aggregated_rps[region][svc]:
        #             logger.debug(f"aggregated_rps, {region}, {svc}, {ep}, {aggregated_rps[region][svc][ep]}")
        #             logger.debug(f"norm_aggregated_rps, {region}, {svc}, {ep}, {norm_aggregated_rps[region][svc][ep]}")
        # for region in norm_total_load:
        #     logger.debug(f"norm_total_load, {region}, {norm_total_load[region]}")
        ############################################################################
        ############################################################################
        
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
            endpoint_size, \
            DOLLAR_PER_MS, \
            max_rps = 1000, \
            normalization_dict=normalization_dict)
        state = "empty"
        logger.info(f"optimizer took {int(time.time()-optimizer_start_ts)}s")
        if not cur_percentage_df.empty:
            percentage_df = cur_percentage_df
            if rules_are_different(jumping_last_seen_opt_output, percentage_df, maxThreshold=0.1) and len(percentage_df) > 0:
                logger.info(f"(loghill optimizer_entrypoint) rules are different, changing base rules")
                jumping_ruleset_num_iterations = 0
                currently_globally_oscillating = False
                jumping_df = percentage_df.copy()
                prev_jumping_df = percentage_df.copy()
                jumping_last_seen_opt_output = percentage_df.copy()
                global_prev_processing_latencies.clear()
                global_processing_latencies.clear()
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
                logger.info(f"run_optimizer runtime, {time.time()-ts}s")
                
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
    logger.debug(f"after run_optimizer temp_counter-{temp_counter}")
    logger.debug(f"run_optimizer temp_counter-{temp_counter}, result: {desc}")
    if percentage_df.empty:
        logger.error(f"ERROR: run_optimizer FAIL (**{desc}**) return without updating percentage_df")
    write_optimizer_output(temp_counter, percentage_df, desc, "routing_history.csv")
    # logger.info(f"loghill writing jumping_routing_history.csv {percentage_df if use_optimizer_output or not jumping_feature_enabled else jumping_df} and {jumping_df}")
    write_optimizer_output(temp_counter, percentage_df if use_optimizer_output or not jumping_feature_enabled else jumping_df, desc, "jumping_routing_history.csv")
    
    
    ''' end of optimizer_entrypoint '''


def load_coef(coef_file="coef.csv"):
    """
    Load coefficients from a CSV file and structure them into a nested dictionary format.
    The format includes the additional 'region' column, which organizes coefficients further by region.
    """
    loaded_coef = dict()
    check_file_exist(coef_file)
    try:
        # Updated column names to include 'region'
        coef_csv_col = ['region', 'svc_name', 'endpoint', 'feature', 'value']
        df = pd.read_csv(coef_file, names=coef_csv_col, header=None)
        
        for region in df['region'].unique():
            if region not in loaded_coef:
                loaded_coef[region] = dict()
            region_df = df[df['region'] == region]
            
            for svc_name in region_df['svc_name'].unique():
                if svc_name not in loaded_coef[region]:
                    loaded_coef[region][svc_name] = dict()
                svc_df = region_df[region_df['svc_name'] == svc_name]
                
                for endpoint in svc_df['endpoint'].unique():
                    if endpoint not in loaded_coef[region][svc_name]:
                        loaded_coef[region][svc_name][endpoint] = dict()
                    ep_df = svc_df[svc_df['endpoint'] == endpoint]
                    
                    for index, row in ep_df.iterrows():
                        try:
                            # Modify coefficient logic here if needed
                            if False:  # Example condition (currently disabled)
                                loaded_coef[region][svc_name][endpoint][row["feature"]] = float(row["value"]) * 2
                                logger.warning(f"!!! Double the coefficient for {region} {svc_name} {endpoint} {row['feature']} {row['value']}\n" * 10)
                            else:
                                loaded_coef[region][svc_name][endpoint][row["feature"]] = float(row["value"])
                                logger.debug(f"loaded_coef,{region},{svc_name},{endpoint},{row['feature']},{row['value']}")
                        except Exception as ex:
                            logger.error(f"Error processing row: {row}. Error: {ex}")
    except Exception as e:
        logger.error(f"!!! ERROR !!!: failed to read {coef_file} with error: {e}")
        assert False
    
    # Create a deep copy for return
    ret_coef = copy.deepcopy(loaded_coef)
    logger.info("-" * 80)
    for region in ret_coef:
        for svc in ret_coef[region]:
            for ep in ret_coef[region][svc]:
                for feat in ret_coef[region][svc][ep]:
                    logger.info(f"ret_coef,{region},{svc},{ep},{feat},{ret_coef[region][svc][ep][feat]}")
    logger.info("-" * 80)
    return ret_coef


def file_write_traces(given_traces, fn):
    with open(fn, "a") as f:
        for region in given_traces:
            for load_bucket in given_traces[region]:
                for tid in given_traces[region][load_bucket]:
                    single_trace = given_traces[region][load_bucket][tid]
                    for i in range(len(single_trace['span'])):
                        span_str = str(single_trace['span'][i])
                        span_reported_time = single_trace['time'][i]
                        f.write(f"{span_reported_time},{span_str}\n")
                        logger.debug(f"{span_reported_time},{span_str}\n")
                    logger.debug(f"----,----,----,----,----,----,----,----,\n")
                    f.write(f"----,----,----,----,----,----,----,----,\n")
    
    
def filter_incomplete_traces(given_traces):
    global required_total_num_services
    ret_traces = dict()
    for region in given_traces:
        num_failed_traces = 0
        num_success_traces = 0
        total_num_span = 0
        for load_bucket in given_traces[region]:
            for tid in given_traces[region][load_bucket]:
                single_trace = given_traces[region][load_bucket][tid]
                total_num_span += len(single_trace['span'])
                if len(single_trace['span']) == required_total_num_services:
                    assert type(single_trace['span']) == type([])
                    assert type(single_trace['time']) == type([])
                    if region not in ret_traces:
                        ret_traces[region] = dict()
                    if load_bucket not in ret_traces[region]:
                        ret_traces[region][load_bucket] = dict()
                    if tid not in ret_traces[region][load_bucket]:
                        ret_traces[region][load_bucket][tid] = dict()
                    # ret_traces[region][load_bucket][tid]['span'] = list()
                    ret_traces[region][load_bucket][tid]['span'] = single_trace['span']
                    ret_traces[region][load_bucket][tid]['time'] = single_trace['time']
                    num_success_traces += 1
                else:
                    num_failed_traces += 1
        total_num_traces = get_num_trace(given_traces, region)
        if total_num_traces > 0:
            success_ratio = int((num_success_traces/total_num_traces) * 100)
            avg_num_svc = total_num_span/total_num_traces
            logger.info(f"region: {region}, #total: {total_num_traces}, #success: {num_success_traces}, #fail: {num_failed_traces}, avg_num_svc: {avg_num_svc:.2f}, success_ratio, {success_ratio}%")
    return ret_traces


def filter_incomplete_trace_for_multi_traffic_class_in_df(given_df):
    global required_total_num_services
    given_df['num_span'] = given_df.groupby('trace_id')['span_id'].transform('count')
    conditions = [
        given_df['endpoint'] == "frontend@POST@/cart",
        given_df['endpoint'] == "frontend@POST@/cart/checkout"
    ]
    values = [4, 8]
    given_df['required_total_num_services'] = np.select(conditions, values, default=0)
    trace_ids_with_complete_spans = given_df[
        given_df['num_span'] == given_df['required_total_num_services']
    ]['trace_id'].unique()
    df_complete_traces = given_df[given_df['trace_id'].isin(trace_ids_with_complete_spans)].copy()
    given_df = given_df[~given_df['trace_id'].isin(trace_ids_with_complete_spans)].copy()
    return df_complete_traces, given_df


def filter_incomplete_trace_in_df(given_df):
    global required_total_num_services
    given_df['num_span'] = given_df.groupby('trace_id')['span_id'].transform('count')

    """
    NOTE: This is a problem. Two traffic classes will have different number of spans for a complete trace.
    """    
    trace_ids_with_complete_spans = given_df[given_df['num_span'] == required_total_num_services]['trace_id'].unique()
    
    df_complete_traces = given_df[given_df['trace_id'].isin(trace_ids_with_complete_spans)].copy()
    given_df = given_df[~given_df['trace_id'].isin(trace_ids_with_complete_spans)].copy()
    return df_complete_traces, given_df


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
                        logger.info(f"set max_capacity_per_service[{svc}][{region}] = {max_capacity_per_service[svc][region]}")

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

def get_all_endpoint_from_df(df):
    temp = dict()
    for _, row in df.iterrows():
        region = row['cluster_id']
        svc = row['svc_name']
        ep = row['endpoint']
        if region not in temp:
            temp[region] = dict()
        if svc not in temp[region]:
            temp[region][svc] = set()
        temp[region][svc].add(ep)
    return temp

def get_placement_from_df(df):
    temp = dict()
    for index, row in df.iterrows():
        region = row['cluster_id']
        svc = row['svc_name']
        if region not in temp:
            temp[region] = set()
        temp[region].add(svc)
    return temp

def initialize_global_datastructure():
    global coef_dict
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
    global global_stitched_df
    assert init_done == False
    
    ts = time.time()
    ep_str_callgraph_table = tst.trace_df_to_endpoint_callgraph_table(global_stitched_df)
    logger.info(f"trace_df_to_endpoint_callgraph_table took: {int(time.time()-ts)}s")
    
    ts = time.time()
    all_endpoints = get_all_endpoint_from_df(global_stitched_df)
    logger.info(f"get_all_endpoint_from_df took: {int(time.time()-ts)}s")
    
    ts = time.time()
    endpoint_to_placement = set_endpoint_to_placement(all_endpoints)
    logger.info(f"set_endpoint_to_placement took: {int(time.time()-ts)}s")
    
    ts = time.time()
    svc_to_placement = get_svc_to_placement(all_endpoints)
    logger.info(f"get_svc_to_placement took: {int(time.time()-ts)}s")
    
    ts = time.time()
    placement = get_placement_from_df(global_stitched_df)
    logger.info(f"get_placement_from_df took: {int(time.time()-ts)}s")
    
    for region in all_endpoints:
        for svc_name in all_endpoints[region]:
            logger.info(f"Init all_endpoints[{region}][{svc_name}]: {all_endpoints[region][svc_name]}")
    for endpoint in endpoint_to_placement:
        logger.info(f"Init endpoint_to_placement[{endpoint}]: {endpoint_to_placement[endpoint]}")
    for svc_name in svc_to_placement:
        logger.info(f"Init svc_to_placement[{svc_name}]: {svc_to_placement[svc_name]}")
    for region in placement:
        logger.info(f"Init placement[{region}]: {placement[region]}")   
    
    
    """
    partial replication
    """
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
    
    ##################### MOVE #######################
    '''
    endpoint_to_cg_key = tst.get_endpoint_to_cg_key_map(stitched_traces)
    ep_str_callgraph_table, key: hashed cg_key
    cg_key_hashmap, key: hashed_cg_key, value: cg_key (concat of all ep_str in sorted order)
    '''
    # ep_str_callgraph_table, cg_key_hashmap = tst.traces_to_endpoint_callgraph_table(stitched_traces)
    logger.info(f"num callgraph: {len(ep_str_callgraph_table)}")
    assert len(ep_str_callgraph_table) > 0
    print_ep_str_callgraph_table()
    file_write_ep_str_callgraph_table()
    for cid in placement:
        logger.debug(f"placement[{cid}]: {placement[cid]}")
        for region in all_endpoints:
            if region not in aggregated_rps:
                aggregated_rps[region] = dict()
            for svc in all_endpoints[region]:
                if svc not in aggregated_rps[region]:
                    aggregated_rps[region][svc] = dict()
                for endpoint in all_endpoints[region][svc]:
                    aggregated_rps[region][svc][endpoint] = 0
                    logger.debug(f"Init aggregated_rps[{region}][{svc}][{endpoint}]: {aggregated_rps[region][svc][endpoint]}")
                    
                    
def check_negative_coef(coef_dict):
    # NOTE: latency function should be strictly increasing function
    for region in coef_dict: # svc_name: metrics-db
        for svc_name in coef_dict[region]: # svc_name: metrics-db
            for ep_str in coef_dict[region][svc_name]: # ep_str: metrics-db@GET@/dbcall
                for feature_ep in coef_dict[region][svc_name][ep_str]: # feature_ep: 'metrics-db@GET@/dbcall' or 'intercept'
                    if coef_dict[region][svc_name][ep_str][feature_ep] < 0:
                        if feature_ep == "intercept":
                            load_bucket_0_xt = calc_avg_exclusive_time_of_load_bucket(region, svc_name, ep_str, target_load_bucket=1)
                            corrected_intercept = 1
                            if load_bucket_0_xt > 0:
                                corrected_intercept = load_bucket_0_xt
                            logger.warning(f"fix negative {feature_ep},{region},{svc_name}. Set it to {corrected_intercept}.")
                            coef_dict[region][svc_name][ep_str]['intercept'] = corrected_intercept
                        else:
                            coef_dict[region][svc_name][ep_str][feature_ep] = 0
                            logger.warning(f"fix negative {feature_ep},{region},{svc_name}. Set it to 0.")
                            
                            
def set_zero_coef(coef_dict):
    for region in coef_dict:
        for svc_name in coef_dict[region]:
            for ep_str in coef_dict[region][svc_name]:
                for feature_ep in coef_dict[region][svc_name][ep_str]:
                    if feature_ep == "b":
                        coef_dict[region][svc_name][ep_str][feature_ep] = 0
                    else:
                        coef_dict[region][svc_name][ep_str][feature_ep] = 0
                    
                    
def record_continuous_coef_dict(coef_dict):
    global temp_counter
    with open("continuous_coef_dict.csv", "a") as f:
        for region in coef_dict:
            for svc_name in coef_dict[region]:
                for ep_str in coef_dict[region][svc_name]:
                    f.write(f'{temp_counter},{region},{svc_name},{ep_str},{coef_dict[region][svc_name][ep_str]}\n')
        f.write("-------------------------------\n")

def new_read_trace_csv(trace_csv):
    col = ['cluster_id','svc_name','method','url','trace_id','span_id','parent_span_id','st','et','rt','xt','ct','call_size','inflight_dict','rps_dict']
    try:
        df = pd.read_csv(trace_csv, names=col, header=None)
        df['endpoint'] = df['svc_name'] + '@' + df['method'] + '@' + df['url']
        df['inflight'] = df['inflight_dict'].apply(lambda x: int(x.split(':')[1].split('|')[0]))
        df['rps'] = df['rps_dict'].apply(lambda x: int(x.split(':')[1].split('|')[0]))
        df['added_time'] = random.random() # between 0 and 1
        df['load_bucket'] = (df['rps'] // load_bucket_size + 1).clip(lower=1)
        df['trace_id'] = df['cluster_id'].astype(str) + "-" + df['trace_id'].astype(str) # needed because replicate.py uses the same trace_id. make trace id in each region unique
        df.drop(columns=['inflight_dict', 'rps_dict'], inplace=True)
    except Exception as e:
        logger.error(f"!!! ERROR !!!: failed to read {trace_csv} with error: {e}")
        assert False
    return df


def new_fit_mm1_model(local_counter, region, svc_name, df, ep_str):
    from scipy.optimize import curve_fit
    exclusive_time_list = df["xt"].tolist()
    max_rps = df["rps"].max()
    constant = 1.05 * max_rps
    def mm1_model(u, a, b):
        return (a / (constant - u)) + b
    popt, _ = curve_fit(mm1_model, df["rps"], exclusive_time_list, maxfev=10000)
    return {ep_str: popt[0], 'intercept': popt[1]}


def save_polynomial_plot(
    rps_list, exclusive_time_list, response_time_list, model, degree, region, svc_name, local_counter
):
    plt.figure()
    plt.scatter(rps_list, exclusive_time_list, color='red', alpha=0.5, label="xt", marker='x')
    plt.scatter(rps_list, response_time_list, color='green', alpha=0.5, label="rt")
    
    # Generate line plot
    xplot = np.linspace(0, max(rps_list), 1000)
    yplot = model.coef_[0] * xplot**degree + model.coef_[1]
    plt.plot(xplot, yplot, color='blue', label=f"a: {model.coef_[0]:.8f}, b: {model.coef_[1]:.8f}")
    
    # Save the plot
    if "poly" not in os.listdir():
        os.mkdir("poly")
    fn = f"poly/poly-{region}-{svc_name}-{local_counter}.pdf"
    plt.title(f"{fn}")
    plt.xlabel("RPS")
    plt.ylabel("Exclusive Time")
    plt.legend(loc='upper left')
    plt.xlim(left=0)
    plt.ylim(0, 1000)
    plt.savefig(fn, format='pdf', bbox_inches='tight')
    logger.info(f"Saved the plot to {fn}")
    plt.close()


def new_fit_polynomial_regression(local_counter, region, svc_name, df, degree, ep_str, overhead):
    ts = time.time()
    rps_list = df["rps"].tolist()
    exclusive_time_list = df["xt"].tolist()
    response_time_list = df["rt"].tolist()
    temp = np.array([x**degree for x in rps_list]).reshape(-1, 1)  # Reshape to 2D
    X_transformed = np.hstack((temp, np.ones((len(rps_list), 1))))
    model = LinearRegression(fit_intercept=False)
    model.fit(X_transformed, exclusive_time_list)
    overhead["curve_fit"] = overhead.get("curve_fit", 0) + time.time()-ts
    
    ts = time.time()
    if svc_name in ["frontend", "checkoutservice"] and region in ["us-west-1"]:
        plot_executor.submit(
            save_polynomial_plot,
            rps_list,
            exclusive_time_list,
            response_time_list,
            copy.deepcopy(model),
            degree,
            region,
            svc_name,
            local_counter
        )
    overhead["plot"] = overhead.get("plot", 0) + time.time() - ts
    
    ##################################################################
    ## Bottleneck!!!
    # if svc_name in ["frontend"] and region in ["us-west-1"]:
    # ts = time.time()
    # if svc_name in ["frontend", "checkoutservice"] and region in ["us-west-1"]:
    #     plt.figure()
    #     plt.scatter(rps_list, exclusive_time_list, color='red', alpha=0.5, label="xt", marker='x')
    #     plt.scatter(rps_list, response_time_list, color='green', alpha=0.5, label="rt")
    #     # Line plot
    #     xplot = np.linspace(0, max(rps_list), 1000)
    #     yplot = model.coef_[0] * xplot**degree + model.coef_[1]
    #     plt.plot(xplot, yplot, color='blue', label=f"a: {model.coef_[0]:.8f}, b: {model.coef_[1]:.8f}")
    #     # Save the plot
    #     if "poly" not in os.listdir():
    #         os.mkdir("poly")
    #     fn = f"poly/poly-{region}-{svc_name}-{local_counter}.pdf"
    #     plt.title(f"{fn}")
    #     plt.xlabel("RPS")
    #     plt.ylabel("Exclusive Time")
    #     plt.legend(loc='upper left')
    #     plt.savefig(fn, format='pdf', bbox_inches='tight')
    #     logger.info(f"Saved the plot to {fn}")
    #     plt.close()
    # overhead["plot"] = overhead.get("plot", 0) + time.time()-ts
    #############################################################
    return {ep_str: model.coef_[0], 'intercept': model.coef_[1]}

def print_coef_dict(msg=""):
    global coef_dict
    for region in coef_dict:
        for svc_name in coef_dict[region]:
            for ep_str in coef_dict[region][svc_name]:
                for feature in coef_dict[region][svc_name][ep_str]:
                    logger.info(f"coef_dict,{msg},{region},{svc_name},{ep_str},{feature[:8]},{coef_dict[region][svc_name][ep_str][feature]:.8f}")

def new_train_latency_function_with_trace(model, df, degree):
    logger.info(f"new_train_latency_function_with_trace start, model: {model}, degree: {degree}")
    coef_dict = {}
    local_counter = temp_counter
    overhead = {}
    for (region, svc_name, ep_str), ep_df in df.groupby(['cluster_id', 'svc_name', 'endpoint']):
        coef_dict.setdefault(region, {}).setdefault(svc_name, {})
        latency_func.setdefault(svc_name, {})
        if model == "poly":
            coef_dict[region][svc_name][ep_str] = new_fit_polynomial_regression(local_counter, region, svc_name, ep_df, degree, ep_str, overhead)
        elif model == "mm1":
            coef_dict[region][svc_name][ep_str] = new_fit_mm1_model(local_counter, region, svc_name, ep_df, ep_str)
        else:
            logger.error(f"ERROR: Unsupported model type '{model}' specified")
            raise ValueError(f"Invalid model: {model}")
    logger.info(f"overhead took: {overhead}")
    logger.info(f"new_train_latency_function_with_trace end")
    return coef_dict

def print_len_df_trace(df, msg):
    for region in df["cluster_id"].unique():
        num_trace = len(df[df['cluster_id']==region]['trace_id'].unique())
        logger.info(f"{msg}, region: {region}, len: {num_trace}")


def fill_load_bucket_column(df):
    pass

def training_phase():
    global coef_dict
    global poly_coef_dict
    global mm1_coef_dict
    global e2e_coef_dict
    global placement
    global all_endpoints
    global svc_to_placement
    global endpoint_to_placement
    global endpoint_to_cg_key
    global ep_str_callgraph_table
    global mode
    global temp_counter
    global train_done
    global train_start
    global trainig_input_trace_file
    global max_capacity_per_service
    global degree
    global init_done
    global state
    global still_training
    global global_stitched_df
    if os.path.isfile(trainig_input_trace_file) == False: # trace.csv
        logger.warning(f"{trainig_input_trace_file} does not exist.")
        return
    if still_training:
        logger.warning(f"Still training. Skip training_phase()")
        return
    if init_done:
        logger.debug(f"Return trianing_phase routine. reason: Training initialization is done.")
        return
    logger.warning("Training starts")
    start_ts = time.time()
    still_training = True
    ts = time.time()
    df_incomplete_traces = new_read_trace_csv(trainig_input_trace_file)
    
    print_len_df_trace(df_incomplete_traces, "training_phase, df_incomplete_traces-1")
    logger.info(f"new_read_trace_csv took {int(time.time()-ts)}s")
    
    ts = time.time()
    # df_new_complete_traces, df_incomplete_traces = filter_incomplete_trace_in_df(df_incomplete_traces)
    df_new_complete_traces, df_incomplete_traces = filter_incomplete_trace_for_multi_traffic_class_in_df(df_incomplete_traces)
    
    print_len_df_trace(df_new_complete_traces, "training_phase, df_new_complete_traces")
    print_len_df_trace(df_incomplete_traces, "training_phase, df_incomplete_traces-2")
    logger.info(f"filter_incomplete_trace_in_df took {int(time.time()-ts)}s")
    
    ts = time.time()
    assert len(global_stitched_df) == 0
    global_stitched_df = tst.stitch_time_in_df(df_new_complete_traces, ep_str_callgraph_table)
    # global_stitched_df = tst.stitch_time_in_df_concurrent(df_new_complete_traces, ep_str_callgraph_table, max_workers=8)
    print_len_df_trace(global_stitched_df, "training_phase, global_stitched_df")
    logger.info(f"stitch_time_in_df took {int(time.time()-ts)}s")
    
    for region in global_stitched_df['cluster_id'].unique():
        for load_bucket in global_stitched_df['load_bucket'].unique():
            temp = global_stitched_df[(global_stitched_df['load_bucket']==load_bucket) & (global_stitched_df['cluster_id']==region)]
            logger.info(f"global_stitched_df, {region}, load_bucket: {load_bucket}, len: {len(temp['trace_id'].unique())}")
    
    ts = time.time()
    initialize_global_datastructure()
    logger.info(f"initialize_global_datastructure took {int(time.time()-ts)}s")
    
    init_done = True
    if mode != "runtime":
        logger.debug(f"It is not runtime mode. Skip training. current mode: {mode}")
        return
    if train_start:
        logger.debug(f"Training is already started.")
        return
    if train_done:
        logger.debug(f"Training was done. Training is required only once")
        return
    train_start = True
    logger.info(f"data preprocessing took {int(time.time() - start_ts)}s")
    if degree <= 0:
        logger.error(f"ERROR: degree is not valid. degree: {degree}")
        assert False
    ## NOTE: No load_coef, fit the function from scratch
    if load_coef_flag: # Load
        try:
            coef_dict = load_coef(coef_file="coef.csv")
            if coef_dict != None:
                check_negative_coef(coef_dict)
            e2e_coef_dict = load_coef(coef_file="e2e-coef.csv")
            if e2e_coef_dict != None:
                check_negative_coef(e2e_coef_dict)
        except Exception as e:
            logger.error(f"!!! ERROR !!!: failed to load coef with error: {e}")
            state = "[!!! PANIC !!!] load_coef() in training_phase()"
            assert False
        print_coef_dict("load_coef")
    else: # Train
        with coef_dict_mutex:
            ts = time.time()
            coef_dict = new_train_latency_function_with_trace("poly", global_stitched_df,   degree=2) # or "mm1"
            print_coef_dict("training_phase")
            logger.info(f"new_train_latency_function_with_trace took {int(time.time()-ts)}s")
            logger.info(f"coef_dict: {coef_dict['us-west-1']['frontend']['frontend@POST@/cart/checkout']}")
            for region in coef_dict:
                if region not in frontend_coef_history:
                    frontend_coef_history[region] = list()
                frontend_coef_history[region].append([coef_dict[region]['frontend']['frontend@POST@/cart/checkout']['frontend@POST@/cart/checkout'], coef_dict[region]['frontend']['frontend@POST@/cart/checkout']['intercept']])
            check_negative_coef(coef_dict)
            record_continuous_coef_dict(coef_dict)
    if ROUTING_RULE == "WATERFALL" or ROUTING_RULE == "WATERFALL2":
        set_zero_coef(coef_dict)
    with open("coefficient.csv", "w") as f:
        f.write("svc_name, endpoint, coef\n")
        for region in coef_dict:
            for svc_name in coef_dict[region]:
                for ep_str in coef_dict[region][svc_name]:
                    logger.debug(f'final coef_dict,{region},{svc_name},{coef_dict[region][svc_name][ep_str]}')
                    f.write(f'{svc_name},{ep_str},{coef_dict[region][svc_name][ep_str]}\n')
    with open("e2e-coefficient.csv", "w") as f:
        f.write("svc_name, endpoint, coef\n")
        for svc_name in e2e_coef_dict:
            for ep_str in e2e_coef_dict[svc_name]:
                logger.debug(f'final e2e_coef_dict,{svc_name},{e2e_coef_dict[svc_name][ep_str]}')
                f.write(f'{svc_name},{ep_str},{e2e_coef_dict[svc_name][ep_str]}\n')
    ''' It will be used as a constraint in the optimizer'''
    train_done = True # train done!
    logger.info(f"trainig_phase took {int(time.time() - start_ts)}s")
    still_training = False
    return


def read_config_file():
    global benchmark_name
    global required_total_num_services
    global mode
    global ROUTING_RULE
    global MODE_SET
    global CAPACITY
    global degree
    global inter_cluster_latency
    global train_done
    global normalization_dict
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
    global max_num_trace
    global load_bucket_size
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
                    elif benchmark_name == "corecontrast":
                        parent_of_bottleneck_service = "sslateingress"
                        bottleneck_service = "corecontrast"
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
                if required_total_num_services != int(line[1]):
                    logger.info(f'Update required_total_num_services: {required_total_num_services} -> {line[1]}')
                    required_total_num_services = int(line[1])
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
            elif line[0] == "normalization":
                # Format: normalization,srcsrv@method@path,dstsvc@method@path,0.01
                #          [0]          [1]                [2]                [3]
                src = line[1]
                dst = line[2]
                norm = float(line[3])
                if src not in normalization_dict:
                    normalization_dict[src] = dict()
                if dst not in normalization_dict[src]:
                    normalization_dict[src][dst] = dict()
                logger.info(f'Update normalization_dict: {src} -> {dst}: {norm}')
                normalization_dict[src][dst] = norm
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
                    logger.info(f'Update workload: {line[1]}-{line[2]}: {line[3]} RPS')
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
            elif line[0] == "max_num_trace":
                max_num_trace = int(line[1])
                assert max_num_trace >= 0
            elif line[0] == "load_bucket_size":
                load_bucket_size = int(line[1])
                assert load_bucket_size >= 0
            else:
                logger.debug(f"SKIP parsing unknown config: {line}")
                # logger.error(f"ERROR: unknown config: {line}")
                # state = f"[!!! PANIC !!!] unknown config in {env_file}: {line[0]}"
                
    # logger.info(f"benchmark_name: {benchmark_name}, required_total_num_services: {required_total_num_services}, mode: {mode}, ROUTING_RULE: {ROUTING_RULE}")


def record_endpoint_rps(aggregated_rps, counter):
    endpoint_rps_fn = "endpoint_rps_history.csv"
    if os.path.isfile(endpoint_rps_fn) == False:
        with open(endpoint_rps_fn, "w") as f:
            f.write("counter,region,service,endpoint,rps\n")
    else:
        if mode == "runtime" and train_done == False:
            logger.debug(f"Skip recording endpoint_rps_history.csv. aggregated_rps has not been initialized because training is not done yet.")
            return
        with open(endpoint_rps_fn, "a") as f:
            for region in aggregated_rps:
                for svc in aggregated_rps[region]:
                    for endpoint in aggregated_rps[region][svc]:
                        temp = f"{counter},{region},{svc},{endpoint},{aggregated_rps[region][svc][endpoint]}"
                        f.write(temp + "\n")
                        

# def aggregated_rps_routine():
#     global per_pod_ep_rps
#     global aggregated_rps
#     global agg_root_node_rps
#     global temp_counter
#     global prev_ts
#     # aggregate_rps_by_region_or_zero(per_pod_ep_rps)
#     aggregate_rps_by_region_or_zero()
#     agg_root_node_rps = get_root_node_rps(ep_str_callgraph_table, aggregated_rps)
#     if check_root_node_rps_condition(agg_root_node_rps) or temp_counter > 0:
#         record_endpoint_rps(aggregated_rps, temp_counter)
#         logger.info("-"*80)
#         logger.info(f"aggregated_rps_routine, temp_counter-{temp_counter}, gap: {time.time()-prev_ts}")
#         prev_ts = time.time()
#         for region in agg_root_node_rps:
#             for svc in agg_root_node_rps[region]:
#                 for endpoint in agg_root_node_rps[region][svc]:
#                     logger.warning(f"agg_root_node_rps,{region},{svc},{endpoint},{agg_root_node_rps[region][svc][endpoint]}")
#         logger.warning("-"*80)
    
#     # also print per_pod_ep_rps AND aggregated_rps for all services in us-west-1.
#     # after that, print per_pod_ep_rps AND aggregated_rps for regions for the frontend service.
#     # logger.info("logadi-aggregate rps")
#     # logger.info("-"*80)
#     # region = "us-west-1"
#     # svc = "sslateingress"
    
    
#     # for endpoint in per_pod_ep_rps[region][svc]:
#     #     for podname in per_pod_ep_rps["us-west-1"][svc][endpoint]:
#     #         logger.info(f"{temp_counter},per_pod_ep_rps,us-west-1,{svc},{endpoint},{podname},{per_pod_ep_rps['us-west-1'][svc][endpoint][podname]}")
#     # for svc in aggregated_rps["us-west-1"]:
#     #     for endpoint in aggregated_rps["us-west-1"][svc]:
#     #         logger.info(f"{temp_counter},aggregated_rps,us-west-1,{svc},{endpoint},{aggregated_rps['us-west-1'][svc][endpoint]}")
#     # for region in per_pod_ep_rps:
#     #     for endpoint in per_pod_ep_rps[region]["frontend"]:
#     #         for podname in per_pod_ep_rps[region]["frontend"][endpoint]:
#     #             logger.info(f"{temp_counter},per_pod_ep_rps,{region},frontend,{endpoint},{podname},{per_pod_ep_rps[region]['frontend'][endpoint][podname]}")
#     # for region in aggregated_rps:
#     #     for endpoint in aggregated_rps[region]["frontend"]:
#     #         logger.info(f"{temp_counter},aggregated_rps,{region},frontend,{endpoint},{aggregated_rps[region]['frontend'][endpoint]}")
#     # logger.info("-"*80)
#     temp_counter += 1


## from global_controller-continuous.py
def aggregated_rps_routine():
    global per_pod_ep_rps
    global aggregated_rps
    global agg_root_node_rps
    global temp_counter
    ## initializing all_endpoint can take time
    for region in per_pod_ep_rps:
        if region not in aggregated_rps:
            aggregated_rps[region] = dict()
        for svc_name in per_pod_ep_rps[region]:
            if svc_name not in aggregated_rps[region]:
                aggregated_rps[region][svc_name] = dict()
            for endpoint in per_pod_ep_rps[region][svc_name]:
                # if endpoint not in aggregated_rps[region][svc_name]: aggregated_rps[region][svc_name][endpoint] = 0
                aggregated_rps[region][svc_name][endpoint] = 0
                logger.debug(f"Set zero, aggregated_rps[{region}][{svc_name}][{endpoint}]: {aggregated_rps[region][svc_name][endpoint]}")
    
    for region in aggregated_rps:
        for svc_name in aggregated_rps[region]:
            for endpoint in aggregated_rps[region][svc_name]:
                aggregated_rps[region][svc_name][endpoint] = 0
                logger.debug(f"Set zero, aggregated_rps[{region}][{svc_name}][{endpoint}]: {aggregated_rps[region][svc_name][endpoint]}")
    
    # aggregated_rps.setdefault(region, {}).setdefault(svc_name, {})[endpoint] = 0
    for region in per_pod_ep_rps:
        for svc_name in per_pod_ep_rps[region]:
            for endpoint in per_pod_ep_rps[region][svc_name]:
                for podname in per_pod_ep_rps[region][svc_name][endpoint]:
                    aggregated_rps[region][svc_name][endpoint] += per_pod_ep_rps[region][svc_name][endpoint][podname]

    # root_node_rps[region][svc_name][endpoint]: rps
    agg_root_node_rps = get_root_node_rps(ep_str_callgraph_table)
    for region in agg_root_node_rps:
        # NOTE: hardcoded
        agg_root_node_rps[region]["sslateingress"]["sslateingress@POST@/cart/checkout"] = aggregated_rps[region]["sslateingress"]["sslateingress@POST@/cart/checkout"]
    
    # if check_root_node_rps_condition(agg_root_node_rps) > 0:
    record_endpoint_rps(aggregated_rps, temp_counter)
    logger.info("-"*80)
    logger.info(f"aggregated_rps_routine, temp_counter-{temp_counter}")
    for region in agg_root_node_rps:
        for svc in agg_root_node_rps[region]:
            for endpoint in agg_root_node_rps[region][svc]:
                logger.info(f"agg_root_node_rps,{region},{svc},{endpoint},{agg_root_node_rps[region][svc][endpoint]}")
    logger.info("-"*80)
    temp_counter += 1


def state_check():
    global state
    if state != "SUCCESS" and state != "empty":
        logger.info(f"state: {state}")

## TODO
def calc_avg_exclusive_time_of_load_bucket(region, svc_name, ep_str, target_load_bucket):
    global global_stitched_df
    df = global_stitched_df[(global_stitched_df['cluster_id']==region) & (global_stitched_df['svc_name']==svc_name) & (global_stitched_df['endpoint']==ep_str)]
    df = df[df['load_bucket']==target_load_bucket]
    if len(df["xt"]) == 0:
        return 1
    return df["xt"].mean()

def runtime_model_update():
    global coef_dict
    global poly_coef_dict
    global mm1_coef_dict
    global degree
    global frontend_coef_history
    global state
    global global_stitched_df
    ts = time.time()
    with coef_dict_mutex:
        ts1 = time.time()
        if model == "mm1":
            coef_dict = trace_parser.train_latency_function_with_trace("mm1", global_stitched_df, directory=".", degree=None)
        elif model == "poly":
            ts2 = time.time()
            coef_dict = new_train_latency_function_with_trace("poly", global_stitched_df, degree=degree)
            print_coef_dict("runtime_model_update")
            
            logger.info(f"new_train_latency_function_with_trace, runtime {int(time.time() - ts2)}s")
        else:
            logger.error(f"!!! ERROR !!!: unknown model: {model}")
            state = "[!!! PANIC !!!] unknown latency model"
            assert False
        logger.info(f"train_latency_function_with_trace took {int(time.time() - ts1)}s")
        
        for region in coef_dict:
            if region not in frontend_coef_history:
                frontend_coef_history[region] = list()
            frontend_coef_history[region].append([coef_dict[region]['frontend']['frontend@POST@/cart/checkout']['frontend@POST@/cart/checkout'], coef_dict[region]['frontend']['frontend@POST@/cart/checkout']['intercept']])
        
        for region in frontend_coef_history:
            if region == "us-west-1":
                for coef in frontend_coef_history[region]:
                    logger.info(f"frontend_coef_history,{region},[a:{coef[0]:.2e}, intercetp:{coef[1]:.2e}]")
        # logger.info(f"poly_coef_dict: {poly_coef_dict['us-west-1']['frontend']['frontend@POST@/cart/checkout']}")
        # logger.info(f"mm1_coef_dict: {mm1_coef_dict['us-west-1']['frontend']['frontend@POST@/cart/checkout']}")
        check_negative_coef(coef_dict)
        record_continuous_coef_dict(coef_dict)
    logger.info(f"runtime_model_update took {int(time.time() - ts)}s")
        
        
def print_num_trace_in_all_regions(given_traces, trace_name):
    for region in given_traces:
        logger.info(f"num {trace_name}[{region}]: {get_num_trace(given_traces, region)}")


def random_sampling_per_load_bucket_in_df(df, sampling_ratio, max_num_trace):
    all_tid = df['trace_id'].unique().tolist()  # Convert to a list
    if len(all_tid) > max_num_trace:
        sampled_tid = random.sample(all_tid, int(len(all_tid) * sampling_ratio))
        df = df[df['trace_id'].isin(sampled_tid)]
    return df

def sliding_window(df, max_num_trace):
    global load_bucket_size
    df['rank'] = df.groupby(['cluster_id', 'load_bucket', 'trace_id'])['added_time'].transform('max')
    df['rank'] = df.groupby(['cluster_id', 'load_bucket'])['rank'].rank(method='first', ascending=False)
    filtered_df = df[df['rank'] <= max_num_trace].drop(columns=['rank'])
    grouped_counts = df.groupby(['cluster_id', 'load_bucket'])['trace_id'].nunique()
    filtered_counts = filtered_df.groupby(['cluster_id', 'load_bucket'])['trace_id'].nunique()
    for (region, load_bucket), count in grouped_counts.items():
        filtered_count = filtered_counts.get((region, load_bucket), 0)
        if count > max_num_trace:
            load_bucket_range = [load_bucket_size * (load_bucket - 1), load_bucket_size * load_bucket - 1]
            logger.info(f"Sliding window applied: region {region},load_bucket[{load_bucket}], {load_bucket_range[0]}-{load_bucket_range[1]}: {count} -> {filtered_count}")
        else:
            logger.debug(
                f"No sliding window applied: region {region}, load_bucket[{load_bucket}]: {count}"
            )
    return filtered_df


# def sliding_window(df, max_num_trace):
#     global load_bucket_size
#     """
#     Enforce a sliding window on the DataFrame by removing older traces
#     (grouped by `trace_id`) when the number of traces exceeds num_max_traces
#     for each load_bucket.

#     Parameters:
#     - df (pd.DataFrame): The DataFrame containing span data.
#     - num_max_traces (int): Maximum number of traces to retain per load_bucket.
#     - load_bucket_size (int): The size of each load bucket.

#     Returns:
#     - pd.DataFrame: Updated DataFrame with excess traces removed.
#     """
#     updated_df = pd.DataFrame()  # To collect filtered spans
#     for region, region_group in df.groupby('cluster_id'):
#         for endpoint, endpoint_group in region_group.groupby('endpoint'):
#             for load_bucket, bucket_group in endpoint_group.groupby('load_bucket'):
#                 # Group by trace_id and find the most recent added_time per trace
#                 trace_times = (
#                     bucket_group.groupby('trace_id')['added_time']
#                     .max()
#                     .reset_index()
#                     .sort_values(by='added_time', ascending=True)
#                 )
#                 previous_count = len(trace_times)
#                 if previous_count > max_num_trace:
#                     trace_ids_to_keep = trace_times.iloc[-max_num_trace:]['trace_id']
#                     bucket_group_to_keep = bucket_group[bucket_group['trace_id'].isin(trace_ids_to_keep)]
#                     bucket_group_to_remove = bucket_group[~bucket_group['trace_id'].isin(trace_ids_to_keep)]
#                     load_bucket_range = [load_bucket_size * (load_bucket - 1), load_bucket_size * load_bucket - 1]
#                     logger.info(
#                         f"Sliding window applied: region {region}, endpoint{endpoint}, load_bucket[{load_bucket}], "
#                         f"{load_bucket_range[0]}-{load_bucket_range[1]}: {previous_count} -> {len(trace_ids_to_keep)}"
#                     )
#                 else:
#                     bucket_group_to_keep = bucket_group
#                     bucket_group_to_remove = pd.DataFrame()  # No traces to remove
#                     logger.debug(
#                         f"No sliding window applied: region {region}, load_bucket[{load_bucket}]: {previous_count}"
#                     )
#                 updated_df = pd.concat([updated_df, bucket_group_to_keep], ignore_index=True)
#     return updated_df



# def enforce_trace_limit(max_num_trace):
#     with stitched_complete_traces_mutex:
#         for region in stitched_complete_traces:
#             for load_bucket in stitched_complete_traces[region]:
#                 load_bucket_range = [load_bucket_size*(load_bucket-1), load_bucket_size*load_bucket-1]
#                 previous_count = len(stitched_complete_traces[region][load_bucket])
#                 if previous_count > max_num_trace:
#                     # Collect trace IDs with their most recent time
#                     trace_times = [
#                         (trace_id, max(trace_data["time"])) 
#                         for trace_id, trace_data in stitched_complete_traces[region][load_bucket].items()
#                     ]
#                     # Find the traces to remove using heapq.nsmallest for efficiency
#                     traces_to_remove = heapq.nsmallest(previous_count - max_num_trace, trace_times, key=lambda x: x[1])
#                     trace_ids_to_delete = [trace_id for trace_id, _ in traces_to_remove]
#                     # Delete the oldest traces
#                     for trace_id in trace_ids_to_delete:
#                         del stitched_complete_traces[region][load_bucket][trace_id]
#                     # Log the results
#                     current_count = len(stitched_complete_traces[region][load_bucket])
#                     logger.info(f"sliding window, region {region}, load_bucket[{load_bucket}], {load_bucket_range[0]}-{load_bucket_range[1]}: {previous_count} -> {current_count}")
#                 else:
#                     logger.debug(f"sliding window, region {region}, load_bucket[{load_bucket}], {load_bucket_range[0]}-{load_bucket_range[1]}: {previous_count}")


def update_traces():
    global train_done
    global init_done
    global temp_counter
    global list_of_body
    global df_incomplete_traces
    global global_stitched_df
    global required_total_num_services
    global ep_str_callgraph_table
    global ROUTING_RULE
    if ROUTING_RULE != "SLATE-with-jumping-global-continuous-profiling":
        logger.info(f"ROUTING_RULE({ROUTING_RULE}) is not SLATE-with-jumping-global-continuous-profiling. Skip update_traces()")
        return
    ts = time.time()
    with list_of_body_mutex: # option 4
        temp = list()
        body_traces = dict()
        for body in list_of_body:
            # logger.info(f"body: {body}")
            for line in body.split('\n'):
                result = re.split(r'[ ,;:|]+', line)
                # logger.info(f"result: {result}")
                """
                result 14: ['us-south-1', 'sslateingress-us-south-1', 'POST', '/cart/checkout', '6f11db9eb19ab79ce26efcba89c37d74', 'e26efcba89c37d74', ' ', '1731636869805', '1731636869831', '0', 'POST@/cart/checkout', '11', '0', '']
                """
                if len(result) == 13:
                    result.insert(6, ' ')
                if len(result) == 14:
                    logger.debug(f"result 14: {result}")
                    temp.append(result)
        list_of_body = [] # empty list_of_body    
        if len(temp) > 0:
            df_new_traces = pd.DataFrame(temp, columns=['cluster_id', 'svc_name', 'method', 'url', 'trace_id', 'span_id', 'parent_span_id', 'st', 'et', 'call_size', 'endpoint', 'rps', 'inflight', "dummy"])
            df_new_traces.drop(columns=['dummy'], inplace=True)
            # 'sslateingress-us-south-1' => 'sslateingress'
            df_new_traces['svc_name'] = df_new_traces['svc_name'].apply(lambda x: x.split('-us-')[0])
            df_new_traces['endpoint'] = df_new_traces['svc_name'] + "@" + df_new_traces['endpoint']
            df_new_traces['st'] = df_new_traces['st'].astype(int)
            df_new_traces['et'] = df_new_traces['et'].astype(int)
            df_new_traces['rt'] = df_new_traces['et'] - df_new_traces['st']
            df_new_traces['xt'] = -1
            df_new_traces['ct'] = -1
            df_new_traces['call_size'] = df_new_traces['call_size'].astype(int)
            num_pod_of_this_region = 4 # NOTE: hardcoded
            df_new_traces['rps'] = df_new_traces['rps'].astype(int)
            df_new_traces['rps'] = df_new_traces['rps']*num_pod_of_this_region
            df_new_traces['load_bucket'] = (df_new_traces['rps']//load_bucket_size + 1).clip(lower=1)
            # df_new_traces['load_bucket'] = ((df_new_traces['rps'] - (load_bucket_size // 2)) // load_bucket_size + 1).clip(lower=1)
            df_new_traces['added_time'] = time.time()
            
            for region in df_new_traces['cluster_id'].unique():
                for load_bucket in df_new_traces['load_bucket'].unique():
                    temp = df_new_traces[(df_new_traces['load_bucket']==load_bucket) & (df_new_traces['cluster_id']==region)]
                    logger.info(f"df_new_traces, {region}, load_bucket: {load_bucket}, len: {len(temp['trace_id'].unique())}")
                
            if len(df_incomplete_traces) == 0:
                df_incomplete_traces = df_new_traces
            else:
                df_incomplete_traces = pd.concat([df_incomplete_traces, df_new_traces])
                
        
    if not train_done:
        logger.info(f"Train has not been done yet. train_done: {train_done}")
        return
    if not init_done:
        logger.info(f"Init has not been done yet. init_done: {init_done}")
        return
    df_new_complete_traces, df_incomplete_traces = filter_incomplete_trace_in_df(df_incomplete_traces)
    print_len_df_trace(df_incomplete_traces, "update_traces/df_new_complete_traces")
    
    df_new_stitched_tracess = tst.stitch_time_in_df(df_new_complete_traces, ep_str_callgraph_table)
    # df_new_stitched_tracess = tst.stitch_time_in_df_concurrent(df_new_complete_traces, ep_str_callgraph_table, max_workers=8)
    print_len_df_trace(df_incomplete_traces, "update_traces/df_new_stitched_tracess")
    
    global_stitched_df = pd.concat([global_stitched_df, df_new_stitched_tracess], ignore_index=True)
    print_len_df_trace(df_incomplete_traces, "update_traces/global_stitched_df")
    
    # global_stitched_df = random_sampling_per_load_bucket_in_df(global_stitched_df, 0.9, max_num_trace)
    print_len_df_trace(df_incomplete_traces, "update_traces/global_stitched_df-sampled")
    
    global_stitched_df = sliding_window(global_stitched_df, max_num_trace)
    print_len_df_trace(df_incomplete_traces, "update_traces/global_stitched_df-sliding_windowed")
    
    runtime_model_update()
    logger.info(f"counter[{temp_counter}], update_traces ends, took {int(time.time() - ts)}s")
    
    
if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=read_config_file, trigger="interval", seconds=1)
    scheduler.add_job(func=write_spans_to_file, trigger="interval", seconds=5)
    time.sleep(3)
    scheduler.add_job(func=update_traces, trigger="interval", seconds=10)
    # scheduler.add_job(func=runtime_model_update, trigger="interval", seconds=1)
    scheduler.add_job(func=training_phase, trigger="interval", seconds=1)
    scheduler.add_job(func=aggregated_rps_routine, trigger="interval", seconds=1)
    scheduler.add_job(func=optimizer_entrypoint, trigger="interval", seconds=1)
    # scheduler.add_job(func=write_load_conditions, trigger="interval", seconds=10)
    scheduler.add_job(func=perform_jumping, trigger="interval", seconds=15)
    scheduler.add_job(func=state_check, trigger="interval", seconds=1)
    # scheduler.add_job(func=write_hillclimb_history_to_file, trigger="interval", seconds=15)
    # scheduler.add_job(func=write_global_hillclimb_history_to_file, trigger="interval", seconds=15)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
    app.run(host='0.0.0.0', port=8080)
