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
import gen_trace
from IPython.display import display
from pprint import pprint
import random
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
import datetime
import os
import math
# import matplotlib.pyplot as plt
import numpy as np
# import logging.config

logging.config.dictConfig(cfg.LOGGING_CONFIG)
# logging.basicConfig(level=logging.INFO)
# logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask(__name__)
logger = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)
logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)


'''runtime (optimizer)'''
endpoint_level_inflight = {}
endpoint_level_rps = {}
endpoint_to_cg_key = {}
ep_str_callgraph_table = {}
# sp_callgraph_table = {}
all_endpoints = {}
placement = {}
coef_dict = {}
degree = 0
endpoint_to_placement = dict()
svc_to_placement = dict()
percentage_df = None
optimizer_cnt = 0
stats_mutex = Lock()

'''profiling (training)'''
list_of_span = list() # unorganized list of spanss
complete_traces = dict() # filtered traces
train_done = False
# trace_str_list = list() # internal data structure of traces before writing it to a file
profile_output_file="trace_string.csv" # traces_str_list -> profile_output_file in write_trace_str_to_file() function every 5s
latency_func = {}
trainig_input_trace_file="trace.slatelog" # NOTE: It should be updated when the app is changed
x_feature = "rps_dict" # "num_inflight_dict"
target_y = "xt"

'''config'''
mode = ""
MODE_SET = ["profile", "runtime", "before_start"]
benchmark_name = ""
benchmark_set = ["metrics-app", "matmul-app", "hotelreservation"]
total_num_services = 0
ROUTING_RULE = "LOCAL" # It will be updated by read_config_file function.
ROUTING_RULE_SET = ["LOCAL", "SLATE", "REMOTE", "MCLB", "WATERFALL"]
CAPACITY = 0 # If it is runtime -> training_phase() -> calc_max_load_per_service() -> set max_load_per_service[svc] = CAPACITY
max_load_per_service = dict() # key: service_name, value: max RPS


def set_endpoint_to_placement(all_endpoints):
    endpoint_to_placement = dict()
    for cid in all_endpoints:
        for svc_name in all_endpoints[cid]:
            for ep in all_endpoints[cid][svc_name]:
                if ep not in endpoint_to_placement:
                    endpoint_to_placement[ep] = set()
                endpoint_to_placement[ep].add(cid)
    logger.debug('endpoint_to_placement')
    logger.debug(f'{endpoint_to_placement}')
    return endpoint_to_placement

def set_svc_to_placement(all_endpoints):
    svc_to_placement = dict()
    for cid in all_endpoints:
        for svc_name in all_endpoints[cid]:
            if svc_name not in svc_to_placement:
                svc_to_placement[svc_name] = set()
            svc_to_placement[svc_name].add(cid)
    logger.debug('svc_to_placement')
    logger.debug(f'{svc_to_placement}')
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
def get_local_routing_rule(src_svc, src_cid):
    global ep_str_callgraph_table
    global endpoint_to_placement
    if len(ep_str_callgraph_table) == 0:
        logger.error(f"ERROR: ep_str_callgraph_table is empty.")
        return ""
    df = pd.DataFrame(columns=["src_endpoint", "dst_endpoint", "src_cid", "dst_cid", "weight"])
    for cg_key in ep_str_callgraph_table:
        for parent_ep_str in ep_str_callgraph_table[cg_key]:
            if parent_ep_str.split(cfg.ep_del)[0] != src_svc:
                continue
            for child_ep_str in ep_str_callgraph_table[cg_key][parent_ep_str]:
                dst_cid_list = endpoint_to_placement[child_ep_str]
                for dst_cid in dst_cid_list:
                    if src_cid == dst_cid:
                        new_row = {"src_endpoint": parent_ep_str, "dst_endpoint": child_ep_str, "src_cid": src_cid, "dst_cid": dst_cid, "weight": 1.0}
                        new_row_df = pd.DataFrame([new_row])
                        df = pd.concat([df, new_row_df], ignore_index=True)
                    else:
                        new_row = {"src_endpoint": parent_ep_str, "dst_endpoint": child_ep_str, "src_cid": src_cid, "dst_cid": dst_cid, "weight": 0.0}
                        new_row_df = pd.DataFrame([new_row])
                        df = pd.concat([df, new_row_df], ignore_index=True)
    csv_string = df.to_csv(header=False, index=False)
    logger.info(f"routing rule, LOCAL: {src_svc}, {src_cid}\n{csv_string}")
    return csv_string

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
    for cg_key in ep_str_callgraph_table:
        for parent_ep_str in ep_str_callgraph_table[cg_key]:
            if parent_ep_str.split(cfg.ep_del)[0] != src_svc:
                continue
            for child_ep_str in ep_str_callgraph_table[cg_key][parent_ep_str]:
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
    logger.info(f"routing rule, REMOTE: {src_svc}, {src_cid}\n{csv_string}")
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
    for cg_key in ep_str_callgraph_table:
        for parent_ep_str in ep_str_callgraph_table[cg_key]:
            if parent_ep_str.split(cfg.ep_del)[0] != src_svc:
                continue
            for child_ep_str in ep_str_callgraph_table[cg_key][parent_ep_str]:
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
    logger.info(f"routing rule, MCLB: {src_svc}, {src_cid}\n{csv_string}")
    return csv_string


