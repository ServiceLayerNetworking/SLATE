from flask import Flask, request, abort
import logging
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from threading import Lock
import optimizer_test as opt
import optimizer_header as opt_func
import config as cfg
import span as sp
import time_stitching as tst
import pandas as pd
from sklearn.model_selection import train_test_split
from IPython.display import display
from pprint import pprint
import random
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
import datetime
import os
import math
import matplotlib.pyplot as plt
import numpy as np
import time
import copy
import warnings
import json
import hashlib

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
aggregated_rps = {}
agg_root_node_rps = {}
endpoint_level_rps_mutex = Lock()
per_pod_ep_rps = {}
per_pod_ep_rps_mutex = Lock()
service_level_rps = {}
endpoint_to_cg_key = {}
ep_str_callgraph_table = {}
# all_endpoints = {}
temp_counter = 0
prev_ts = time.time()
load_coef_flag = False
init_done = False

placement = {}
coef_dict = {}
degree = 0
endpoint_to_placement = dict()
svc_to_placement = dict()
percentage_df = pd.DataFrame()
optimizer_cnt = 0
endpoint_rps_cnt = 0
inter_cluster_latency = dict()
stats_mutex = Lock()
endpoint_rps_history = list()
traffic_segmentation = 1
objective = "avg_latency"
first_write_flag_for_profiled_trace=True


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
ROUTING_RULE_SET = ["LOCAL", "SLATE", "REMOTE", "MCLB", "WATERFALL", "WATERFALL2"]
CAPACITY = 0 
max_capacity_per_service = dict() # max_capacity_per_service[svc][region] = CAPACITY

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
                            ## scalability test    
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
                else:
                    logger.info("root node rps is 0")
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


def write_optimizer_output(optimizer_cnt, percentage_df, desc, fn):
    if percentage_df.empty:
        if os.path.isfile(fn):
            with open(fn, "a") as f:
                f.write(f"idx,{optimizer_cnt},fail,{desc}\n")
    else:
        sim_percentage_df = percentage_df.copy()
        # if benchmark_name != "usecase3-compute-diff" or benchmark_name != "hotelreservation":
        #     sim_percentage_df = sim_percentage_df.drop(columns=['src_endpoint', "dst_endpoint"]).reset_index(drop=True)
        sim_percentage_df.insert(loc=0, column="counter", value=optimizer_cnt)
        if os.path.isfile(fn) == False:
            sim_percentage_df.to_csv(fn, mode="w")
        else:
            sim_percentage_df.to_csv(fn, header=False, mode="a")
        sim_percentage_df = sim_percentage_df.reset_index(drop=True)
        logger.info(f"sim_percentage_df:\n{sim_percentage_df.to_csv()}")
        

