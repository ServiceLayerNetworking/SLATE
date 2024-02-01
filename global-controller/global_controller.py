from flask import Flask, request
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

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# app.logger.setLevel(logging.INFO)
# werklog = logging.getLogger('werkzeug')
# werklog.setLevel(logging.DEBUG)
# app.logger.setLevel(logging.INFO)

# Create a custom filter to exclude log messages for the specified route
# class SuppressRouteFilter(logging.Filter):
#     def filter(self, record):
#         # Exclude log messages for the "/proxyLoad" route
#         return "/proxyLoad" not in record.getMessage()

# # Add the custom filter to the app logger
# app.logger.addFilter(SuppressRouteFilter())

latency_func = {}
is_trained_flag = False
complete_traces = {}
all_traces = {}
prerecorded_trace = {}
svc_to_rps = {}
endpoint_level_inflight = {}
endpoint_level_rps = {}
endpoint_to_cg_key = {}
ep_str_callgraph_table = {}
# sp_callgraph_table = {}
all_endpoints = {}
placement = {}
coef_dict = {}
trace_str = list()
percentage_df = None
mode = ""
train_done = False
benchmark_name = ""
total_num_services = 0

'''
cluster_to_cid and cid_to_cluster should be deprecated
cluster_id is given as a number. e.g., 0, 1, 2, ...
'''
# cluster_to_cid = {"us-west": 0, "us-east": 1}
# cid_to_cluster = {0: "us-west", 1: "us-east"}
stats_mutex = Lock()
cluster_pcts = {}

'''
local routing example
cluster_pcts[0] = {0: "1.0", 1: "0.0"}
cluster_pcts[1] = {0: "0.0", 1: "1.0"}
'''
def local_routing_rule():
    cluster_pcts_ = dict()
    for cid in range(cfg.NUM_CLUSTER):
        cluster_pcts_[cid] = {}
        for dst_cid in range(cfg.NUM_CLUSTER):
            if dst_cid == cid:
                cluster_pcts_[cid][dst_cid] = "1.0"
            else:
                cluster_pcts_[cid][dst_cid] = "0.0"
    return cluster_pcts_


def is_span_existed_in_trace(traces_, span_):
    if (span_.cluster_id in traces_) and (span_.trace_id in traces_[span_.cluster_id]):
            for span in traces_[span_.cluster_id][span_.trace_id]:
                if sp.are_they_same_service_spans(span_, span):
                    app.logger.debug(f"{cfg.log_prefix} span already exists in all_trace {span.trace_id[:8]}, {span.my_span_id}, {span.svc_name}")
                    return True
    return False

# def add_span_to_traces(traces_, span_):
#     if span_.cluster_id not in traces_:
#         traces_[span_.cluster_id] = {}
#     if span_.trace_id not in traces_[span_.cluster_id]:
#         traces_[span_.cluster_id][span_.trace_id] = {}
#     traces_[span_.cluster_id][span_.trace_id].append(span_)
#     return traces_[span_.cluster_id][span_.trace_id]

def parse_inflight_stats(body):
    lines = body.split("\n")
    # for i in range(len(lines)):
    #     app.logger.info(f"{cfg.log_prefix} parse_inflight_stats, lines[{i}]: {lines[i]}")
    inflightStats = lines[1]
    return inflightStats


def parse_stats_into_spans(body, given_svc_name):
    lines = body.split("\n")
    requestStats = lines[3:]
    spans = []
    for span_stat in requestStats:
        ss = span_stat.split(" ")
        # app.logger.debug(f"ss: {ss}")
        # app.logger.debug(f"len(ss): {len(ss)}")
        ## NOTE: THIS SHOUD BE UPDATED WHEN member fields in span class is updated.
        if len(ss) != 11:
            app.logger.error(f"ERROR, len(ss) != 11, (len(ss):{len(ss)}, ss:{ss})")
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
        else:
            bodySize = 50
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
        # app.logger.info(f"{cfg.log_prefix} new span parsed. serviceName: {serviceName}, bodySize: {bodySize}")
    return spans


def write_trace_str_to_file():
    global mode
    if mode != "profile":
        return
    with stats_mutex:
        # with open(cfg.init_time+"-trace_string.csv", "w") as file:
        with open("trace_string.csv", "w") as file:
            # file.write("update is " + cfg.get_cur_time() + "\n")
            for span_str in trace_str:
                file.write(span_str+"\n")
        trace_str.clear()
    app.logger.debug(f"{cfg.log_prefix} write_trace_str_to_file happened.")
    