def parse_inflight_stats(body):
    # logger.info(f"{cfg.log_prefix} body: {body}")
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
            logger.error(f"ERROR, len(ss) != 11, (len(ss):{len(ss)}, ss:{ss})")
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
            logger.debug(f"{cfg.log_prefix} Rewriting bodySize: {bodySize}, svc: {serviceName}, method: {method}, path: {path}")
        else:
            bodySize = 50
            logger.debug(f"{cfg.log_prefix} Rewriting bodySize: {bodySize}, svc: {serviceName}, method: {method}, path: {path}")
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
        spans.append(sp.Span(method, path, serviceName, region, traceId, spanId, parentSpanId, startTime, endTime, bodySize, rps_dict=rps_dict, num_inflight_dict=inflight_dict))
        # logger.info(f"{cfg.log_prefix} new span parsed. serviceName: {serviceName}, bodySize: {bodySize}")
    return spans


def write_spans_to_file():
    global mode
    global profile_output_file
    global list_of_span
    if mode == "profile":
        if len(list_of_span) > 0:
            with stats_mutex:
                with open(profile_output_file, "w") as file:
                    for span in list_of_span:
                        file.write(str(span)+"\n")
            logger.debug(f"{cfg.log_prefix} write_trace_str_to_file happened.")
    

