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
import test as test
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
werklog = logging.getLogger('werkzeug')
werklog.setLevel(logging.DEBUG)

latency_func = {}
is_trained_flag = False
complete_traces = {}
all_traces = {}
prerecorded_trace = {}
svc_to_rps = {}


'''
cluster_to_cid and cid_to_cluster should be deprecated
cluster_id is given as a number. e.g., 0, 1, 2, ...
'''
# cluster_to_cid = {"us-west": 0, "us-east": 1}
# cid_to_cluster = {0: "us-west", 1: "us-east"}
stats_mutex = Lock()
# stats_arr = []
# TODO: It is currently dealing with ingress gateway only.
# cluster_pcts[cluster_id][dest cluster] = pct
cluster_pcts = {} 
prof_start = {0: False, 1: False}
counter = dict()
for cid in range(cfg.NUM_CLUSTER):
    counter[cid] = 0 # = {0:0, 1:0} # {cid:counter, ...}
load_bucket = dict()

# def parse_stats_into_spans(stats, cluster_id, service):
#     spans = []
#     lines = stats.split("\n")
#     for i in range(1, len(lines)):
#         line = lines[i]
#         ss = line.split(" ")
#         ## NOTE: THIS SHOUD BE UPDATED WHEN member fields in span class is updated.
#         if len(ss) != 12:
#             print(f"{cfg.log_prefix} len(ss) != 12, {len(ss)}")
#             assert False
#         method = ss[0]
#         url = ss[1]
#         trace_id = ss[2]
#         my_span_id = ss[3]
#         parent_span_id = ss[4]
#         start = int(ss[5])
#         end = int(ss[6])
#         call_size = int(ss[7])
#         first_load = int(ss[8])
#         last_load = int(ss[9])
#         avg_load = int(ss[10])
#         rps = int(ss[11])
#         spans.append(sp.Span(method, url, service, cluster_id, trace_id, my_span_id, parent_span_id, start, end, first_load, last_load, avg_load, rps, call_size))
#     if len(spans) > 0:
#         print(f"{cfg.log_prefix} ==================================")
#         for span in spans:
#             print(f"{cfg.log_prefix} {span}")
#         print(f"{cfg.log_prefix} ==================================")
#     return spans



def is_this_trace_complete(single_trace):
    # TODO: Must be changed for other applications.
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
                    if span.my_span_id in span_exists:
                        ignore_cur = True
                        break
                    span_exists.append(span.my_span_id)
                    if ignore_cur:
                        app.logger.debug(f"{cfg.log_prefix} span exist, ignore_cur, cid,{span.cluster_id}, tid,{span.trace_id}, span_id,{span.my_span_id}")
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




def optimizer_entrypoint(sp_callgraph_table, ep_str_callgraph_table, endpoint_level_inflight_req, endpoint_level_rps, placement, coef_dict, all_endpoints, endpoint_to_cg_key):
    # latency_func[svc_name][ep]: trained regression model
    traffic_segmentation = 1
    objective = "avg_latency" # avg_latency, end_to_end_latency, multi_objective, egress_cost
    percentage_df, desc = opt.run_optimizer(coef_dict, endpoint_level_inflight_req, endpoint_level_rps,  placement, all_endpoints, endpoint_to_cg_key, sp_callgraph_table, ep_str_callgraph_table, traffic_segmentation, objective)
    ingress_gw_df = percentage_df[percentage_df['src']=='ingress_gw']
    for src_cid in range(cfg.NUM_CLUSTER):
        for dst_cid in range(cfg.NUM_CLUSTER):
            row = ingress_gw_df[(ingress_gw_df['src_cid']==src_cid) & (ingress_gw_df['dst_cid']==dst_cid)]
            if len(row) == 1:
                cluster_pcts[src_cid][dst_cid] = str(round(row['weight'].tolist()[0], 2))
            elif len(row) == 0:
                # empty means no routing from this src to this dst
                cluster_pcts[src_cid][dst_cid] = str(0)
            else:
                # It should not happen
                print(f"{cfg.log_prefix} [ERROR] length of row can't be greater than 1.")
                print(f"{cfg.log_prefix} row: {row}")
                assert len(row) <= 1
    return cluster_pcts