'''
----------------------------------------------------
service_level_rps_of_all_endpoints
service_level_num_inflight_req_of_all_endpoints
endpoint_0,endpoint_0_rps,endpoint_0_num_inflight
endpoint_1,endpoint_1_rps,endpoint_1_num_inflight

region svc_name method path traceId spanId parentSpanId startTime endTime bodySize endpoint_0#endpoint_0_rps#endpoint_0_num_inflight_req@endpoint_1#endpoint_1_rps#endpoint_1_num_inflight_req

Example:
service_level_rps
3

inflightStats
endpoint,endpoint_rps,endpoint_num_inflight
GET /recommendations,6,0

requestStats
7077af93f0f42b3a  1704850297727 1704850297793 0 GET /hotels,8,0|POST /user,1,0|GET /recommendations,26,0|POST /reservation,59,2|
us-west-1 frontend-us-west-1 GET /recommendations 8d025f3477105642098d1be482cb9d20 098d1be482cb9d20  1704850297777 1704850297871 0 POST /reservation,59,1|GET /hotels,8,0|GET /recommendations,27,1|POST /user,1,0|
us-west-1 frontend-us-west-1 GET /recommendations d355834dbf0a45032c18e6905b0a8839 2c18e6905b0a8839  1704850297800 1704850297871 0 GET /recommendations,28,2|POST /reservation,59,0|GET /hotels,8,0|POST /user,1,0|
...
----------------------------------------------------
'''
# @app.route("/clusterLoad", methods=["POST"]) # from cluster-controller
@app.post('/proxyLoad') # from wasm
def handleProxyLoad():
    global endpoint_level_rps
    global endpoint_level_inflight
    global percentage_df
    
    # body = request.get_json(force=True)
    svc = request.headers.get('x-slate-servicename')
    if svc.find("-us-") != -1:
            svc = svc.split("-us-")[0]
    region = request.headers.get('x-slate-region')
    if svc == "slate-controller":
        app.logger.debug(f"{cfg.log_prefix} WARNING: skip slate-controller in handleproxy")
        return ""
    if region == "SLATE_UNKNOWN_REGION":
        app.logger.debug(f"{cfg.log_prefix} WARNING: skip SLATE_UNKNOWN_REGION in handleproxy")
        return ""
    body = request.get_data().decode('utf-8')
    # app.logger.debug("{svc} in {region}:\n{body}".format(svc=svc, region=region, body=body))
        
    app.logger.info(f"{cfg.log_prefix} handleProxyLoad, svc: {svc}, region: {region}")
    
    inflightStats = parse_inflight_stats(body)
    if inflightStats == "":
        for ep in endpoint_level_rps[region][svc]:
            endpoint_level_rps[region][svc][ep] = 0
        for ep in endpoint_level_inflight[region][svc]:
            endpoint_level_inflight[region][svc][ep] = 0
        app.logger.info(f"{cfg.log_prefix} {svc} inflightStats is empty")
        app.logger.info(f"{cfg.log_prefix} Init entire inflight and rps to 0")
        return ""
    
    # inflightStats: GET@/start,4,1|POST@/start,4,1|
    app.logger.info(f"{cfg.log_prefix} inflightStats: {inflightStats}")
    active_endpoint_stats = inflightStats.split("|")[:-1]
    for ep_stats in active_endpoint_stats:
        # ep_stats: GET@/start,4,1
        app.logger.info(f"{cfg.log_prefix} ep_stats: {ep_stats}")
        ep = svc + sp.ep_del + ep_stats.split(",")[0]
        # ep: metrics-handler@GET@/start
        assert len(ep.split(sp.ep_del)) == 3
        ontick_rps = int(ep_stats.split(",")[1])
        ontick_inflight = int(ep_stats.split(",")[2])
        endpoint_level_rps[region][svc][ep] = ontick_rps
        endpoint_level_inflight[region][svc][ep] = ontick_inflight
            
    for ep in endpoint_level_rps[region][svc]:
        app.logger.info(f"{cfg.log_prefix} handleProxyLoad, endpoint_level_rps: {region}, {svc}, {ep}, {endpoint_level_rps[region][svc][ep]}")
    for ep in endpoint_level_inflight[region][svc]:
        app.logger.info(f"{cfg.log_prefix} handleProxyLoad, endpoint_level_inflight: {region}, {svc}, {ep}, {endpoint_level_inflight[region][svc][ep]}")
        
    if mode == "profile":
        # TODO: In the end of the profile phase, all the traces have to be written into a file.
        
            
        spans = parse_stats_into_spans(body, svc)
        # app.logger.debug(f"{cfg.log_prefix} service_level_rps: {service_level_rps}")
        app.logger.debug(f"{cfg.log_prefix} inflightStats: {inflightStats}")
        # It is necessary to initialize rps and inflight for each endpoint since it is not guaranteed that all endpoints are in the stats. In the current ontick, it shouldn't use previous rps or inflight. If there is stats for endpoint A, it doesn't mean that there is stats for endpoint B. 
        all_ep_for_rps_so_far = endpoint_level_rps[region][svc]
        for ep in all_ep_for_rps_so_far:
            endpoint_level_rps[region][svc][ep] = 0
        all_ep_for_inflight_so_far = endpoint_level_inflight[region][svc]
        for ep in all_ep_for_inflight_so_far:
            endpoint_level_inflight[region][svc][ep] = 0
            
        # This code is for debugging purpose. for performance, comment it out.
        # for i in len(all_ep_for_rps_so_far):
        #     assert all_ep_for_inflight_so_far[i] == all_ep_for_rps_so_far[i]
    
        if len(spans) > 0:
            with stats_mutex:
                for span in spans:
                    if is_span_existed_in_trace(all_traces, span):
                        app.logger.info(f"{cfg.log_prefix} span already exists in all_trace {span.trace_id}, {span.span_id}, {span.svc_name}")
                    else:
                        # NOTE: Trace could be incomplete. It should be filtered in postprocessing phase.
                        # metrics-app: #spans = 3
                        # matmul-app: #spans = 2
                        # hotelreservation: #spans = ?
                        trace_str.append(str(span))
        return ""
    else:
        ''' generate fake load stat '''
        # endpoint_level_inflight = gen_endpoint_level_inflight(all_endpoints)
        # endpoint_level_rps = gen_endpoint_level_rps(all_endpoints)
        
        '''
        API, global_controller --> wasm
        
        data format:
        src_endpoint, dst_endpoint, src_cid, dst_cid, weight
        
        It is raw text. It should be parsed in wasm.
        example:
        
        west
        ingress
        
        metrics-fake-ingress@GET@/start, us-west-1, us-west-1, 0.6
        metrics-fake-ingress@GET@/start, us-west-1, us-east-1, 0.4
        metrics-fake-ingress@POST@/start, us-west-1, us-west-1, 0.9
        metrics-fake-ingress@POST@/start, us-west-1, us-east-1, 0.1
        
        east
        ingress
        
        metrics-fake-ingress@GET@/start, us-east-1, us-west-1, 1.0
        metrics-fake-ingress@GET@/start, us-east-1, us-east-1, 0.0
        metrics-fake-ingress@POST@/start, us-east-1, us-west-1, 0.8
        metrics-fake-ingress@POST@/start, us-east-1, us-east-1, 0.2
        '''
        if percentage_df:
            temp_df = percentage_df.loc[(percentage_df['src_svc'] == svc)]
            temp_df = temp_df.loc[(temp_df['src_cid'] == region)]
            temp_df = temp_df.drop(columns=['index_col', 'src_svc', "dst_svc", 'flow', 'total'])
            csv_string = temp_df.to_csv(header=False, index=False)
            
            if len(temp_df) == 0:
                return None # rollback to local routing
            
        else:
            csv_string = "" # rollback to local routing
    app.logger.debug(f'csv_string for {svc} in {region}:')
    app.logger.debug(csv_string)
    return csv_string