# @app.route("/clusterLoad", methods=["POST"]) # from cluster-controller
@app.post('/proxyLoad') # from wasm
def handleProxyLoad():
    global endpoint_level_rps
    global endpoint_level_inflight
    global percentage_df
    # global trace_str_list
    global ROUTING_RULE
    global mode
    global list_of_span
    global stats_mutex
    
    svc = request.headers.get('x-slate-servicename')
    if svc.find("-us-") != -1:
            svc = svc.split("-us-")[0]
    if svc == "slate-controller":
        logger.debug(f"{cfg.log_prefix} WARNING: skip slate-controller in handleproxy")
        return ""
    
    region = request.headers.get('x-slate-region')
    if region == "SLATE_UNKNOWN_REGION":
        logger.debug(f"{cfg.log_prefix} WARNING: skip SLATE_UNKNOWN_REGION in handleproxy")
        return ""
    
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
    logger.debug(f"{cfg.log_prefix} svc: {svc}, region: {region}")
    if region not in endpoint_level_rps:
        endpoint_level_rps[region] = dict()
    if svc not in endpoint_level_rps[region]:
        endpoint_level_rps[region][svc] = dict()
        logger.info(f"Init endpoint_level_rps[{region}][{svc}]")
    if region not in endpoint_level_inflight:
        endpoint_level_inflight[region] = dict()
    if svc not in endpoint_level_inflight[region]:
        endpoint_level_inflight[region][svc] = dict()
        logger.info(f"Init endpoint_level_inflight[{region}][{svc}]")
    
    inflightStats = parse_inflight_stats(body)
    # When there is no load in this service
    if inflightStats == "":
        for ep in endpoint_level_rps[region][svc]:
            endpoint_level_rps[region][svc][ep] = 0
        for ep in endpoint_level_inflight[region][svc]:
            endpoint_level_inflight[region][svc][ep] = 0
        # logger.info(f"{cfg.log_prefix} {svc} inflightStats is empty")
        # logger.info(f"{cfg.log_prefix} Init entire inflight and rps to 0")
        # return ""
    
    # inflightStats: "GET@/start,4,1|POST@/start,4,1|"
    # METHOD1@URL1,RPS,INFLIGHT|METHOD2@URL2,RPS,INFLIGHT|...|
    logger.debug(f"{cfg.log_prefix} inflightStats: {inflightStats}")
    # endpoints of this service which has load now
    # E.g., there could be three endpoints(GET,POST,PUT) in the Service A and only GET,POST have load now. Then, active_endpoint_stats will be "GET,4,1|POST,10,2|"
    active_endpoint_stats = inflightStats.split("|")[:-1]
    logger.debug(f"{cfg.log_prefix} active_endpoint_stats: {active_endpoint_stats}")
    
    '''
    TODO: parse_service_level_rps should be updated to ontick per endpoint level rps
    '''
    svc_level_rps = parse_service_level_rps(body)
    for endpoint_stat in active_endpoint_stats:
        # E.g., endpoint_stat: GET@/start,4,1
        logger.info(f"{cfg.log_prefix} endpoint_stats: {endpoint_stat}")
        method_and_url = endpoint_stat.split(",")[0] # GET@/start
        method = method_and_url.split("@")[0] # GET
        url = method_and_url.split("@")[1] # /start
        ontick_rps = int(endpoint_stat.split(",")[1]) # 4
        ontick_inflight = int(endpoint_stat.split(",")[2]) # 1
        endpoint = svc + cfg.ep_del + method_and_url
        
        '''
        Setting endpoint_level_rps
        TODO: ontick_rps should be fixed in wasm'''
        ## set per endpoint rps at OnTick function call time
        endpoint_level_rps[region][svc][endpoint] = svc_level_rps
        # endpoint_level_rps[region][svc][endpoint] = ontick_rps # TODO: correct metric
        
        endpoint_level_inflight[region][svc][endpoint] = ontick_inflight # NOTE: not used
    

    # debug print
    for ep in endpoint_level_rps[region][svc]:
        logger.debug(f"{cfg.log_prefix} endpoint_level_rps: {region}, {svc}, {ep}, {endpoint_level_rps[region][svc][ep]}")
    for ep in endpoint_level_inflight[region][svc]:
        logger.debug(f"{cfg.log_prefix} endpoint_level_inflight: {region}, {svc}, {ep}, {endpoint_level_inflight[region][svc][ep]}")
        
    if mode == "profile":
        spans = parse_stats_into_spans(body, svc)
        for span in spans:
            list_of_span.append(span) # it will be written into a file in write_spans_to_file() function
        csv_string = get_local_routing_rule(svc, region) # response to wasm
        
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
        # ''' Generate fake load stat '''
        # endpoint_level_inflight = gen_endpoint_level_inflight(all_endpoints)
        # endpoint_level_rps = gen_endpoint_level_rps(all_endpoints)
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
        logger.info(f'ROUTING_RULE: {ROUTING_RULE}')
        if ROUTING_RULE == "LOCAL":
            csv_string = get_local_routing_rule(svc, region)
        elif ROUTING_RULE == "REMOTE":
            csv_string = always_remote_routing_rule(svc, region)
        elif ROUTING_RULE == "MCLB":
            csv_string = MCLB_routing_rule(svc, region)
        elif ROUTING_RULE == "SLATE" or ROUTING_RULE == "WATERFALL":
            # NOTE: remember percentage_df is set by 'optimizer_entrypoint' async function
            if percentage_df.empty:
                logger.info(f"{svc}, {region}, percentage_df is empty. rollback to local routing")
                csv_string = get_local_routing_rule(svc, region)
            else:
                logger.info(f"{svc}, {region}, percentage_df is not empty")
                temp_df = percentage_df.loc[(percentage_df['src_svc'] == svc) & (percentage_df['src_cid'] == region)].copy()
                # temp_df = temp_df.loc[(temp_df['src_cid'] == region)]
                # logger.info(f"{cfg.log_prefix} handleProxyLoad df after filtering, temp_df: {temp_df}")
                if len(temp_df) == 0:
                    logger.error(f"{cfg.log_prefix} ERROR: {region}, {svc}. percentage_df becomes empty after filtering.\nrollback to local routing")
                    csv_string = get_local_routing_rule(svc, region)
                else:
                    ## Add_region_back_to_svc_name
                    # temp_df['src_endpoint'] = temp_df['src_endpoint'].str.replace(r'([^@]+)', fr'\1-{temp_df["src_cid"]}', n=1, regex=True)
                    # temp_df['dst_endpoint'] = temp_df['dst_endpoint'].str.replace(r'([^@]+)', fr'\1-{temp_df["dst_cid"]}', n=1, regex=True)
                    temp_df = temp_df.drop(columns=['src_svc', "dst_svc"])
                    temp_df = temp_df.reset_index(drop=True)
                    temp_df.to_csv(f'percentage_df-{svc}-{region}.csv')
                    csv_string = temp_df.to_csv(header=False, index=False)
                    logger.info(f"{cfg.log_prefix} new routing rule! percentage_df-{svc}-{region}.csv")
        else:
            logger.error(f"ERROR: ROUTING_RULE is not supported yet. ROUTING_RULE: {ROUTING_RULE}")
            assert False
        ''' end of if mode == runtime '''
    else:
        logger.error(f"ERROR: Invalid. mode: {mode}")
        assert False
    if csv_string != "":    
        logger.info(f'ROUTING_RULE: {ROUTING_RULE}, csv_string updated for {svc} in {region}: \n{csv_string}')
        # with open(f'csv_string-{svc}-{region}.txt', 'w') as f:
        #     f.write(csv_string)
    else:
        logger.error(f"ERROR: csv_string is empty")
    return csv_string


