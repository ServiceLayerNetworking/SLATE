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
CAPACITY = 0 # If it is runtime -> training_phase() -> max_capacity_per_service() -> set max_capacity_per_service[svc] = CAPACITY
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
        if serviceName.find("metrics-handler") != -1:
            bodySize = 5000
            logger.debug(f"Rewriting bodySize: {bodySize}, svc: {serviceName}, method: {method}, path: {path}")
        else:
            bodySize = 50
            logger.debug(f"Rewriting bodySize: {bodySize}, svc: {serviceName}, method: {method}, path: {path}")
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
        assert row['src_endpoint'] in aggregated_rps[row['src_cid']][row['src_svc']]
        assert row['dst_endpoint'] in aggregated_rps[row['dst_cid']][row['dst_svc']]
        assert row['src_endpoint'].split(cfg.ep_del)[0] == row['src_svc']
        assert row['dst_endpoint'].split(cfg.ep_del)[0] == row['dst_svc']
        assert row['src_cid'] == src_region
        
    return_df = return_df.drop(columns=['src_svc', "dst_svc", "flow", "total"])
    desired_order_of_columns = ['src_endpoint', 'dst_endpoint', 'src_cid', 'dst_cid', 'weight']
    # Select only the columns to keep from the DataFrame
    return_df = return_df.loc[:, desired_order_of_columns] 
    # make sure it has CORRECT order of columns to comply with wasm api
    return_df = return_df[desired_order_of_columns]
    assert list(return_df.columns) == desired_order_of_columns
    return return_df