# def optimizer_entrypoint(sp_callgraph_table, ep_str_callgraph_table, endpoint_level_inflight, endpoint_level_rps, placement, coef_dict, all_endpoints, endpoint_to_cg_key):
## All variables are global variables
def optimizer_entrypoint():
    global coef_dict
    global endpoint_level_inflight
    global endpoint_level_rps
    global placement
    global all_endpoints
    global endpoint_to_cg_key
    # global sp_callgraph_table
    global ep_str_callgraph_table
    global percentage_df
    # global traffic_segmentation
    # global objective
    if mode != "runtime":
        return
    traffic_segmentation = 1
    objective = "avg_latency"
    
    app.logger.debug("coef_dict")
    app.logger.debug(coef_dict)
    app.logger.info("[OPTIMIZER] endpoint_level_inflight")
    for region in endpoint_level_inflight:
        for svc in endpoint_level_inflight[region]:
            for ep in endpoint_level_inflight[region][svc]:
                app.logger.info(f"[OPTIMIZER] {region}, {svc} {ep} {endpoint_level_inflight[region][svc][ep]}")
    app.logger.info("[OPTIMIZER] endpoint_level_rps")
    for region in endpoint_level_rps:
        for svc in endpoint_level_rps[region]:
            for ep in endpoint_level_rps[region][svc]:
                app.logger.info(f"[OPTIMIZER] {region}, {svc} {ep} {endpoint_level_rps[region][svc][ep]}")
    # app.logger.info(f'[OPTIMIZER] {endpoint_level_rps}')
    app.logger.debug("placement")
    app.logger.debug(placement)
    app.logger.debug("all_endpoints")
    app.logger.debug(all_endpoints)
    app.logger.debug("endpoint_to_cg_key")
    app.logger.debug(endpoint_to_cg_key)
    # app.logger.debug("sp_callgraph_table")
    # app.logger.debug(sp_callgraph_table)
    app.logger.info("ep_str_callgraph_table")
    for cg_key in ep_str_callgraph_table:
        for ep_str in ep_str_callgraph_table[cg_key]:
            app.logger.info(f"[OPTIMIZER] {ep_str} -> {ep_str_callgraph_table[cg_key][ep_str]}")
    app.logger.debug(ep_str_callgraph_table)
    app.logger.debug("traffic_segmentation")
    app.logger.debug(traffic_segmentation)
    app.logger.debug("objective")
    app.logger.debug(objective)
    
    percentage_df = opt.run_optimizer(coef_dict, endpoint_level_inflight, endpoint_level_rps,  placement, all_endpoints, endpoint_to_cg_key, ep_str_callgraph_table, traffic_segmentation, objective)
    if percentage_df == None:
        app.logger.debug(f"{cfg.log_prefix} [OPTIMIZER] ERROR: run_optimizer FAILS.")
        return
    app.logger.debug(f"{cfg.log_prefix} [OPTIMIZER] run_optimizer is done.")
    percentage_df.to_csv(f"percentage_df_new.csv")
    