## All variables are global variables
def optimizer_entrypoint(degree_, fanout):
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
    global optimizer_cnt
    # global degree
    global inter_cluster_latency
    global CAPACITY
    global train_done
    global benchmark_name
    global bottleneck_service
    global parent_of_bottleneck_service
    global aggregated_rps
    global agg_root_node_rps
    # aggregated_rps = aggregate_rps_by_region()
    # record_endpoint_rps(aggregated_rps)
    # agg_root_node_rps = get_root_node_rps(ep_str_callgraph_table, aggregated_rps)
    
    if mode != "runtime":
        logger.info(f"run optimizer only in runtime mode. current mode: {mode}. return optimizer_entrypoint without executing optimizer...")
        return
    if ROUTING_RULE != "SLATE" and ROUTING_RULE != "WATERFALL" and ROUTING_RULE != "WATERFALL2":
        logger.info(f"run optimizer only in SLATE or WATERFALL ROUTING_RULE. current ROUTING_RULE: {ROUTING_RULE}. return optimizer_entrypoint without executing optimizer...")
        return
    if train_done == False:
        logger.info(f"run optimizer only after training. train_done: {train_done}. return optimizer_entrypoint without executing optimizer...")
        return
    if len(ep_str_callgraph_table) == 0:
        logger.error(f"!!! ERROR !!!: ep_str_callgraph_table is empty.")
        return
    
    ''' check '''
    # init_max_capacity_per_service(CAPACITY)        
    logger.info(f"coef_dict: {coef_dict}\n")
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
    
    
    src_svc_total_demand = get_total_rps_for_service(parent_of_bottleneck_service, aggregated_rps) # frontend
    dst_svc_total_cap = get_total_cap_for_service(bottleneck_service) # a
    if src_svc_total_demand > dst_svc_total_cap: 
        logger.error(f"!!! ERROR !!! Total demand({src_svc_total_demand}) at {parent_of_bottleneck_service} > total capcity({dst_svc_total_cap}) at {bottleneck_service}")
        new_capacity_for_bottleneck_svc = int(src_svc_total_demand/len(max_capacity_per_service[bottleneck_service]))+1
        for dst_region in max_capacity_per_service[bottleneck_service]:
            max_capacity_per_service[bottleneck_service][dst_region] = new_capacity_for_bottleneck_svc
            logger.error(f"recalc capacity: {bottleneck_service}, old_capacity,{max_capacity_per_service[bottleneck_service][dst_region]} -> new_capacity, {new_capacity_for_bottleneck_svc}")
    ## Passed all the basic requirement
    optimizer_cnt += 1
    logger.info(f"start run optimizer optimizer_cnt-{optimizer_cnt} ROUTING_RULE:{ROUTING_RULE}")
    logger.info(f"before run_optimizer optimizer_cnt-{optimizer_cnt}")
    # logger.info(f"inter_cluster_latency: {inter_cluster_latency}")
    '''
    percentage_df = pd.DataFrame(
        data={
            "src_svc": src_svc_list,
            "dst_svc": dst_svc_list,
            "src_endpoint": src_endpoint_list,
            "dst_endpoint": dst_endpoint_list, 
            "src_cid": src_cid_list,
            "dst_cid": dst_cid_list,
            "flow": flow_list,
        },
        index = src_and_dst_index
    )
    '''
    if ROUTING_RULE == "SLATE":
        if benchmark_name == "usecase1-cascading":
            logger.info(f"WARNING: Keep the capacity threshold for SLATE for usecase1-cascading")
        else:
            # NOTE: No capacity threshold for SLATE
            logger.info(f"WARNING: No capacity threshold in SLATE. latency curve will cover things")
            aggregated_rps_per_region = dict()
            for region in aggregated_rps:
                aggregated_rps_per_region[region] = dict()
                for svc in aggregated_rps[region]:
                    aggregated_rps_per_region[region][svc] = 0
                    for ep in aggregated_rps[region][svc]:
                        aggregated_rps_per_region[region][svc] += aggregated_rps[region][svc][ep]
            for svc in max_capacity_per_service:
                for region in max_capacity_per_service[svc]:
                    max_capacity_per_service[svc][region] = aggregated_rps_per_region[region][svc]*num_cluster
        ts = time.time()
        logger.info(f"run_optimizer starts")
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
            degree_, \
            inter_cluster_latency, \
            fanout)
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
            
            order_of_optimization = ['us-central-1', 'us-south-1', 'us-east-1', 'us-west-1']
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
                    else:
                        logger.error(f"!!! ERROR !!!: benchmark_name is not supported. benchmark_name: {benchmark_name}")
                        assert False
                    for frontend_ep in endpoint_rps_at_frontend:
                        target_region_ingress_gw_rps[frontend_ep] = endpoint_rps_at_frontend[frontend_ep]
                        logger.info(f"run_optimizer optimizer_cnt-{optimizer_cnt}, target_region: {target_region}, frontend endpoint: {frontend_ep}, rps: {endpoint_rps_at_frontend[frontend_ep]}")
                else:
                    for svc in region_endpoint_level_rps[region]:
                        for ep in region_endpoint_level_rps[region][svc]:
                            region_endpoint_level_rps[region][svc][ep] = 0
            logger.info(f"run_optimizer optimizer_cnt-{optimizer_cnt}, optimize region,{target_region}")
            logger.info(f"run_optimizer optimizer_cnt-{optimizer_cnt}, region_endpoint_level_rps: {region_endpoint_level_rps[target_region]}")
            frontend_ep_load_flag = False
            for frontend_ep in target_region_ingress_gw_rps:
                if target_region_ingress_gw_rps[frontend_ep] != 0:
                    logger.info(f"run_optimizer optimizer_cnt-{optimizer_cnt}, target_region: {target_region}, frontend endpoint: {frontend_ep}, rps: {target_region_ingress_gw_rps[frontend_ep]}")
                    frontend_ep_load_flag = True
                    break
            if frontend_ep_load_flag == False:
                logger.info(f"Skip optimizer optimizer_cnt-{optimizer_cnt} for {target_region}. all target_region_ingress_gw_rps == 0")
                for frontend_ep in target_region_ingress_gw_rps:
                    logger.info(f"run_optimizer optimizer_cnt-{optimizer_cnt}, target_region: {target_region}, frontend endpoint: {frontend_ep}, rps: {target_region_ingress_gw_rps[frontend_ep]}")
            else:
                logger.info(f"run_optimizer optimizer_cnt-{optimizer_cnt}, region: {target_region}, target_region_ingress_gw_rps: {target_region_ingress_gw_rps}")
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
                    logger.info(f"run_optimizer optimizer_cnt-{optimizer_cnt}, target_region: {target_region}")
                    logger.info(f"run_optimizer optimizer_cnt-{optimizer_cnt}, df_str: {df_str}")        
                    prev_remaining_capacity = copy.deepcopy(curr_remaining_capacity)
                    update_remaining_capacity(curr_remaining_capacity, pct_df)
                    for region in curr_remaining_capacity:
                        for svc in curr_remaining_capacity[region]:
                            if curr_remaining_capacity[region][svc] < 0:
                                logger.error(f"!!! ERROR !!!: curr_remaining_capacity[{region}][{svc}] < 0, {curr_remaining_capacity[region][svc]}")
                                assert False
                            # logger.info(f"run_optimizer optimizer_cnt-{optimizer_cnt}, region,{region}, svc,{svc}, remaining_capacity: {prev_remaining_capacity[region][svc]} ->  {curr_remaining_capacity[region][svc]}")
                else:
                    logger.info(f"pct_df: {pct_df}")
                    logger.error(f"!!! ERROR !!! FAIL. run_optimizer optimizer_cnt-{optimizer_cnt}, target_region: {target_region}. {desc}")
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
        # write_optimizer_output(optimizer_cnt, percentage_df, desc, "alternative_routing_history.csv")
        # write_optimizer_output(optimizer_cnt, concat_pct_df, desc, "concat_pct_df.csv")
    logger.info(f"after run_optimizer optimizer_cnt-{optimizer_cnt}")
    logger.info(f"run_optimizer optimizer_cnt-{optimizer_cnt}, result: {desc}")
    if percentage_df.empty:
        logger.error(f"ERROR: run_optimizer FAIL (**{desc}**) return without updating percentage_df")
    write_optimizer_output(optimizer_cnt, percentage_df, desc, "routing_history.csv")
    ''' end of optimizer_entrypoint '''


    