## All variables are global variables
def optimizer_entrypoint():
    global coef_dict
    global endpoint_level_inflight
    global endpoint_level_rps
    global placement
    global all_endpoints
    global svc_to_placement
    global endpoint_to_placement
    global endpoint_to_cg_key
    # global sp_callgraph_table
    global ep_str_callgraph_table
    global percentage_df
    global ROUTING_RULE
    global traffic_segmentation
    global objective
    global max_load_per_service
    global mode
    global optimizer_cnt
    global degree
    
    if mode != "runtime":
        logger.info(f"run optimizer only in runtime mode. current mode: {mode}. return optimizer_entrypoint without executing optimizer...")
        return
    
    if ROUTING_RULE != "SLATE" and ROUTING_RULE != "WATERFALL":
        logger.info(f"run optimizer only in SLATE or WATERFALL ROUTING_RULE. current ROUTING_RULE: {ROUTING_RULE}. return optimizer_entrypoint without executing optimizer...")
        return
    
    traffic_segmentation = 1
    objective = "avg_latency"

    logger.info(f"start run optimizer ROUTING_RULE:{ROUTING_RULE}")
        
    logger.debug("coef_dict")
    logger.debug(coef_dict)
    logger.debug("endpoint_level_inflight")
    for region in endpoint_level_inflight:
        for svc in endpoint_level_inflight[region]:
            for ep in endpoint_level_inflight[region][svc]:
                logger.debug(f"{region}, {svc} {ep} {endpoint_level_inflight[region][svc][ep]}")
    logger.debug("endpoint_level_rps")
    for region in endpoint_level_rps:
        for svc in endpoint_level_rps[region]:
            for ep in endpoint_level_rps[region][svc]:
                logger.debug(f"{region}, {svc} {ep} {endpoint_level_rps[region][svc][ep]}")
    # logger.debug(f'{endpoint_level_rps}')
    logger.debug("placement")
    logger.debug(placement)
    logger.debug("all_endpoints")
    logger.debug(all_endpoints)
    logger.debug("endpoint_to_cg_key")
    logger.debug(endpoint_to_cg_key)
    # logger.debug("sp_callgraph_table")
    # logger.debug(sp_callgraph_table)
    logger.info("ep_str_callgraph_table")
    for cg_key in ep_str_callgraph_table:
        for ep_str in ep_str_callgraph_table[cg_key]:
            logger.info(f"{ep_str} -> {ep_str_callgraph_table[cg_key][ep_str]}")
    logger.debug(ep_str_callgraph_table)
    logger.debug("traffic_segmentation")
    logger.debug(traffic_segmentation)
    logger.debug("objective")
    logger.debug(objective)
    
    with open("optimizier_input.txt", "w") as f:
        f.write(f"coef_dict: {coef_dict}\n")
        f.write(f"endpoint_level_inflight: {endpoint_level_inflight}\n")
        f.write(f"endpoint_level_rps: {endpoint_level_rps}\n")
        f.write(f"placement: {placement}\n")
        f.write(f"all_endpoints: {all_endpoints}\n")
        f.write(f"endpoint_to_cg_key: {endpoint_to_cg_key}\n")
        f.write(f"ep_str_callgraph_table: {ep_str_callgraph_table}\n")
        f.write(f"traffic_segmentation: {traffic_segmentation}\n")
        f.write(f"objective: {objective}\n")
        
    def get_total_svc_rps(target_svc):
        global endpoint_level_rps
        rps = 0
        for region in endpoint_level_rps:
            for ep in endpoint_level_rps[region][target_svc]:
                rps += endpoint_level_rps[region][target_svc][ep]
        return rps
    
    # total service rps across all clusters should be less than max_load_per_service[svc]*num_cluster
    for svc in max_load_per_service:
        total_svc_rps = get_total_svc_rps(svc)
        total_capacity_across_all_clusters = max_load_per_service[svc]*len(svc_to_placement[svc])
        logger.info(f"svc,{svc}, total_svc_rps: {total_svc_rps}, total_capacity_across_all_clusters: {total_capacity_across_all_clusters}")
        if total_svc_rps > total_capacity_across_all_clusters:
            logger.error("!!! ERROR !!!")
            logger.error(f"ERROR: svc,{svc}, total_svc_rps({total_svc_rps}) exceeds total_capacity_across_all_clusters({total_capacity_across_all_clusters}), max_load_per_service[svc],{max_load_per_service[svc]}, len(placement),{len(placement)}")
            logger.error("!!! ERROR !!!")
            assert False
    logger.info("!!! before run_optimizer")
    percentage_df, desc = opt.run_optimizer(coef_dict, endpoint_level_inflight, endpoint_level_rps,  placement, all_endpoints, svc_to_placement, endpoint_to_placement, endpoint_to_cg_key, ep_str_callgraph_table, traffic_segmentation, objective, ROUTING_RULE, max_load_per_service, degree)
    logger.info("!!! after run_optimizer")
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
    
    logger.info(f"run_optimizer result: {desc}")
    optimizer_cnt += 1
    pct_df_history_fn = "sim_percentage_df_history.csv"
    file_exists = os.path.isfile(pct_df_history_fn)
    if percentage_df.empty:
        logger.error(f"ERROR: run_optimizer FAIL (**{desc}**) return without updating percentage_df")
        if file_exists:
            with open(pct_df_history_fn, "a") as f:
                f.write(f"idx,{optimizer_cnt},fail,{desc}\n")
        return
    
    logger.info(f"percentage_df is valid (not empty) ({ROUTING_RULE})")
    percentage_df.to_csv("percentage_df.csv", mode="w")
    
    # sim_percentage_df is only for pretty print
    sim_percentage_df = percentage_df.copy()
    sim_percentage_df = sim_percentage_df.drop(columns=['src_endpoint', "dst_endpoint"]).reset_index(drop=True)
    # sim_percentage_df['counter'] = optimizer_cnt
    sim_percentage_df.insert(loc=0, column="counter", value=optimizer_cnt) # same as previous line but inserting to the leftmost position of the dataframe
    sim_percentage_df.to_csv("sim_percentage_df_most_recent.csv", mode="w")
    logger.info(f"sim_percentage_df:\n{sim_percentage_df.to_csv()}")
    
    if file_exists == False:
        sim_percentage_df.to_csv(pct_df_history_fn, mode="w")
    else:
        sim_percentage_df.to_csv(pct_df_history_fn, header=False, mode="a")
    logger.info(f"sim_percentage_df_most_recent.csv, sim_percentage_df_history.csv updated")
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
    
    '''
    feature_names: ['metrics-db@GET@/dbcall', 'intercept']
    
    coef_dict[metrics-db][metrics-db@GET@/dbcall]: {'metrics-db@GET@/dbcall': -1.3077803530123953e-17, 'intercept': 0.5702831840648688}
    '''
    
    # '''plot'''
    # plt.scatter(X, y, color='blue', alpha=0.1, label='Data')
    # X_plot = np.linspace(X.min(), X.max(), 100).reshape(-1, 1)
    # X_plot_transformed = np.hstack((X_plot**degree, np.ones(X_plot.shape)))
    # y_plot = model.predict(X_plot_transformed)
    # plt.plot(X_plot, y_plot, color='red', linewidth=2, label=f'Cubic Fit: $a \cdot x^{degree} + b$')
    # plt.xlabel(x_feature)
    # plt.ylabel(y_col_name)
    # plt.title(f'{ep_str} in {cid}')
    # plt.legend()
    # plt.savefig(f"poly{degree}-latency-{x_feature}-{svc_name}.pdf")
    # plt.show()
    
    return coefficients.to_dict()
    