# Sample data
def fit_linear_regression(data, y_col_name):
    df = pd.DataFrame(data)

    # Separate features and target
    x_colnames = list()
    for colname in df.columns:
        if colname != y_col_name:
            x_colnames.append(colname)
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


def train_latency_function_with_trace(traces):
    # df = pd.read_csv(f"{trace_file_path}")
    # traces = sp.file_to_trace(trace_file_path)
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
                # app.logger.debug(f"before len(temp_df): {len(temp_df)}")
                ep_df = cid_svc_df[cid_svc_df["endpoint_str"]==ep_str]
                # app.logger.debug(f'cluter_id: {cid}, svc_name: {svc_name}, ep_str: {ep_str}, len(X_) == 0')
                # app.logger.debug(f"after len(ep_df): {len(ep_df)}")
                
                # Data preparation: load(X) and latency(y) 
                data = dict()
                y_col = "latency"
                for index, row in ep_df.iterrows():
                    for key, val in row["num_inflight_dict"].items():
                        if key not in data:
                            data[key] = list()
                        data[key].append(val)
                    if y_col not in data:
                        data[y_col] = list()
                    data[y_col].append(row["xt"])
                
                # app.logger.debug(f"data: {data}")
                # app.logger.debug()
                coef_dict[svc_name][ep_str] = fit_linear_regression(data, y_col)
                # NOTE: overwriting for debugging
                # latency_func[svc_name][ep_str], X_ = opt_func.get_regression_pipeline(load_dict)
                # X_.to_csv(f"X_c{cid}_{row['method']}.csv")
                # # app.logger.debug(f"latency_func[ep_str]: {latency_func[svc_name][ep_str]}")
                # if len(X_) == 0:
                #     app.logger.debug(f'cluter_id: {cid}, svc_name: {svc_name}, ep_str: {ep_str}, len(X_) == 0')
                # app.logger.debug(f"len(X_): {len(X_)}")
                # if len(X_) > 10:
                #     X_train, X_test, y_train, y_test = train_test_split(X_, y_, train_size=0.9, random_state=1)
                # else:
                #     X_train = X_
                #     X_test = X_
                #     y_train = y_
                #     y_test = y_
                # latency_func[svc_name][ep_str].fit(X_train, y_train)
                # app.logger.debug(f"fitted latency_func[{svc_name}][{row['method']}] coef: {latency_func[svc_name][ep_str]['linearregression'].coef_}")
                # app.logger.debug(f"fitted latency_func[{svc_name}][{row['method']}] intercept: {latency_func[svc_name][ep_str]['linearregression'].intercept_}")
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