# def init_max_capacity_per_service(capacity):
#     global max_capacity_per_service
#     global svc_to_placement
#     global bottleneck_service
#     for svc in svc_to_placement:
#         if svc not in max_capacity_per_service:
#             max_capacity_per_service[svc] = dict()
#     for svc in svc_to_placement:
#         for region in svc_to_placement[svc]:
#             for region in all_endpoints:
#                 for svc in all_endpoints[region]:
#                     if svc not in max_capacity_per_service:
#                         max_capacity_per_service[svc] = dict()
#                     max_capacity_per_service[svc][region] = capacity
#             logger.debug(f"set max_capacity_per_service[{svc}][{region}] = {max_capacity_per_service[svc][region]}")

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
    all_endpoints = tst.get_all_endpoints(stitched_traces)
    endpoint_to_placement = set_endpoint_to_placement(all_endpoints)
    svc_to_placement = set_svc_to_placement(all_endpoints)
    placement = tst.get_placement_from_trace(stitched_traces)
    logger.info(f"Init all_endpoints: {all_endpoints}")
    logger.info(f"Init endpoint_to_placement: {endpoint_to_placement}")
    logger.info(f"Init svc_to_placement: {svc_to_placement}")
    logger.info(f"Init placement: {placement}")
    # endpoint_to_cg_key = tst.get_endpoint_to_cg_key_map(stitched_traces)
    # ep_str_callgraph_table, key: hashed cg_key
    # cg_key_hashmap, key: hashed_cg_key, value: cg_key (concat of all ep_str in sorted order)
    ep_str_callgraph_table, cg_key_hashmap = tst.traces_to_endpoint_str_callgraph_table(stitched_traces)
    logger.info(f"len(ep_str_callgraph_table: {len(ep_str_callgraph_table)}")
    print_ep_str_callgraph_table()
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


