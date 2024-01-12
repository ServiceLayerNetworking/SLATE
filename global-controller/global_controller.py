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

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

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
sp_callgraph_table = {}
all_endpoints = {}
placement = {}
coef_dict = {}
profiling = True
trace_str = list()


'''
cluster_to_cid and cid_to_cluster should be deprecated
cluster_id is given as a number. e.g., 0, 1, 2, ...
'''
# cluster_to_cid = {"us-west": 0, "us-east": 1}
# cid_to_cluster = {0: "us-west", 1: "us-east"}
stats_mutex = Lock()
cluster_pcts = {}


# TODO: Must be changed for other applications.
def is_this_trace_complete(single_trace):
    if len(single_trace) == 4: 
        return True
    return False


# This function can be async
def check_and_move_to_complete_trace():
    for cid in all_traces:
        for tid in all_traces[cid]:
            single_trace = all_traces[cid][tid]
            if is_this_trace_complete(single_trace) == True:
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
                    if span.cluster_id not in complete_traces:
                        complete_traces[span.cluster_id] = {}
                    if span.trace_id not in complete_traces[span.cluster_id]:
                        complete_traces[span.cluster_id][span.trace_id] = {}
                    complete_traces[span.cluster_id][span.trace_id] = all_traces[span.cluster_id][span.trace_id].copy()


def print_routing_rule(pct_df):
    print(f"\n{cfg.log_prefix} OPTIMIZER: ********************")
    print(f"\n{cfg.log_prefix} OPTIMIZER: ** Routing rule")
    print(f"\n{cfg.log_prefix} OPTIMIZER: ** west->west: {int(float(pct_df[0][0])*100)}%")
    print(f"\n{cfg.log_prefix} OPTIMIZER: ** west->east: {int(float(pct_df[0][1])*100)}%")
    print(f"\n{cfg.log_prefix} OPTIMIZER: ** east->east: {int(float(pct_df[1][1])*100)}%")
    print(f"\n{cfg.log_prefix} OPTIMIZER: ** east->west: {int(float(pct_df[1][0])*100)}%")
    print(f"\n{cfg.log_prefix} OPTIMIZER: ********************")


def print_trace(target_traces):
    with stats_mutex:
        if cid in all_traces:
            print(f"{cfg.log_prefix} ================ CLUSTER {cid} PRINT ALL TRACE START ==================")
            print(f"{cfg.log_prefix} len(all_traces[{cid}]), {len(all_traces[cid])}")
            for tid, target_traces in all_traces[cid].items():
                for span in target_traces:
                    print(f"{cfg.log_prefix} {span}")
            print(f"{cfg.log_prefix} ================ CLUSTER {cid} PRINT ALL TRACE DONE ==================")
        
        if cid in complete_traces:
            print(f"{cfg.log_prefix} ================ CLUSTER {cid} PRINT COMPLETE TRACE START ==================")
            print(f"{cfg.log_prefix} len(complete_traces[{cid}]), {len(complete_traces[cid])}")
            for tid, target_traces in complete_traces[cid].items():
                for span in target_traces:
                    print(f"{cfg.log_prefix} {span}")
            print(f"{cfg.log_prefix} ================ CLUSTER {cid} PRINT COMPLETE TRACE DONE ==================")


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


def is_this_trace_complete(single_trace):
    # TODO: Must be changed for other applications.
    if len(single_trace) == 4: 
        return True
    return False

def is_span_existed_in_trace(traces_, span_):
    if (span_.cluster_id in traces_) and (span_.trace_id in traces_[span_.cluster_id]):
            for span in traces_[span_.cluster_id][span_.trace_id]:
                if sp.are_they_same_service_spans(span_, span):
                    print(f"{cfg.log_prefix} span already exists in all_trace {span.trace_id[:8]}, {span.my_span_id}, {span.svc_name}")
                    return True
    return False

# def add_span_to_traces(traces_, span_):
#     if span_.cluster_id not in traces_:
#         traces_[span_.cluster_id] = {}
#     if span_.trace_id not in traces_[span_.cluster_id]:
#         traces_[span_.cluster_id][span_.trace_id] = {}
#     traces_[span_.cluster_id][span_.trace_id].append(span_)
#     return traces_[span_.cluster_id][span_.trace_id]