def fit_linear_regression(data, y_col_name):
    df = pd.DataFrame(data)

    # Separate features and target
    x_colnames = list()
    for colname in df.columns:
        if colname != y_col_name:
            x_colnames.append(colname)
    logger.debug(f"x_colnames: {x_colnames}")
    logger.debug(f"y_col_name: {y_col_name}")
    X = df[x_colnames]
    y = df[y_col_name]
    
    '''Use this if you want preprocessing like normalization, standardization, etc.'''
    # Standardize features using StandardScaler
    # scaler = StandardScaler()
    # X = scaler.fit_transform(X)

    # Create and fit a linear regression model on standardized features
    model = LinearRegression()
    model.fit(X, y)
    
    feature_names =  list(X.columns)+ ['intercept']

    # Create a DataFrame with coefficients and feature names
    coefficients_df = pd.DataFrame(\
            {'Feature': feature_names, \
            'Coefficient':  list(model.coef_)+[model.intercept_]}\
        )

    # Display the coefficients DataFrame
    coef = dict()
    for index, row in coefficients_df.iterrows():
        coef[row['Feature']] = row['Coefficient']
    return coef


def train_latency_function_with_trace(traces, degree):
    global coef_dict
    df = tst.trace_to_df(traces)
    df.to_csv(f"trace_to_file.csv")
    for cid in df["cluster_id"].unique():
        cid_df = df[df["cluster_id"]==cid]
        for svc_name in cid_df["svc_name"].unique():
            cid_svc_df = cid_df[cid_df["svc_name"]==svc_name]
            if svc_name not in latency_func:
                latency_func[svc_name] = dict()
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
    return coef_dict

def gen_endpoint_level_inflight(all_endpoints):
        ep_inflight_req = dict()
        for cid in all_endpoints:
            ep_inflight_req[cid] = dict()
            for svc_name in all_endpoints[cid]:
                ep_inflight_req[cid][svc_name] = dict()
                for ep in all_endpoints[cid][svc_name]:
                    ########################################################
                    # ep_inflight_req[cid][svc_name][ep] = random.randint(50, 60)
                    ep_inflight_req[cid][svc_name][ep] = 0
                    ########################################################
        return ep_inflight_req
    
def gen_endpoint_level_rps(all_endpoints):
    ep_rps = dict()
    for cid in all_endpoints:
        ep_rps[cid] = dict()
        for svc_name in all_endpoints[cid]:
            ep_rps[cid][svc_name] = dict()
            for ep in all_endpoints[cid][svc_name]:
                ########################################################
                # ep_rps[cid][svc_name][ep] = random.randint(10, 50)
                if cid == 0:
                    ep_rps[cid][svc_name][ep] = 10
                else:
                    ep_rps[cid][svc_name][ep] = 100
                ########################################################
    return ep_rps