def aggregate_rps_by_region(per_pod_ep_rps):
    aggregate = dict()
    for region in per_pod_ep_rps:
        if region not in aggregate: aggregate[region] = dict()
        for svc in per_pod_ep_rps[region]:
            if svc not in aggregate[region]: aggregate[region][svc] = dict()
            for endpoint in per_pod_ep_rps[region][svc]:
                if endpoint not in aggregate[region][svc]: aggregate[region][svc][endpoint] = 0
                for podname in per_pod_ep_rps[region][svc][endpoint]:
                    ## scalability test
                    # aggregate[region][svc][endpoint] += 100
                    aggregate[region][svc][endpoint] += per_pod_ep_rps[region][svc][endpoint][podname]
    return aggregate

def aggregated_rps_routine():
    global per_pod_ep_rps
    global aggregated_rps
    global agg_root_node_rps
    global temp_counter
    global prev_ts
    
    for region in all_endpoints:
        for svc_name in all_endpoints[region]:
            for endpoint in all_endpoints[region][svc_name]:
                for podname in placement[region]:
                    if region not in per_pod_ep_rps:
                        per_pod_ep_rps[region] = dict()
                    if svc_name not in per_pod_ep_rps[region]:
                        per_pod_ep_rps[region][svc_name] = dict()
                    if endpoint not in per_pod_ep_rps[region][svc_name]:
                        per_pod_ep_rps[region][svc_name][endpoint] = dict()
                    # podname_list = ["pod1", "pod2", "pod3", "pod4"]
                    podname_list = ["pod1"]
                    for podname in podname_list:
                        if region == "cluster0":
                            per_pod_ep_rps[region][svc_name][endpoint][podname] = random.randint(1000, 1000)
                        else:
                            per_pod_ep_rps[region][svc_name][endpoint][podname] = random.randint(100, 100)
    aggregated_rps = aggregate_rps_by_region(per_pod_ep_rps)
    agg_root_node_rps = get_root_node_rps(ep_str_callgraph_table, aggregated_rps)
    logger.info(f"aggregated_rps: {aggregated_rps}")
    logger.info(f"agg_root_node_rps: {agg_root_node_rps}")