# def trace_string_file_to_trace_data_structure(trace_string_file_path):
#     df = pd.read_csv(trace_string_file_path)
#     sliced_df = df.iloc[:, 10:]
#     list_of_span = list()
#     for (index1, row1), (index2, row2) in zip(df.iterrows(), sliced_df.iterrows()):
#         num_inflight_dict = dict()
#         rps_dict = dict()
#         app.logger.debug(f'row1: {row1}')
#         for _, v_list in row2.items():
#             app.logger.debug(f'v_list: {v_list}')
#             for v in v_list.split("@"):
#                 elem = v.split("#")
#                 endpoint = elem[0]
#                 rps = int(float(elem[1]))
#                 inflight = int(float(elem[2]))
#                 num_inflight_dict[endpoint] = inflight
#                 rps_dict[endpoint] = rps
                
#         span = sp.Span(row1["method"], row1["path"], row1["svc_name"], int(row1["region"]), row1["traceId"], row1["spanId"], row1["parentSpanId"], st=float(row1["startTime"]), et=float(row1["endTime"]), callsize=int(row1["bodySize"]), rps_dict=num_inflight_dict, num_inflight_dict=num_inflight_dict)
#         list_of_span.append(span)
        
#     # Convert list of span to traces data structure
#     traces = dict()
#     for span in list_of_span:
#         if span.cluster_id not in traces:
#             traces[span.cluster_id] = dict()
#         if span.trace_id not in traces[span.cluster_id]:
#             traces[span.cluster_id][span.trace_id] = list()
#         traces[span.cluster_id][span.trace_id].append(span)
#     return traces

def trace_string_file_to_trace_data_structure(trace_string_file_path):
    col = ["cluster_id","svc_name","method","path","trace_id","span_id","parent_span_id","st","et","rt","xt","ct","call_size","inflight_dict","rps_dict"]
    df = pd.read_csv(trace_string_file_path, names=col, header=None)
    # span_df = df.iloc[:, :-2] # inflight_dict, rps_dict
    # inflight_df = df.iloc[:, -2:-1] # inflight_dict, rps_dict
    # rps_df = df.iloc[:, -1:] # inflight_dict, rps_dict
    list_of_span = list()
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
        
        # inflight_row =  "user-us-west-1@POST@/user.User/CheckUser:1|user-us-west-1@POST@/user.User/CheckUser:1|"
        # print(row)
        # print(row["inflight_dict"])
        try:
            inflight_list = row["inflight_dict"].split("|")[:-1]
        except:
            print(f"row: {row}")
            print(f"row['inflight_dict']: {row['inflight_dict']}")
            assert False
        for ep_inflight in inflight_list:
            # print(row)
            temp = ep_inflight.split(":")
            # print(f"len(temp): {len(temp)}")
            # print(temp)
            assert len(temp) == 2
            ep = temp[0] # user-us-west-1@POST@/user.User/CheckUser
            inflight = int(temp[1]) # 1
            svc_name = ep.split("@")[0]
            method = ep.split("@")[1]
            path = ep.split("@")[2]
            num_inflight_dict[ep] = inflight
            
        rps_list = row["rps_dict"].split("|")[:-1]
        for ep_rps in rps_list:
            temp = ep_rps.split(":")
            # print(f"len(temp): {len(temp)}")
            assert len(temp) == 2
            ep = temp[0] # user-us-west-1@POST@/user.User/CheckUser
            rps = int(temp[1]) # 1
            svc_name = ep.split("@")[0]
            method = ep.split("@")[1]
            path = ep.split("@")[2]
            rps_dict[ep] = rps
            
        
        ##################################################
        # serviceName = row["svc_name"]
        # if serviceName.find("-us-") != -1:
        #     serviceName = serviceName.split("-us-")[0]
        ##################################################
        span = sp.Span(row["method"], row["path"], row["svc_name"], row["cluster_id"], row["trace_id"], row["span_id"], row["parent_span_id"], st=float(row["st"]), et=float(row["et"]), callsize=int(row["call_size"]), rps_dict=num_inflight_dict, num_inflight_dict=num_inflight_dict)
        list_of_span.append(span)
        # print(str(span))
        # exit()
        
    # Convert list of span to traces data structure
    traces = dict()
    for span in list_of_span:
        if span.cluster_id not in traces:
            traces[span.cluster_id] = dict()
        if span.trace_id not in traces[span.cluster_id]:
            traces[span.cluster_id][span.trace_id] = list()
        traces[span.cluster_id][span.trace_id].append(span)
    
    for cid in traces:
        tot_num_svc = 0
        for tid in traces[cid]:
            tot_num_svc += len(traces[cid][tid])
        avg_num_svc = tot_num_svc / len(traces[cid])
        
    print(f"avg_num_svc: {avg_num_svc}")
    required_num_svc = math.ceil(avg_num_svc)
    print(f"required_num_svc: {required_num_svc}")
    
    complete_traces = dict()
    for cid in traces:
        if cid not in complete_traces:
            complete_traces[cid] = dict()
        for tid in traces[cid]:
            if len(traces[cid][tid]) == required_num_svc:
                complete_traces[cid][tid] = traces[cid][tid]
    for cid in traces:
        print(f"len(traces[{cid}]): {len(traces[cid])}")
    for cid in complete_traces:
        print(f"len(complete_traces[{cid}]): {len(complete_traces[cid])}")
    return complete_traces