'''
filter spans
- SLATE_UNKNOWN_REGION in cluster name (refer to the slate-plugin/main.go)
- consul in svc_name (hotel reservation)
string format of trace to span data structure
put unorganized spans into traces data structure 
filter incomplete traces
- ceil(avg_num_svc)
'''
def parse_trace_string_file_to_trace_data_structure(trainig_input_trace_file):
    col = ["cluster_id","svc_name","method","path","trace_id","span_id","parent_span_id","st","et","rt","xt","ct","call_size","inflight_dict","rps_dict"]
    df = pd.read_csv(trainig_input_trace_file, names=col, header=None)
    # span_df = df.iloc[:, :-2] # inflight_dict, rps_dict
    # inflight_df = df.iloc[:, -2:-1] # inflight_dict, rps_dict
    # rps_df = df.iloc[:, -1:] # inflight_dict, rps_dict
    spans = list()
    # for (index1, span_df_row), (index2, inflight_df_row), (index2, rps_df_row) in zip(span_df.iterrows(), inflight_df.iterrows(), rps_df.iterrows()):
    for index, row in df.iterrows():
        if row["cluster_id"] == "SLATE_UNKNOWN_REGION" or row["svc_name"] == "consul":
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
            logger.debug(f"row: {row}")
            logger.debug(f"row['inflight_dict']: {row['inflight_dict']}")
            assert False
        for ep_inflight in inflight_list:
            # ep_inflight: user-us-west-1@POST@/user.User/CheckUser:1
            temp = ep_inflight.split(":")
            assert len(temp) == 2
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
            assert len(temp) == 2
            ep = temp[0] # user-us-west-1@POST@/user.User/CheckUser
            rps = int(temp[1]) # 1
            rps_dict[ep] = rps
            # svc_name = ep.split("@")[0]
            # method = ep.split("@")[1]
            # path = ep.split("@")[2]
            
        span = sp.Span(row["method"], row["path"], row["svc_name"], row["cluster_id"], row["trace_id"], row["span_id"], row["parent_span_id"], st=float(row["st"]), et=float(row["et"]), callsize=int(row["call_size"]), rps_dict=rps_dict, num_inflight_dict=num_inflight_dict)
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
        
    ''' NOTE: using average num svc in a trace is shaky... '''
    for cid in traces:
        tot_num_svc = 0
        for tid in traces[cid]:
            tot_num_svc += len(traces[cid][tid])
        avg_num_svc = tot_num_svc / len(traces[cid])
    required_num_svc = math.ceil(avg_num_svc)
    logger.info(f"avg_num_svc: {avg_num_svc}")
    logger.info(f"required_num_svc: {required_num_svc}")
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
    return complete_traces


# Deprecated
def is_trace_complete(single_trace):
    return True
    # # TODO: Must be changed for other applications.
    # if len(single_trace) == total_num_services: 
    #     return True
    # return False


#  '''Deprecated'''
# This function can be async
# def check_and_move_to_complete_trace(traces_):
#     c_traces = dict()
#     for cid in traces_:
#         for tid in traces_[cid]:
#             single_trace = traces_[cid][tid]
#             if is_trace_complete(single_trace) == True:
#                 ########################################################
#                 ## Weird behavior: In some traces, all spans have the same span id which is productpage's span id.
#                 ## For now, to filter out them following code exists.
#                 ## If the traces were good, it is redundant code.
#                 span_exists = []
#                 ignore_cur = False
#                 for span in single_trace:
#                     if span.span_id in span_exists:
#                         ignore_cur = True
#                         break
#                     span_exists.append(span.span_id)
#                     if ignore_cur:
#                         logger.debug(f"{cfg.log_prefix} span exist, ignore_cur, cid,{span.cluster_id}, tid,{span.trace_id}, span_id,{span.span_id}")
#                         continue
#                     if span.cluster_id not in c_traces:
#                         c_traces[span.cluster_id] = {}
#                     if span.trace_id not in c_traces[span.cluster_id]:
#                         c_traces[span.cluster_id][span.trace_id] = {}
#                     c_traces[span.cluster_id][span.trace_id] = traces_[span.cluster_id][span.trace_id].copy()
#     return c_traces

def calc_max_load_per_service():
    global max_load_per_service
    global svc_to_placement
    global benchmark_name
    global CAPACITY
    for svc in svc_to_placement:
        if benchmark_name == "metrics":
            if svc == "metrics-fake-ingress":
                # fake-ingress gw should receive the original traffic all the time. Routing in User->ingress gateway is fixed as given.
                max_load_per_service[svc] = 9999999999999
            else:
                if CAPACITY == 0:
                    logger.error(f"ERROR: CAPACITY is 0. It should be set to a positive number.")
                    assert False
                max_load_per_service[svc] = CAPACITY # It should per-service enforcement. For now, only one number.
        else:
            max_load_per_service[svc] = 9999999999
        logger.info(f"benchmark_name: {benchmark_name}, set max_load_per_service[{svc}] = {max_load_per_service[svc]}")
    