def gen(num_cluster, num_callgraph, depth, fanout):
    global coef_dict
    global endpoint_level_inflight
    global placement
    global all_endpoints
    global svc_to_placement
    global endpoint_to_placement
    global ep_str_callgraph_table
    global mode
    global train_done
    global traffic_segmentation
    global ROUTING_RULE
    global max_capacity_per_service
    global degree
    global inter_cluster_latency
    global objective
    
    mode = "runtime"
    train_done = True
    
    
    def create_node_name():
        input_string = str(random.randint(1,1000000))
        byte_string = input_string.encode("utf-8")
        md5_hash = hashlib.md5(byte_string).hexdigest()
        return str(md5_hash)[:4]
    
    def generate_tree(root_name, depth, fanout):
        def create_subtree(current_depth, parent_name):
            if current_depth == depth:
                return {parent_name: []}
            temp_children = [f"{parent_name}-{i}" for i in range(1, fanout + 1)]
            # logger.info("parent_name")
            # logger.info(parent_name)
            # logger.info("temp_children")
            # logger.info(temp_children)
            children = list()
            for temp_node in temp_children:
                tokens_in_node_name = temp_node.split('-')
                # new_node_name = ""
                # for i in range(len(tokens_in_node_name)):
                #     new_node_name += int(tokens_in_node_name[i])*(len(tokens_in_node_name)-i)
                new_node_name = create_node_name()
                children.append(str(new_node_name))
            # logger.info("parent_name")
            # logger.info(parent_name)
            # logger.info("children")
            # logger.info(children)
            subtree = {parent_name: children}
            for child in children:
                subtree.update(create_subtree(current_depth + 1, child))
                break
            return subtree
        tree = create_subtree(1, root_name)
        return tree
    
    temp_ep_str_callgraph_table = dict()
    root_name = create_node_name()  # Root node's name
    temp_ep_str_callgraph_table = generate_tree(root_name, depth, fanout)
    
    replicated_temp_ep_str_callgraph_table = dict()
    for idx in range(num_callgraph):
        replicated_temp_ep_str_callgraph_table[str(idx)] = copy.deepcopy(temp_ep_str_callgraph_table)
    
    ep_str_callgraph_table = dict()
    for cg_key in replicated_temp_ep_str_callgraph_table:
        if cg_key not in ep_str_callgraph_table:
            ep_str_callgraph_table[cg_key] = dict()
        for temp_parent, temp_children in temp_ep_str_callgraph_table.items():
            parent = f"s{temp_parent}@m{cg_key}@e{cg_key}"
            for temp_child in temp_children:
                child = f"s{temp_child}@m{cg_key}@e{cg_key}"
                if parent not in ep_str_callgraph_table[cg_key]:
                    ep_str_callgraph_table[cg_key][parent] = list()
                if child not in ep_str_callgraph_table[cg_key]:
                    ep_str_callgraph_table[cg_key][child] = list() # in case it is leaf node
                ep_str_callgraph_table[cg_key][parent].append(child)
    logger.info("temp_ep_str_callgraph_table")
    logger.info(temp_ep_str_callgraph_table)
    logger.info("replicated_temp_ep_str_callgraph_table")
    logger.info(replicated_temp_ep_str_callgraph_table)
    logger.info("ep_str_callgraph_table")
    logger.info(ep_str_callgraph_table)
    
    cluster_list = list()
    for i in range(num_cluster):
        cluster_list.append(f"cluster{i}")
    logger.info("cluster_list")
    logger.info(cluster_list)
    
    all_endpoints = dict()
    for cid in cluster_list:
        for cg_key in ep_str_callgraph_table:
            for parent_endpoint in ep_str_callgraph_table[cg_key]:
                parent_svc = parent_endpoint.split("@")[0]
                if cid not in all_endpoints:
                    all_endpoints[cid] = dict()
                if parent_svc not in all_endpoints[cid]:
                    all_endpoints[cid][parent_svc] = set()
                all_endpoints[cid][parent_svc].add(parent_endpoint)
    logger.info("all_endpoints")
    logger.info(all_endpoints)
    
    coef_dict = dict()
    for cid in all_endpoints:
        for svc_name in all_endpoints[cid]:
            if svc_name not in coef_dict:
                coef_dict[svc_name] = dict()
            for ep_str in all_endpoints[cid][svc_name]:
                coef_dict[svc_name][ep_str] = dict()
                coef_dict[svc_name][ep_str]["intercept"] = 0
                coef_dict[svc_name][ep_str][ep_str] = 1
    logger.info("coef_dict")
    logger.info(coef_dict)
    
    placement = dict()
    for cid in all_endpoints:
        if cid not in placement:
            placement[cid] = set()
        for svc_name in all_endpoints[cid]:
            placement[cid].add(svc_name)
    
    endpoint_to_placement = set_endpoint_to_placement(all_endpoints)
    logger.info("endpoint_to_placement")
    logger.info(endpoint_to_placement)
    logger.info(len(endpoint_to_placement))
    
    svc_to_placement = set_svc_to_placement(all_endpoints)
    logger.info("svc_to_placement")
    logger.info(svc_to_placement)
    logger.info(len(svc_to_placement))
    traffic_segmentation = True
    objective = "avg_latency"
    ROUTING_RULE = "SLATE"
    
    for region in all_endpoints:
        for svc in all_endpoints[region]:
            if svc not in max_capacity_per_service:
                max_capacity_per_service[svc] = dict()
            max_capacity_per_service[svc][region] = 1000*num_cluster
    logger.info("max_capacity_per_service")
    logger.info(max_capacity_per_service)
    
    
    for src_cid in cluster_list:
        if src_cid not in inter_cluster_latency:
            inter_cluster_latency[src_cid] = dict()
        for dst_cid in cluster_list:
            if src_cid != dst_cid:
                inter_cluster_latency[src_cid][dst_cid] = random.randint(5, 50)
            else:
                inter_cluster_latency[src_cid][dst_cid] = 0
    logger.info("inter_cluster_latency")
    logger.info(inter_cluster_latency)
    
import sys
if __name__ == "__main__":
    num_cluster = int(sys.argv[1])
    num_callgraph = int(sys.argv[2])
    depth = int(sys.argv[3])
    fanout = int(sys.argv[4])
    degree_ = int(sys.argv[5])
    gen(num_cluster, num_callgraph, depth, fanout)
    aggregated_rps_routine()
    optimizer_entrypoint(degree_, fanout)