# @app.route("/clusterLoad", methods=["POST"]) # from cluster-controller
@app.post('/proxyLoad') # from wasm
def handleProxyLoad():
    global aggregated_rps
    global endpoint_level_inflight
    global percentage_df
    # global trace_str_list
    global ROUTING_RULE
    global mode
    global list_of_span
    global stats_mutex
    global endpoint_rps_history
    global endpoint_level_rps_mutex
    
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
    request body format:
    service_level_rps at OnTick time
    endpoint,endpoint_level_rps,endpoint_level_rps|...| at OnTick time
    requestStat-1
    requestStat-2
    requestStat-3
    
    e.g.,
    54 
    GET@/start,0,12|POST@/upload,0,34|
    us-west-1 metrics-fake-ingress-us-west-1 GET /start 70904b1c08f35622387a6bb5c9141596 387a6bb5c9141596  1709763447436 1709763447540 0 GET@/start,0,18446744073709530962|
    us-west-1 metrics-fake-ingress-us-west-1 GET /start 8b869b12bba09c5e3843e396eeab84b5 3843e396eeab84b5  1709763447465 1709763447512 0 GET@/start,0,18446744073709530962|
    us-west-1 metrics-fake-ingress-us-west-1 GET /start 4d098d189169f0f7e07e75c587d4c608 e07e75c587d4c608  1709763447751 1709763447814 0 GET@/start,0,18446744073709530944|
    us-west-1 metrics-fake-ingress-us-west-1 GET /start d3c0c9e72a315edce2e118bb2d7be53d e2e118bb2d7be53d  1709763447856 1709763447929 0 GET@/start,0,18446744073709530939|
    '''
    logger.debug(f"svc: {svc}, region: {region}")
    
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
        global optimizer_cnt
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
                csv_string = temp_df.to_csv(header=False, index=False)
                assert csv_string != ""
                logger.debug(f"Enforcement, {ROUTING_RULE}, optimizer_cnt-{optimizer_cnt}, {full_podname} in {region}\n{csv_string.strip()}")
            else:
                _, csv_string = local_and_failover_routing_rule(svc, region)
                
            # logger.info(f"Enforcement, {ROUTING_RULE}, optimizer_cnt-{optimizer_cnt}, {full_podname} in {region}, {csv_string.strip()}")
            with open(f'percentage_df-{svc}.csv', 'a') as f:
                f.write(csv_string)
            return csv_string
        elif ROUTING_RULE == "SLATE" or ROUTING_RULE == "WATERFALL":
            # NOTE: remember percentage_df is set by 'optimizer_entrypoint' async function
            if type(percentage_df) == type(None):
                logger.debug(f"optimizer never succeeds yet. Rollback to local routing. {full_podname}, {region}")
                _, csv_string = local_and_failover_routing_rule(svc, region)
                return csv_string
            global train_done
            if train_done == False:
                _, csv_string = local_and_failover_routing_rule(svc, region)
                return csv_string
            if percentage_df.empty:
                logger.debug(f"WARNING, Rollback to local routing. {region}, {full_podname}, percentage_df is empty. rollback to local routing")
                _, csv_string = local_and_failover_routing_rule(svc, region)
                return csv_string
            else:
                temp_df = percentage_df.loc[(percentage_df['src_svc'] == svc) & (percentage_df['src_cid'] == region)].copy()
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
                        logger.info(f"Enforcement,{ROUTING_RULE}, optimizer_cnt-{optimizer_cnt}, {full_podname} in {region}\n{csv_string.strip()}")
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

def fill_local_first(src_region, remaining_src_region_src_svc_rps, waterfall_load_balance, src_svc="slate-ingress", dst_svc="frontend"):
    global max_capacity_per_service
    global optimizer_cnt
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
    logger.info(f"{optimizer_cnt},waterfall2,{src_svc},{dst_svc},{src_region},{dst_region},{waterfall_load_balance[src_region][dst_region]}")
    logger.debug(f"{optimizer_cnt},waterfall2,src remaining_src_region_src_svc_rps[{src_region}]: {src_original_demand},{remaining_src_region_src_svc_rps[src_region]}")
    logger.debug(f"{optimizer_cnt},waterfall2,dst max_capacity_per_service[{dst_svc}][{dst_region}]: {dst_original_cap},{max_capacity_per_service[dst_svc][dst_region]}")
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
                logger.info(f"{optimizer_cnt},waterfall2,{src_svc},{dst_svc},{src_region},{dst_region},{remaining_src_region_src_svc_rps[src_region]}")
                if src_region not in waterfall_load_balance:
                    waterfall_load_balance[src_region] = dict()
                waterfall_load_balance[src_region][dst_region] = remaining_src_region_src_svc_rps[src_region]
                src_orignal_demand = remaining_src_region_src_svc_rps[src_region]
                remaining_src_region_src_svc_rps[src_region] = 0
                logger.debug(f"{optimizer_cnt},waterfall2,src remaining_src_region_src_svc_rps[{src_region}]: {src_orignal_demand},{remaining_src_region_src_svc_rps[src_region]}")
                logger.debug(f"{optimizer_cnt},waterfall2,dst max_capacity_per_service[{dst_svc}][{dst_region}]: {original_cap},{max_capacity_per_service[dst_svc][dst_region]}")
                break
            else:
                logger.debug(f"{optimizer_cnt},waterfall2,max_capacity_per_service[{dst_svc}][{dst_region}] < remaining_src_region_src_svc_rps[{src_region}]({remaining_src_region_src_svc_rps[src_region]})")
                if src_region not in waterfall_load_balance:
                    waterfall_load_balance[src_region] = dict()
                waterfall_load_balance[src_region][dst_region] = max_capacity_per_service[dst_svc][dst_region]
                src_original_demand = remaining_src_region_src_svc_rps[src_region]
                remaining_src_region_src_svc_rps[src_region] -= max_capacity_per_service[dst_svc][dst_region]
                dst_original_cap = max_capacity_per_service[dst_svc][dst_region]
                max_capacity_per_service[dst_svc][dst_region] = 0
                logger.info(f"{optimizer_cnt},waterfall2,{src_region},{dst_region},{dst_original_cap},{max_capacity_per_service[dst_svc][dst_region]}")
                logger.debug(f"{optimizer_cnt},waterfall2,src remaining_src_region_src_svc_rps[{src_region}]: {src_original_demand},{remaining_src_region_src_svc_rps[src_region]}")
                logger.debug(f"{optimizer_cnt},waterfall2,dst max_capacity_per_service[{dst_svc}][{dst_region}]: {max_capacity_per_service[dst_svc][dst_region]}")
                if remaining_src_region_src_svc_rps[src_region] == 0:
                    logger.debug(f"{optimizer_cnt},waterfall2 for {src_region}, {src_svc} is done. break and return")
                    break
    return waterfall_load_balance

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
def optimizer_entrypoint(degree, fanout):
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
            for svc in max_capacity_per_service:
                for region in max_capacity_per_service[svc]:
                    max_capacity_per_service[svc][region] = 100000
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
            degree, \
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

def load_coef():
    loaded_coef = dict()
    df = pd.read_csv(f"coef.csv")
    for svc_name in df["svc_name"].unique():
        if svc_name not in loaded_coef:
            loaded_coef[svc_name] = dict()
        svc_df = df[df["svc_name"]==svc_name]
        for endpoint in svc_df["endpoint"].unique():
            if endpoint not in loaded_coef[svc_name]:
                loaded_coef[svc_name][endpoint] = dict()
            ep_df = svc_df[svc_df["endpoint"]==endpoint]
            for index, row in ep_df.iterrows():
                loaded_coef[svc_name][endpoint][row["feature"]] = float(row["value"])
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
    col = ["cluster_id","svc_name","method","path","trace_id","span_id","parent_span_id","st","et","rt","xt","ct","call_size","inflight_dict","rps_dict"]
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
            
        rps_list = row["rps_dict"].split("|")[:-1]
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
        
        if load_coef_flag:
            exclusive_time = int(row["xt"])
            # span = sp.Span(row["method"], row["path"], row["svc_name"], row["cluster_id"], \
            #     row["trace_id"], row["span_id"], row["parent_span_id"], \
            #         st=float(row["st"]), et=float(row["et"]), xt=, \
            #             callsize=int(row["call_size"]), \
            #                 rps_dict=rps_dict, \
            #                     num_inflight_dict=num_inflight_dict)
        else:
            exclusive_time = -1
            # span = sp.Span(row["method"], row["path"], row["svc_name"], row["cluster_id"], \
            #     row["trace_id"], row["span_id"], row["parent_span_id"], \
            #         st=float(row["st"]), et=float(row["et"]), xt=-1, \
            #             callsize=int(row["call_size"]), \
            #                 rps_dict=rps_dict, \
            #                     num_inflight_dict=num_inflight_dict)
        span = sp.Span(row["method"], row["path"], row["svc_name"], row["cluster_id"], \
                row["trace_id"], row["span_id"], row["parent_span_id"], \
                st=float(row["st"]), et=float(row["et"]), xt=exclusive_time, \
                callsize=int(row["call_size"]), \
                rps_dict=rps_dict, \
                num_inflight_dict=num_inflight_dict)
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
    if not check_file_exist(trainig_input_trace_file):
        return

    if init_done:
        return
    if load_coef_flag: # load_coef_flag=True assumes that time stitching is done
        stitched_traces = trace_string_file_to_trace_data_structure(load_coef_flag)
    else:
        traces = trace_string_file_to_trace_data_structure(load_coef_flag)
        complete_traces = filter_incomplete_traces(traces)
        stitched_traces = tst.stitch_time(complete_traces)
    for region in ["us-east-1", "us-south-1", "us-central-1"]:
        if region not in stitched_traces:
            stitched_traces[region] = stitched_traces["us-west-1"].copy()
                        
    initialize_global_datastructure(stitched_traces=stitched_traces)
    init_done = True
    
    if mode != "runtime":
        logger.debug(f"It is not runtime mode. Skip training. current mode: {mode}")
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
        coef_dict = load_coef()
        for svc_name in coef_dict:
            for ep_str in coef_dict[svc_name]:
                for feature_ep in coef_dict[svc_name][ep_str]:
                    # if feature_ep in coef_dict[svc_name][ep_str]:
                    #     coef_dict[svc_name][ep_str][feature_ep] = coef_dict[svc_name][ep_str][feature_ep]
                    logger.info(f"coef_dict[{svc_name}][{ep_str}][{feature_ep}]: {coef_dict[svc_name][ep_str][feature_ep]}")
    else:
        coef_dict = train_latency_function_with_trace(stitched_traces, degree)
    
    check_negative_coef(coef_dict)      
    if ROUTING_RULE == "WATERFALL" or ROUTING_RULE == "WATERFALL2":
        set_zero_coef(coef_dict)
                        
    with open("coefficient.csv", "w") as f:
        f.write("svc_name, endpoint, coef\n")
        for svc_name in coef_dict:
            for ep_str in coef_dict[svc_name]:
                logger.info(f'final coef_dict[{svc_name}][{ep_str}]: {coef_dict[svc_name][ep_str]}')
                f.write(f'{svc_name},{ep_str},{coef_dict[svc_name][ep_str]}\n')
                        
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
    
    with open("env.txt", "r") as file:
        lines = file.readlines()
        for line in lines:
            line = line.strip().split(",")
            if line[0] == "benchmark_name":
                if benchmark_name != line[1]:
                    logger.info(f'Update benchmark_name: {benchmark_name} -> {line[1]}')
                    benchmark_name = line[1]
                    ###################################################################
                    if benchmark_name == "usecase1-howmuch" or benchmark_name == "usecase1-whichcluster" or benchmark_name == "usecase1-orderofevent" or benchmark_name == "usecase1-cascading":
                        parent_of_bottleneck_service = "frontend"
                        bottleneck_service = "a"
                    elif benchmark_name == "usecase3-compute-diff":
                        bottleneck_service = "compute-node"
                    elif benchmark_name == "hotelreservation":
                        parent_of_bottleneck_service = "slateingress"
                        bottleneck_service = "frontend"
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
                src = line[1]
                dst = line[2]
                oneway_latency = int(line[3])
                if src not in inter_cluster_latency:
                    inter_cluster_latency[src] = dict()
                # if dst not in inter_cluster_latency:
                #     inter_cluster_latency[dst] = dict()
                inter_cluster_latency[src][dst] = oneway_latency
                # inter_cluster_latency[dst][src] = oneway_latency
                logger.debug(f'Update inter_cluster_latency: {src} -> {dst}: {oneway_latency}')
            elif line[0] == "load_coef_flag":
                if load_coef_flag != int(line[1]):
                    logger.info(f'Update load_coef_flag: {load_coef_flag} -> {int(line[1])}')
                    load_coef_flag = int(line[1])
            else:
                logger.debug(f"ERROR: unknown config: {line}")
    logger.debug(f"benchmark_name: {benchmark_name}, total_num_services: {total_num_services}, mode: {mode}, ROUTING_RULE: {ROUTING_RULE}")


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
    # logger.info("-"*80)
    # for region in per_pod_ep_rps:
    #     for svc in per_pod_ep_rps[region]:
    #         for endpoint in per_pod_ep_rps[region][svc]:
    #             for podname in per_pod_ep_rps[region][svc][endpoint]:
    #                 logger.info(f"per_pod_ep_rps,{region},{svc},{endpoint},{podname},{per_pod_ep_rps[region][svc][endpoint][podname]}")
    # logger.info("-"*80)
    # for region in aggregate:
    #     for svc in aggregate[region]:
    #         for endpoint in aggregate[region][svc]:
    #             logger.info(f"aggregate,{region},{svc},{endpoint},{aggregate[region][svc][endpoint]}")
    # logger.info("-"*80)
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
                    podname_list = ["pod1", "pod2", "pod3", "pod4"]
                    for podname in podname_list:
                        per_pod_ep_rps[region][svc_name][endpoint][podname] = random.randint(50, 1000)
    aggregated_rps = aggregate_rps_by_region(per_pod_ep_rps)
    agg_root_node_rps = get_root_node_rps(ep_str_callgraph_table, aggregated_rps)
    logger.info(f"aggregated_rps: {aggregated_rps}")
    logger.info(f"agg_root_node_rps: {agg_root_node_rps}")
    ## scalability test
    # if check_root_node_rps_condition(agg_root_node_rps) or temp_counter > 0:
    if True:
        record_endpoint_rps(aggregated_rps, temp_counter)
        
        logger.info("-"*80)
        # logger.info(f"aggregated_rps_routine, temp_counter-{temp_counter}, gap: {time.time()-prev_ts}")
        prev_ts = time.time()
        for region in agg_root_node_rps:
            for svc in agg_root_node_rps[region]:
                for endpoint in agg_root_node_rps[region][svc]:
                    logger.info(f"agg_root_node_rps,{region},{svc},{endpoint},{agg_root_node_rps[region][svc][endpoint]}")
        logger.info("-"*80)
        temp_counter += 1

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
            # print("parent_name")
            # print(parent_name)
            # print("temp_children")
            # print(temp_children)
            children = list()
            for temp_node in temp_children:
                tokens_in_node_name = temp_node.split('-')
                # new_node_name = ""
                # for i in range(len(tokens_in_node_name)):
                #     new_node_name += int(tokens_in_node_name[i])*(len(tokens_in_node_name)-i)
                new_node_name = create_node_name()
                children.append(str(new_node_name))
            # print("parent_name")
            # print(parent_name)
            # print("children")
            # print(children)
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
    print("temp_ep_str_callgraph_table")
    pprint(temp_ep_str_callgraph_table)
    print("replicated_temp_ep_str_callgraph_table")
    pprint(replicated_temp_ep_str_callgraph_table)
    print("ep_str_callgraph_table")
    pprint(ep_str_callgraph_table)
    
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
    logger.info("placement")
    logger.info(placement)
    
    endpoint_to_placement = set_endpoint_to_placement(all_endpoints)
    print("endpoint_to_placement")
    pprint(endpoint_to_placement)
    pprint(len(endpoint_to_placement))
    
    svc_to_placement = set_svc_to_placement(all_endpoints)
    print("svc_to_placement")
    pprint(svc_to_placement)
    pprint(len(svc_to_placement))
    exit()
    traffic_segmentation = True
    objective = "avg_latency"
    ROUTING_RULE = "SLATE"
    degree = 2
    
    for region in all_endpoints:
        for svc in all_endpoints[region]:
            if svc not in max_capacity_per_service:
                max_capacity_per_service[svc] = dict()
            max_capacity_per_service[svc][region] = 100000
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
    # read_config_file()
    # write_spans_to_file()
    # training_phase()
    num_cluster = int(sys.argv[1])
    num_callgraph = int(sys.argv[2])
    depth = int(sys.argv[3])
    fanout = int(sys.argv[4])
    degree = int(sys.argv[5])
    # print(f"num_cluster: {num_cluster}, num_callgraph: {num_callgraph}, depth: {depth}, fanout: {fanout}")
    gen(num_cluster, num_callgraph, depth, fanout)
    aggregated_rps_routine()
    optimizer_entrypoint(degree, fanout)