def training_phase():
    global coef_dict
    global endpoint_level_rps
    global endpoint_level_inflight
    global placement
    global all_endpoints
    global svc_to_placement
    global endpoint_to_placement
    global endpoint_to_cg_key
    # global sp_callgraph_table
    global ep_str_callgraph_table
    global mode
    global train_done
    global trainig_input_trace_file
    global max_load_per_service
    global degree
    
    if mode != "runtime":
        logger.debug(f"{cfg.log_prefix} It is not runtime mode. Skip training. current mode: {mode}")
        return
    
    ## We only need to train once.
    if train_done:
        logger.debug(f"{cfg.log_prefix} Training has been done already.")
        return
    
    logger.debug(f"{cfg.log_prefix} Training starts.")
        
    ## Train has not been done yet.
    '''Option 1: Generate dummy traces'''
    # complete_traces = gen_trace.run(cfg.NUM_CLUSTER, num_traces=10)
    
    '''Option 2: Read trace string file'''
    if trainig_input_trace_file not in os.listdir() or os.path.getsize(trainig_input_trace_file) == 0:
        if trainig_input_trace_file not in os.listdir():
            logger.debug(f"{cfg.log_prefix} ERROR: {profile_output_file} is not in the current directory.")
        if os.path.getsize(trainig_input_trace_file) == 0:
            logger.debug(f"{cfg.log_prefix} ERROR: {profile_output_file} is empty.")        
        logger.debug(f"{cfg.log_prefix} Skip training.")
        return
    
    complete_traces = parse_trace_string_file_to_trace_data_structure(trainig_input_trace_file)
    for cid in complete_traces:
        logger.info(f"{cfg.log_prefix} len(complete_traces[{cid}]): {len(complete_traces[cid])}")
    # complete_traces = check_and_move_to_complete_trace(all_traces)
    # for cid in complete_traces:
    #     logger.info(f"{cfg.log_prefix} len(complete_traces[{cid}]): {len(complete_traces[cid])}")
    
    '''Time stitching'''
    stitched_traces = tst.stitch_time(complete_traces)
    for cid in stitched_traces:
        logger.info(f"{cfg.log_prefix} len(stitched_traces[{cid}]): {len(stitched_traces[cid])}")
    '''Create useful data structures from the traces'''
    # sp_callgraph_table = tst.traces_to_span_callgraph_table(stitched_traces)
    # tst.file_write_callgraph_table(sp_callgraph_table)
    endpoint_to_cg_key = tst.get_endpoint_to_cg_key_map(stitched_traces)
    ep_str_callgraph_table = tst.traces_to_endpoint_str_callgraph_table(stitched_traces)
    all_endpoints = tst.get_all_endpoints(stitched_traces)
    endpoint_to_placement = set_endpoint_to_placement(all_endpoints)
    svc_to_placement = set_svc_to_placement(all_endpoints)
    placement = tst.get_placement_from_trace(stitched_traces)
    
    logger.info("ep_str_callgraph_table")
    logger.info(f"num different callgraph: {len(ep_str_callgraph_table)}")
    for cg_key in ep_str_callgraph_table:
        logger.debug(f"{cg_key}: {ep_str_callgraph_table[cg_key]}")
    for cid in all_endpoints:
        for svc_name in all_endpoints[cid]:
            logger.debug(f"all_endpoints[{cid}][{svc_name}]: {all_endpoints[cid][svc_name]}")
    for cid in placement:
        logger.debug(f"placement[{cid}]: {placement[cid]}")
            
    # Initialize endpoint_level_rps, endpoint_level_inflight
    for region in all_endpoints:
        if region not in endpoint_level_rps:
            endpoint_level_rps[region] = dict()
        if region not in endpoint_level_inflight:
            endpoint_level_inflight[region] = dict()
        for svc in all_endpoints[region]:
            if svc not in endpoint_level_rps[region]:
                endpoint_level_rps[region][svc] = dict()
            if svc not in endpoint_level_inflight[region]:
                endpoint_level_inflight[region][svc] = dict()
            for ep_str in all_endpoints[region][svc]:
                endpoint_level_rps[region][svc][ep_str] = 0
                endpoint_level_inflight[region][svc][ep_str] = 0
                logger.debug(f"training_phase, Init endpoint_level_rps[{region}][{svc}][{ep_str}]: {endpoint_level_rps[region][svc][ep_str]}")
                logger.debug(f"training_phase, Init endpoint_level_inflight[{region}][{svc}][{ep_str}]: {endpoint_level_inflight[region][svc][ep_str]}")
                
    
    '''
    Train linear regression model

    coef_dict[metrics-db][metrics-db@GET@/dbcall]: {'metrics-db@GET@/dbcall': -1.3077803530123953e-17, 'intercept': 0.5702831840648688}
    '''
    if degree <= 0:
        logger.error(f"ERROR: degree is not valid. degree: {degree}")
        assert False
    coef_dict = train_latency_function_with_trace(stitched_traces, degree)
    # NOTE: overwrite coefficient to 1 for debugging
    for svc_name in coef_dict: # svc_name: metrics-db
        for ep_str in coef_dict[svc_name]: # ep_str: metrics-db@GET@/dbcall
            for feature_ep in coef_dict[svc_name][ep_str]: # feature_ep: 'metrics-db@GET@/dbcall' or 'intercept'
                if feature_ep != "intercept": # a in a*(x^degree) + b
                    if coef_dict[svc_name][ep_str][feature_ep] < 0:
                        coef_dict[svc_name][ep_str][feature_ep] = 0
                        coef_dict[svc_name][ep_str]['intercept'] = 1
                        logger.warning(f"coef_dict[{svc_name}][{ep_str}] coefficient is negative. Set it to 0.")
                    else: # a is positive
                        if coef_dict[svc_name][ep_str]['intercept'] < 0:
                            coef_dict[svc_name][ep_str]['intercept'] = 0
                            logger.warning(f"coef_dict[{svc_name}][{ep_str}], coefficient is positive.")
                            logger.warning(f"But, coef_dict[{svc_name}][{ep_str}], intercept is negative. Set it to 0.")
                        coef_dict[svc_name][ep_str][feature_ep] = 1
                    
    if ROUTING_RULE == "WATERFALL":
        logger.info(f"!!! WARNING !!! {ROUTING_RULE} algorithm, set all coefficients to 0!")
        for svc_name in coef_dict:
            for ep_str in coef_dict[svc_name]:
                for feature_ep in coef_dict[svc_name][ep_str]:
                    if feature_ep == "intercept":
                        coef_dict[svc_name][ep_str][feature_ep] = 0
                    else:
                        coef_dict[svc_name][ep_str][feature_ep] = 0
                        
    for svc_name in coef_dict:
        for ep_str in coef_dict[svc_name]:
            logger.info(f'final coef_dict[{svc_name}][{ep_str}]: {coef_dict[svc_name][ep_str]}')
    
    coef_df = pd.DataFrame(coef_dict)
    coef_df.to_csv("coefficient.csv")
                        
    # Print coefficient
    for svc_name in coef_dict:
        for ep_str in coef_dict[svc_name]:
            logger.info(f'coef_dict[{svc_name}][{ep_str}]: {coef_dict[svc_name][ep_str]}')
    
    ''' It will be used as a constraint in the optimizer'''
    calc_max_load_per_service()
    train_done = True # train done!
    return