# Sample data
def train_linear_regression(data, y_col_name):
    df = pd.DataFrame(data)

    # Separate features and target
    x_colnames = list()
    for colname in df.columns:
        if colname != y_col_name:
            x_colnames.append(colname)
    X = df[x_colnames]
    y = df[y_col_name]
    # Standardize features using StandardScaler
    '''
    Use this if you want preprocessing like normalization, standardization, etc.
    '''
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
    # latency_func = dict()
    coef_dict = dict()
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
                coef_dict[svc_name][ep_str] = train_linear_regression(data, y_col)
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

def gen_endpoint_level_inflight_req(all_endpoints):
        endpoint_level_inflight_req = dict()
        for cid in all_endpoints:
            endpoint_level_inflight_req[cid] = dict()
            for svc_name in all_endpoints[cid]:
                endpoint_level_inflight_req[cid][svc_name] = dict()
                for ep in all_endpoints[cid][svc_name]:
                    ########################################################
                    # endpoint_level_inflight_req[cid][svc_name][ep] = random.randint(50, 60)
                    endpoint_level_inflight_req[cid][svc_name][ep] = 0
                    ########################################################
        return endpoint_level_inflight_req
    
def gen_endpoint_level_rps(all_endpoints):
    endpoint_level_rps = dict()
    for cid in all_endpoints:
        endpoint_level_rps[cid] = dict()
        for svc_name in all_endpoints[cid]:
            endpoint_level_rps[cid][svc_name] = dict()
            for ep in all_endpoints[cid][svc_name]:
                ########################################################
                # endpoint_level_rps[cid][svc_name][ep] = random.randint(10, 50)
                if cid == 0:
                    endpoint_level_rps[cid][svc_name][ep] = 10
                else:
                    endpoint_level_rps[cid][svc_name][ep] = 100
                ########################################################
    return endpoint_level_rps

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

if __name__ == "__main__":
    
    # scheduler = BackgroundScheduler()
    # scheduler.add_job(func=check_and_move_to_complete_trace, trigger="interval", seconds=1)
    # scheduler.start()
    # atexit.register(lambda: scheduler.shutdown())
    # app.run(host='0.0.0.0', port=8080)
    
    
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
    # for cid in all_endpoints:
    #     for svc_name in all_endpoints[cid]:
    #         print(f"all_endpoints[{cid}][{svc_name}]: {all_endpoints[cid][svc_name]}")
    # exit()
    tst.file_write_callgraph_table(sp_callgraph_table)
    placement = tst.get_placement_from_trace(stitched_traces)
    
    
    '''
    Train linear regression model
    The linear regression model is function of "inflight_req"
    '''
    coef_dict = train_latency_function_with_trace(stitched_traces)
    ## NOTE: overwriting coefficient for debugging
    for svc_name in coef_dict:
        for ep_str in coef_dict[svc_name]:
            for feature_ep in coef_dict[svc_name][ep_str]:
                if feature_ep == "intercept":
                    coef_dict[svc_name][ep_str][feature_ep] = 0
                else:
                    coef_dict[svc_name][ep_str][feature_ep] = 1
    for svc_name in coef_dict:
        for ep_str in coef_dict[svc_name]:
            print(f'coef_dict[{svc_name}][{ep_str}]: {coef_dict[svc_name][ep_str]}')
    
    '''
    Set load
    - rps(future incoming load): request per second
    - inflight_req(current): number of inflight requests in the system at the moment
    '''
    endpoint_level_inflight_req = gen_endpoint_level_inflight_req(all_endpoints)
    endpoint_level_rps = gen_endpoint_level_rps(all_endpoints)
    
    
    '''Entry point of optimizer'''
    optimizer_entrypoint(sp_callgraph_table, ep_str_callgraph_table, endpoint_level_inflight_req, endpoint_level_rps, placement, coef_dict, all_endpoints, endpoint_to_cg_key)