def is_trace_complete(single_trace):
    # TODO: Must be changed for other applications.
    if len(single_trace) == total_num_services: 
        return True
    return False


# This function can be async
def check_and_move_to_complete_trace(all_traces):
    c_traces = dict()
    for cid in all_traces:
        for tid in all_traces[cid]:
            single_trace = all_traces[cid][tid]
            if is_trace_complete(single_trace) == True:
                ########################################################
                ## Weird behavior: In some traces, all spans have the same span id which is productpage's span id.
                ## For now, to filter out them following code exists.
                ## If the traces were good, it is redundant code.
                span_exists = []
                ignore_cur = False
                for span in single_trace:
                    if span.span_id in span_exists:
                        ignore_cur = True
                        break
                    span_exists.append(span.span_id)
                    if ignore_cur:
                        app.logger.debug(f"{cfg.log_prefix} span exist, ignore_cur, cid,{span.cluster_id}, tid,{span.trace_id}, span_id,{span.span_id}")
                        continue
                    if span.cluster_id not in c_traces:
                        c_traces[span.cluster_id] = {}
                    if span.trace_id not in c_traces[span.cluster_id]:
                        c_traces[span.cluster_id][span.trace_id] = {}
                    c_traces[span.cluster_id][span.trace_id] = all_traces[span.cluster_id][span.trace_id].copy()
    return c_traces