def parse_stats_into_spans(body, cluster_id, service):
    spans = []
    lines = body.split("\n")
    '''
     ['us-west-1', 'profile-us-west-1', 'POST', '/profile.Profile/GetProfiles', '4a1afd4e0565e973d6bfd803432ae314', '31efa4c6f2197ac7', 'd6bfd803432ae314', '1704910272445', '1704910272447', '0', 'POST@/profile.Profile/GetProfiles,1,1|us-west-1', 'profile-us-west-1', 'POST', '/profile.Profile/GetProfiles', '2857529ac30263da51709ea9b6c9c578', '022d10421302e0f6', '51709ea9b6c9c578', '1704910272723', '1704910272725', '0', 'POST@/profile.Profile/GetProfiles,2,1|us-west-1', 'profile-us-west-1', 'POST', '/profile.Profile/GetProfiles', '3e7eb51dcdeeae6b1456481977f216fc', 'c23cfe5e72207f6a', '1456481977f216fc', '1704910272943', '1704910272945', '0', 'POST@/profile.Profile/GetProfiles,3,1|us-west-1', 'profile-us-west-1', 'POST', '/profile.Profile/GetProfiles', '1d99a31fa2261f7d62e52212c362bfda', 'b124fe1f6fc5c726', '62e52212c362bfda', '1704910273122', '1704910273124', '0', 'POST@/profile.Profile/GetProfiles,4,1|us-west-1', 'profile-us-west-1', 'POST', '/profile.Profile/GetProfiles', 'a7eed018a3853824b2bd871b66e07e1d', '4a73e25f4d0526c1', 'b2bd871b66e07e1d', '1704910273304', '1704910273306', '0', 'POST@/profile.Profile/GetProfiles,5,1|us-west-1', 'profile-us-west-1', 'POST', '/profile.Profile/GetProfiles', '9e6ffa80728847844c827938e1fd09c8', '5dc9301134652860', '4c827938e1fd09c8', '1704910273487', '1704910273489', '0', 'POST@/profile.Profile/GetProfiles,6,1|us-west-1', 'profile-us-west-1', 'POST', '/profile.Profile/GetProfiles', '7f1a217d64410611b44abf639652e341', 'f7fe7d2e60f46317', 'b44abf639652e341', '1704910273656', '1704910273657', '0', 'POST@/profile.Profile/GetProfiles,7,1|']
    '''
    service_level_rps = int(lines[0])
    inflightStats = lines[1]
    requestStats = lines[3:]
    # app.logger.debug('='*30)
    # app.logger.debug(f'lines: {lines}')
    # app.logger.debug('='*30)
    # app.logger.debug(f'service_level_rps: {service_level_rps}')
    # app.logger.debug('='*30)
    # app.logger.debug(f'inflightStats: {inflightStats}')
    # app.logger.debug('='*30)
    # app.logger.debug(f'requestStats: {requestStats}')
    # app.logger.debug('='*30)
    for span_stat in requestStats:
        ss = span_stat.split(" ")
        # app.logger.debug(f"ss: {ss}")
        # app.logger.debug(f"len(ss): {len(ss)}")
        ## NOTE: THIS SHOUD BE UPDATED WHEN member fields in span class is updated.
        if len(ss) != 11:
            app.logger.error(f"ERROR, len(ss) != 11, {len(ss)}, {ss}")
            # assert False
            continue
        region = ss[0]
        serviceName = ss[1]
        method = ss[2]
        path = ss[3]
        traceId = ss[4]
        spanId = ss[5]
        parentSpanId = ss[6]
        startTime = int(ss[7])
        endTime = int(ss[8])
        bodySize = int(ss[9])
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
        app.logger.info(f"{cfg.log_prefix} new span parsed")
    return spans


def parse_inflight_stats(cid, svc_name, inflight_stats):
    ep_inflight = dict()
    # TODO: Parsing should be done here.
    return ep_inflight

def parse_rps_stats(cid, svc_name, inflight_stats):
    ep_rps = dict()
    # TODO: Parsing should be done here.
    return ep_rps

def write_trace_str_to_file():
    with stats_mutex:
        # app.logger.info("asdf")
        # for span_str in trace_str:
        #     app.logger.info(f"asdf {span_str}")
        with open(cfg.init_time+"-trace_string.csv", "w") as file:
            file.write("update is " + cfg.get_cur_time() + "\n")
            for span_str in trace_str:
                file.write(span_str+"\n")
        trace_str.clear()
    