def read_config_file():
    global benchmark_name
    global total_num_services
    global mode
    global ROUTING_RULE
    global MODE_SET
    global CAPACITY
    global degree
    with open("env.txt", "r") as file:
        lines = file.readlines()
        for line in lines:
            line = line.strip().split(",")
            if line[0] == "benchmark_name":
                if benchmark_name != line[1]:
                    logger.info(f'Update benchmark_name: {benchmark_name} -> {line[1]}')
                    benchmark_name = line[1]
            elif line[0] == "total_num_services":
                temp = int(line[1])
                if total_num_services != temp:
                    logger.info(f'Update total_num_services: {total_num_services} -> {temp}')
                    total_num_services = temp
            elif line[0] == "mode":
                if mode != line[1]:
                    if line[1] not in MODE_SET:
                        logger.error(f"ERROR: unknown mode: {line[1]}")
                        assert False
                    logger.info(f'Update mode: {mode} -> {line[1]}')
                    mode = line[1]
            elif line[0] == "routing_rule":
                if ROUTING_RULE != line[1]:
                    if line[1] not in ROUTING_RULE_SET:
                        logger.error(f"ERROR: unknown routing_rule: {line[1]}")
                        assert False
                    logger.info(f'Update mode: {ROUTING_RULE} -> {line[1]}')
                    ROUTING_RULE = line[1]
            elif line[0] == "capacity":
                logger.info(f'Update CAPACITY: {CAPACITY} -> {line[1]}')
                CAPACITY = int(line[1])
            elif line[0] == "degree":
                logger.info(f'Update degree: {degree} -> {line[1]}')
                degree = int(line[1])
            else:
                logger.debug(f"ERROR: unknown config: {line}")
    logger.info(f"benchmark_name: {benchmark_name}, total_num_services: {total_num_services}, mode: {mode}, ROUTING_RULE: {ROUTING_RULE}")

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    
    ''' update mode '''
    scheduler.add_job(func=read_config_file, trigger="interval", seconds=1)
    
    ''' mode: profile '''
    scheduler.add_job(func=write_spans_to_file, trigger="interval", seconds=5)
    
    ''' mode: runtime '''
    scheduler.add_job(func=training_phase, trigger="interval", seconds=5)
    scheduler.add_job(func=optimizer_entrypoint, trigger="interval", seconds=1)
        
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
    app.run(host='0.0.0.0', port=8080)