def training_phase():
    global coef_dict
    global endpoint_level_rps
    global endpoint_level_inflight
    global placement
    global all_endpoints
    global endpoint_to_cg_key
    # global sp_callgraph_table
    global ep_str_callgraph_table
    global mode
    global train_done
    if mode != "runtime":
        app.logger.debug(f"{cfg.log_prefix} Skip training. mode: {mode}")
        return
    ## We only need to train once.
    if train_done:
        app.logger.debug(f"{cfg.log_prefix} Training has been done already.")
        return
    
    
    app.logger.debug(f"{cfg.log_prefix} Training starts.")
    
    ## Train has not been done yet.
    '''Option 1: Generate dummy traces'''
    # complete_traces = gen_trace.run(cfg.NUM_CLUSTER, num_traces=10)
    
    '''Option 2: Read trace string file'''
    if "trace_string.csv" not in os.listdir() or os.path.getsize("trace_string.csv") == 0:
        if "trace_string.csv" not in os.listdir():
            app.logger.debug(f"{cfg.log_prefix} ERROR: trace_string.csv is not in the current directory.")
        if os.path.getsize("trace_string.csv") == 0:
            app.logger.debug(f"{cfg.log_prefix} ERROR: trace_string.csv is empty.")        
        app.logger.debug(f"{cfg.log_prefix} Skip training.")
        return
    
    all_traces = trace_string_file_to_trace_data_structure("trace_string.csv")
    app.logger.debug(f"{cfg.log_prefix} len(all_traces): {len(all_traces)}")
    complete_traces = check_and_move_to_complete_trace(all_traces)
    app.logger.debug(f"{cfg.log_prefix} len(complete_traces): {len(complete_traces)}")
    # for span in complete_traces:
    #     app.logger.debug(span)
    
    '''Time stitching'''
    stitched_traces = tst.stitch_time(complete_traces)
    
    '''Create useful data structures from the traces'''
    # sp_callgraph_table = tst.traces_to_span_callgraph_table(stitched_traces)
    endpoint_to_cg_key = tst.get_endpoint_to_cg_key_map(stitched_traces)
    ep_str_callgraph_table = tst.traces_to_endpoint_str_callgraph_table(stitched_traces)
    app.logger.debug("ep_str_callgraph_table")
    app.logger.debug(f"num different callgraph: {len(ep_str_callgraph_table)}")
    for cg_key in ep_str_callgraph_table:
        app.logger.debug(f"{cg_key}: {ep_str_callgraph_table[cg_key]}")
        
        
    all_endpoints = tst.get_all_endpoints(stitched_traces)
    for cid in all_endpoints:
        for svc_name in all_endpoints[cid]:
            app.logger.debug(f"all_endpoints[{cid}][{svc_name}]: {all_endpoints[cid][svc_name]}")
            
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
                app.logger.info(f"Init endpoint_level_rps[{region}][{svc}][{ep_str}]: {endpoint_level_rps[region][svc][ep_str]}")
                app.logger.info(f"Init endpoint_level_inflight[{region}][{svc}][{ep_str}]: {endpoint_level_inflight[region][svc][ep_str]}")
                
    # tst.file_write_callgraph_table(sp_callgraph_table)
    placement = tst.get_placement_from_trace(stitched_traces)
    for cid in placement:
        app.logger.debug(f"placement[{cid}]: {placement[cid]}")
    
    '''
    Train linear regression model
    The linear regression model is function of "inflight_req"
    '''
    coef_dict = train_latency_function_with_trace(stitched_traces)
    for svc_name in coef_dict:
        for ep_str in coef_dict[svc_name]:
            app.logger.debug(f'coef_dict[{svc_name}][{ep_str}]: {coef_dict[svc_name][ep_str]}')
    ############################################################
    ## NOTE: overwriting coefficient for debugging
    # for svc_name in coef_dict:
    #     for ep_str in coef_dict[svc_name]:
    #         for feature_ep in coef_dict[svc_name][ep_str]:
    #             if feature_ep == "intercept":
    #                 coef_dict[svc_name][ep_str][feature_ep] = 0
    #             else:
    #                 coef_dict[svc_name][ep_str][feature_ep] = 1
    # ############################################################
    # for svc_name in coef_dict:
    #     for ep_str in coef_dict[svc_name]:
    #         app.logger.debug(f'coef_dict[{svc_name}][{ep_str}]: {coef_dict[svc_name][ep_str]}')
            
    train_done = True # train done!
    return

def read_config_file():
    global benchmark_name
    global total_num_services
    global mode
    with open("env.txt", "r") as file:
        lines = file.readlines()
        for line in lines:
            line = line.strip().split(",")
            if line[0] == "benchmark_name":
                if benchmark_name != line[1]:
                    app.logger.debug(f'Update benchmark_name: {benchmark_name} -> {line[1]}')
                    benchmark_name = line[1]
            elif line[0] == "total_num_services":
                temp = int(line[1])
                if total_num_services != temp:
                    app.logger.debug(f'Update total_num_services: {total_num_services} -> {temp}')
                    total_num_services = temp
            elif line[0] == "mode":
                if mode != line[1]:
                    app.logger.debug(f'Update mode: {mode} -> {line[1]}')
                    mode = line[1]
            else:
                app.logger.debug(f"ERROR: unknown config: {line}")
                assert False
    app.logger.debug(f"{cfg.log_prefix} benchmark_name: {benchmark_name}, total_num_services: {total_num_services}, mode: {mode}")

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    
    ''' update mode '''
    scheduler.add_job(func=read_config_file, trigger="interval", seconds=5)
    
    ''' mode: profile '''
    scheduler.add_job(func=write_trace_str_to_file, trigger="interval", seconds=5)
    
    ''' mode: runtime '''
    scheduler.add_job(func=training_phase, trigger="interval", seconds=5)
    scheduler.add_job(func=optimizer_entrypoint, trigger="interval", seconds=1)
        
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
    app.run(host='0.0.0.0', port=8080)