'''
<handleProxyLoad stat format>
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
    # body = request.get_json(force=True)
    svc = request.headers.get('x-slate-servicename')
    region = request.headers.get('x-slate-region')
    body = request.get_data().decode('utf-8')
    # print("{svc} in {region}:\n{body}".format(svc=svc, region=region, body=body))
    if profiling:
        # TODO: In the end of the profiling phase, all the traces have to be written into a file.
        spans = parse_stats_into_spans(body, region, svc)
        app.logger.debug(f"{cfg.log_prefix} len(spans): {len(spans)}")
        if len(spans) > 0:
            # app.logger.info(f"{cfg.log_prefix} ==================================")
            # for span in spans:
            #     app.logger.info(f"{span}")
            # app.logger.info(f"{cfg.log_prefix} ==================================")
            with stats_mutex:
                for span in spans:
                    if is_span_existed_in_trace(all_traces, span):
                        app.logger.info(f"{cfg.log_prefix} span already exists in all_trace {span.trace_id}, {span.span_id}, {span.svc_name}")
                    else:
                        # NOTE: Trace could be incomplete. It should be filtered in postprocessing phase.
                        trace_str.append(str(span))
                        # app.logger.info(f"{cfg.log_prefix} span added to all_trace {span.cluster_id} {span.trace_id}, {span.span_id}, {span.svc_name}")
    else:
        ''' generate fake load stat '''
        # endpoint_level_inflight = gen_endpoint_level_inflight(all_endpoints)
        # endpoint_level_rps = gen_endpoint_level_rps(all_endpoints)
        
        ''' parse actual load stat '''
        endpoint_level_inflight = parse_inflight_stats(cluster_id, svc_name, inflight_stats)
        endpoint_level_rps = parse_rps_stats(cluster_id, svc_name, rps_stats)
    return ""

# def optimizer_entrypoint(sp_callgraph_table, ep_str_callgraph_table, endpoint_level_inflight, endpoint_level_rps, placement, coef_dict, all_endpoints, endpoint_to_cg_key):
## All variables are global variables
def optimizer_entrypoint():
    traffic_segmentation = 1
    objective = "avg_latency" # avg_latency, end_to_end_latency, multi_objective, egress_cost
    percentage_df, desc = opt.run_optimizer(coef_dict, endpoint_level_inflight, endpoint_level_rps,  placement, all_endpoints, endpoint_to_cg_key, sp_callgraph_table, ep_str_callgraph_table, traffic_segmentation, objective)
    # ingress_gw_df = percentage_df[percentage_df['src']=='ingress_gw']
    # for src_cid in range(cfg.NUM_CLUSTER):
    #     for dst_cid in range(cfg.NUM_CLUSTER):
    #         row = ingress_gw_df[(ingress_gw_df['src_cid']==src_cid) & (ingress_gw_df['dst_cid']==dst_cid)]
    #         if len(row) == 1:
    #             cluster_pcts[src_cid][dst_cid] = str(round(row['weight'].tolist()[0], 2))
    #         elif len(row) == 0:
    #             # empty means no routing from this src to this dst
    #             cluster_pcts[src_cid][dst_cid] = str(0)
    #         else:
    #             # It should not happen
    #             print(f"{cfg.log_prefix} [ERROR] length of row can't be greater than 1.")
    #             print(f"{cfg.log_prefix} row: {row}")
    #             assert len(row) <= 1
                
    return cluster_pcts


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
                # print(f"before len(temp_df): {len(temp_df)}")
                ep_df = cid_svc_df[cid_svc_df["endpoint_str"]==ep_str]
                # print(f'cluter_id: {cid}, svc_name: {svc_name}, ep_str: {ep_str}, len(X_) == 0')
                # print(f"after len(ep_df): {len(ep_df)}")
                
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
                
                # print(data)
                # df = pd.DataFrame(data)
                # print("="*20)
                # print(df)
                print(f"data: {data}")
                print()
                coef_dict[svc_name][ep_str] = fit_linear_regression(data, y_col)
                # NOTE: overwriting for debugging
                # latency_func[svc_name][ep_str], X_ = opt_func.get_regression_pipeline(load_dict)
                # X_.to_csv(f"X_c{cid}_{row['method']}.csv")
                # # print(f"latency_func[ep_str]: {latency_func[svc_name][ep_str]}")
                # if len(X_) == 0:
                #     print(f'cluter_id: {cid}, svc_name: {svc_name}, ep_str: {ep_str}, len(X_) == 0')
                # print(f"len(X_): {len(X_)}")
                # if len(X_) > 10:
                #     X_train, X_test, y_train, y_test = train_test_split(X_, y_, train_size=0.9, random_state=1)
                # else:
                #     X_train = X_
                #     X_test = X_
                #     y_train = y_
                #     y_test = y_
                # latency_func[svc_name][ep_str].fit(X_train, y_train)
                # print(f"fitted latency_func[{svc_name}][{row['method']}] coef: {latency_func[svc_name][ep_str]['linearregression'].coef_}")
                # print(f"fitted latency_func[{svc_name}][{row['method']}] intercept: {latency_func[svc_name][ep_str]['linearregression'].intercept_}")
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

def trace_string_file_to_trace_data_structure(trace_string_file_path):
    df = pd.read_csv(trace_string_file_path)
    sliced_df = df.iloc[:, 10:]
    list_of_span = list()
    for (index1, row1), (index2, row2) in zip(df.iterrows(), sliced_df.iterrows()):
        num_inflight_dict = dict()
        rps_dict = dict()
        print(f'row1: {row1}')
        for _, v_list in row2.items():
            print(f'v_list: {v_list}')
            for v in v_list.split("@"):
                elem = v.split("#")
                endpoint = elem[0]
                rps = int(float(elem[1]))
                inflight = int(float(elem[2]))
                num_inflight_dict[endpoint] = inflight
                rps_dict[endpoint] = rps
                
        span = sp.Span(row1["method"], row1["path"], row1["svc_name"], int(row1["region"]), row1["traceId"], row1["spanId"], row1["parentSpanId"], st=float(row1["startTime"]), et=float(row1["endTime"]), callsize=int(row1["bodySize"]), rps_dict=num_inflight_dict, num_inflight_dict=num_inflight_dict)
        list_of_span.append(span)
        
    # Convert list of span to traces data structure
    traces = dict()
    for span in list_of_span:
        if span.cluster_id not in traces:
            traces[span.cluster_id] = dict()
        if span.trace_id not in traces[span.cluster_id]:
            traces[span.cluster_id][span.trace_id] = list()
        traces[span.cluster_id][span.trace_id].append(span)
    return traces

def training_phase():
    '''Option 1: Generate dummy traces'''
    # complete_traces = gen_trace.run(cfg.NUM_CLUSTER, num_traces=10)
    
    '''Option 2: Read trace string file'''
    complete_traces = trace_string_file_to_trace_data_structure("trace_string.csv")
    for span in complete_traces:
        print(span)
    
    
    '''Time stitching'''
    stitched_traces = tst.stitch_time(complete_traces)
    
    
    '''Create useful data structures from the traces'''
    sp_callgraph_table = tst.traces_to_span_callgraph_table(stitched_traces)
    endpoint_to_cg_key = tst.get_endpoint_to_cg_key_map(stitched_traces)
    ep_str_callgraph_table = tst.traces_to_endpoint_str_callgraph_table(stitched_traces)
    all_endpoints = tst.get_all_endpoints(stitched_traces)
    tst.file_write_callgraph_table(sp_callgraph_table)
    placement = tst.get_placement_from_trace(stitched_traces)
    
    '''
    Train linear regression model
    The linear regression model is function of "inflight_req"
    '''
    coef_dict = train_latency_function_with_trace(stitched_traces)
    ############################################################
    ## NOTE: overwriting coefficient for debugging
    for svc_name in coef_dict:
        for ep_str in coef_dict[svc_name]:
            for feature_ep in coef_dict[svc_name][ep_str]:
                if feature_ep == "intercept":
                    coef_dict[svc_name][ep_str][feature_ep] = 0
                else:
                    coef_dict[svc_name][ep_str][feature_ep] = 1
    ############################################################
    for svc_name in coef_dict:
        for ep_str in coef_dict[svc_name]:
            print(f'coef_dict[{svc_name}][{ep_str}]: {coef_dict[svc_name][ep_str]}')


if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    if profiling:
        # cluster_pcts = local_routing_rule()
        scheduler.add_job(func=write_trace_str_to_file, trigger="interval", seconds=5)
    else:
        training_phase()
        '''Entry point of optimizer'''
        # optimizer_entrypoint(sp_callgraph_table, ep_str_callgraph_table, endpoint_level_inflight, endpoint_level_rps, placement, coef_dict, all_endpoints, endpoint_to_cg_key)
        scheduler.add_job(func=optimizer_entrypoint, trigger="interval", seconds=1)
        
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
    app.run(host='0.0.0.0', port=8080)