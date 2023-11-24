#!/usr/bin/env python
# coding: utf-8

# In[31]:
import sys
sys.dont_write_bytecode = True

import time
import numpy as np  
import pandas as pd
import datetime
import graphviz
import gurobipy as gp
from gurobipy import GRB
import random
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.preprocessing import StandardScaler
from sklearn.compose import make_column_transformer
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline
from sklearn.metrics import r2_score
import gurobipy_pandas as gppd
from gurobi_ml import add_predictor_constr
import matplotlib.pyplot as plt
import math
import argparse
from pprint import pprint
from IPython.display import display
from global_controller import app
import time_stitching as tst
from config import *
import span as sp
import zlib


random.seed(1234)

timestamp_list = list()
def LOG_TIMESTAMP(event_name):
    timestamp_list.append([event_name, time.time()])
    if len(timestamp_list) > 1:
        dur = round(timestamp_list[-1][1] - timestamp_list[-2][1], 5)
        app.logger.debug(f"{log_prefix} Finished, {event_name}, duration,{dur}")

def prettyprint_timestamp():
    app.logger.info(f"{log_prefix} ** timestamp_list(ms)")
    for i in range(1, len(timestamp_list)):
        app.logger.info(f"{log_prefix} {timestamp_list[i][0]}, {timestamp_list[i][1] - timestamp_list[i-1][1]}")
        
def print_error(msg):
    exit_time = 5
    print("[ERROR] " + msg)
    print("EXIT PROGRAM in")
    for i in reversed(range(exit_time)) :
        print("{} seconds...".format(i))
        time.sleep(1)
    exit()


def count_cross_cluster_routing(percent_df):
    remote_routing = 0
    local_routing = 0
    for index, row in percent_df.iterrows():
        src_cid = row["src_cid"]
        dst_cid = row["dst_cid"]
        src_svc = row["src"]
        dst_svc = row["dst"]
        if src_cid != "*" and dst_cid != "*":
            if src_cid != dst_cid:
                remote_routing += row["flow"]
            else:
                local_routing += row["flow"]
    return remote_routing


def plot_request_flow(percent_df):
    g_ = graphviz.Digraph()
    node_pw = "1"
    edge_pw = "0.5"
    fs = "8"
    edge_fs_0 = "10"
    edge_fs_1 = "5"
    local_routing_edge_color = "black"
    remote_routing_edge_color = "blue"
    fn="times bold italic"
    edge_arrowsize="0.5"
    edge_minlen="1"
    src_and_dst_node_color = "#8587a8" # Gray
    node_color = ["#FFBF00", "#ff6375", "#6973fa", "#AFE1AF"] # yellow, pink, blue, green
    # node_color = ["#ff0000","#ff7f00","#ffff00","#7fff00","#00ff00","#00ff7f","#00ffff","#007fff","#0000ff","#7f00ff"] # rainbow
    name_cut = 6
    for index, row in percent_df.iterrows():
        src_cid = row["src_cid"]
        dst_cid = row["dst_cid"]
        src_svc = row["src"]
        dst_svc = row["dst"]
        if src_cid == '*' or  dst_cid == '*':
            edge_color = "black"
        else:
            if src_cid == dst_cid:
                edge_color =  local_routing_edge_color # local routing
            else:
                edge_color = remote_routing_edge_color # remote routing
        if src_cid == "*":
            src_node_color = src_and_dst_node_color
        else:
            src_node_color = node_color[src_cid]
        if dst_cid == '*':
            dst_node_color = src_and_dst_node_color
        else:
            dst_node_color = node_color[dst_cid]
        
        src_node_name = src_svc+str(src_cid)
        dst_node_name = dst_svc+str(dst_cid)
        g_.node(name=src_node_name, label=src_svc[:name_cut], shape='circle', style='filled', fillcolor=src_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        
        g_.node(name=dst_node_name, label=dst_svc[:name_cut], shape='circle', style='filled', fillcolor=dst_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        
        g_.edge(src_node_name, dst_node_name, label=str(row["flow"]) + " ("+str(int(row["weight"]*100))+"%)", penwidth=edge_pw, style="filled", fontsize=edge_fs_0, fontcolor=edge_color, color=edge_color, arrowsize=edge_arrowsize, minlen=edge_minlen)
            
    now =datetime .datetime.now()
    g_.render(OUTPUT_DIR + now.strftime("%Y%m%d_%H:%M:%S") + "_" + APP_NAME+ '_call_graph', view = True) # output: call_graph.pdf
    g_

def span_to_compute_arc_var_name(svc_name, cid):
    # return (svc_name+DELIMITER+str(cid)+DELIMITER+"start", svc_name+DELIMITER+str(cid)+DELIMITER+"end") # return type: tuple
    return f'{svc_name}{DELIMITER}{cid}{DELIMITER}start,{svc_name}{DELIMITER}{cid}{DELIMITER}end' # return type: tuple

def spans_to_network_arc_var_name(parent_name, src_cid, child_name, dst_cid):
    if parent_name == "src_*_*":
        src_postfix = "*"
    else:
        src_postfix = "end"
    if child_name == "dst_*_*":
        dst_postfix = "*"
    else:
        dst_postfix = "start"
    src_name = parent_name+DELIMITER+str(src_cid)+DELIMITER+src_postfix
    dst_name = child_name+DELIMITER+str(dst_cid)+DELIMITER+dst_postfix
    return (src_name, dst_name)


def check_network_arc_var_name(net_arc_var):
    if ENTRANCE == tst.FRONTEND_svc:
        if tst.REVIEW_V1_svc in unique_services:
            assert len(net_arc_var) == 14 # bookinfo, without ingress gw, two cluster set up
        else:
            assert len(net_arc_var) == 18 # bookinfo, without ingress gw, two cluster set up
    elif ENTRANCE == INGRESS_GW_NAME:
        if tst.REVIEW_V1_svc in unique_services:
            assert len(net_arc_var) == 18 # bookinfo, with ingress gw, two cluster set up
        elif PRODUCTPAGE_ONLY:
            assert len(net_arc_var) == 8
        else:
            print("len(network_arc_var_name):", len(network_arc_var_name))
            # assert len(network_arc_var_name) == 22 # bookinfo, with ingress gw, two cluster set up
    else:
        assert False
    for (src, dst), _ in net_arc_var.items():
        src_node = src.split(DELIMITER)[0]
        dst_node = dst.split(DELIMITER)[0]
        src_postfix = src.split(DELIMITER)[-1]
        dst_postfix = dst.split(DELIMITER)[-1]
        if src_node == source_name:
            assert dst_postfix == "start" 
        elif dst_node == destination_name:
            assert src_postfix == "end" 
        else:
            assert src_postfix == "end" 
            assert dst_postfix == "start" 

def translate_to_percentage(df_req_flow):
    src_list = list()
    dst_list = list()
    src_cid_list = list()
    dst_cid_list = list()
    flow_list = list()
    edge_name_list = list()
    edge_dict = dict()
    src_and_dst_index = list()
    for index, row in df_req_flow.iterrows():
        src_svc = row["From"].split(DELIMITER)[0]
        dst_svc = row["To"].split(DELIMITER)[0]
        src_cid = row["From"].split(DELIMITER)[1]
        dst_cid = row["To"].split(DELIMITER)[1]
        src_node_type = row["From"].split(DELIMITER)[2]
        dst_node_type = row["To"].split(DELIMITER)[2]
        if src_svc == source_name or dst_svc == destination_name or (src_node_type == "end" and dst_node_type == "start"):
            # print(src_svc)
            if src_svc != source_name:
                src_cid = int(src_cid)
            if dst_svc != destination_name:
                dst_cid = int(dst_cid)
            src_and_dst_index.append((src_svc, src_cid, dst_svc))
            src_list.append(src_svc)
            dst_list.append(dst_svc)
            src_cid_list.append(src_cid)
            dst_cid_list.append(dst_cid)
            flow_list.append(int(row["Flow"]))
            edge_name = src_svc+","+dst_svc
            edge_name_list.append(edge_name)
            if edge_name not in edge_dict:
                edge_dict[edge_name] = list()
            edge_dict[edge_name].append([src_cid,dst_cid,row["Flow"]])
    percentage_df = pd.DataFrame(
        data={
            "src": src_list,
            "dst": dst_list, 
            "src_cid": src_cid_list,
            "dst_cid": dst_cid_list,
            "flow": flow_list,
        },
        index = src_and_dst_index
    )
    percentage_df.index.name = "index_col"
    group_by_sum = percentage_df.groupby(['index_col']).sum()
    if DISPLAY:
        display(group_by_sum)
    
    total_list = list()
    for index, row in percentage_df.iterrows():
        total = group_by_sum.loc[[index]]["flow"].tolist()[0]
        total_list.append(total)
    percentage_df["total"] = total_list
    
    # app.logger.error(f"{log_prefix} percentage_df: {percentage_df}")
    
    weight_list = list()
    for index, row in percentage_df.iterrows():
        try:
            weight_list.append(row['flow']/row['total'])
        except Exception as e:
            app.logger.error(f"{log_prefix} ERROR: {e}")
            assert False
    percentage_df["weight"] = weight_list
    return percentage_df
'''
For interactive run with jupyternotebook, comment out following lines "COMMENT OUT FOR JUPYTER".
And adjust the indentation accordingly.
'''

# In[31]:

''' start of run_optimizer function '''
# def run_optimizer(raw_traces=None, trace_file=None, NUM_REQUESTS=[100,900], model_parameter=None): ## COMMENT_OUT_FOR_JUPYTER
NUM_REQUESTS = [50, 0]
for num_req in NUM_REQUESTS:
    assert num_req >= 0

callgraph = {'productpage-v1': ['details-v1', 'reviews-v3'], 'ratings-v1': [], 'details-v1': [], 'reviews-v3': ['ratings-v1']}
unique_service = dict()
unique_service[0] = ['productpage-v1', 'details-v1', 'reviews-v3', 'ratings-v1']
unique_service[1] = ['productpage-v1', 'details-v1', 'reviews-v3', 'ratings-v1']
depth_dict = {'productpage-v1': 1, 'details-v1': 2, 'reviews-v3': 2, 'ratings-v1': 3}
NUM_REQUESTS=[50, 0]
NUM_CLUSTER = len(NUM_REQUESTS)

if ENTRANCE == INGRESS_GW_NAME:
    callgraph[INGRESS_GW_NAME] = list()
    for parent_svc, children in callgraph.items():
        if parent_svc == tst.FRONTEND_svc:
            callgraph[INGRESS_GW_NAME].append(parent_svc)
    for parent_svc, child_svc_list in callgraph.items():
        app.logger.debug(f"{log_prefix} {parent_svc}: {child_svc_list}")
app.logger.info(f"{log_prefix} callgraph")
app.logger.info(f"{log_prefix} {callgraph}")
for i in range(NUM_CLUSTER):
    app.logger.info(f"{log_prefix} unique_service[{i}]: {unique_service[i]}")

svc_name_list = list()
compute_arc_var_name = list()
per_service_compute_arc = dict()
for cid in range(NUM_CLUSTER):
    for svc_name in unique_service[cid]:
        compute_arc_var_name.append(span_to_compute_arc_var_name(svc_name, cid))
        
network_arc_var_name = list()

        network_arc_var_name.append(span_to_network_arc_var_name(svc_name, cid))
        

def check_compute_arc_var_name(c_arc_var_name):
    for elem in c_arc_var_name:
        src_node = elem.split(",")[0]
        dst_node = elem.split(",")[1]
        
        src_svc_name = src_node.split(DELIMITER)[0]
        src_cid = src_node.split(DELIMITER)[1]
        src_node_type = src_node.split(DELIMITER)[2]
        dst_svc_name = dst_node.split(DELIMITER)[0]
        dst_cid = dst_node.split(DELIMITER)[1]
        dst_node_type = dst_node.split(DELIMITER)[2]
        
        if src_svc_name != dst_svc_name:
            print(f'src_svc_name != dst_svc_name, {src_svc_name} != {dst_svc_name}')
            assert False
        if src_cid != dst_cid:
            print(f'src_cid != dst_cid, {src_cid} != {dst_cid}')
            assert False
        if src_node_type != "start":
            print(f'src_node_type != "start", {src_node_type} != "start"')
            assert False
        if dst_node_type != "end":
            print(f'dst_node_type != "end", {dst_node_type} != "end"')
            assert False

check_compute_arc_var_name(compute_arc_var_name)
LOG_TIMESTAMP("defining compute_arc_var_name")
if DISPLAY:
    display(compute_arc_var_name)
    
MAX_LOAD = sum(NUM_REQUESTS)
compute_df = pd.DataFrame(
    # columns=["svc_name", "src_cid", "dst_cid", "min_compute_time", "max_compute_time", "min_load", "max_load", "min_compute_egress_cost", "max_compute_egress_cost", "compute_time", "compute_load", "observed_x", "observed_y", "latency_function", "predicted_y"],
    columns=["svc_name", "src_cid", "dst_cid", "min_compute_time", "min_load", "max_load", "min_egress_cost", "max_egress_cost", "observed_x", "observed_y", "latency_function"],
    data={
    },
    index=compute_arc_var_name
)
svc_list = list()
src_cid_list = list()
dst_cid_list = list()
# for tup in list(compute_arc_var_name):
for var_name in compute_arc_var_name:
    svc_list.append(var_name.split(",")[0].split(DELIMITER)[0])
    src_cid_list.append(int(var_name.split(",")[0].split(DELIMITER)[1]))
    dst_cid_list.append(int(var_name.split(",")[1].split(DELIMITER)[1]))
# print("svc_list: ", svc_list)
# print("src_cid_list: ", src_cid_list)
# print("dst_cid_list: ", dst_cid_list)


# In[31]:

compute_df["svc_name"] = svc_list
compute_df["src_cid"] = src_cid_list
compute_df["dst_cid"] = dst_cid_list
compute_df["min_compute_time"] = 0
# compute_df["max_compute_time"] = math.inf
compute_df["min_load"] = 0
compute_df["max_load"] = MAX_LOAD
compute_df["min_egress_cost"] = 0
compute_df["max_egress_cost"] = 0
optimizer_start_time = time.time()
model = gp.Model('RequestRouting')

# for index, row in compute_df.iterrows():
#     compute_df.at[index, 'compute_time'] = \
#         model.addVar(name="compute_time", lb=row["min_compute_time"])
#     compute_df.at[index, 'compute_load'] = \
#         model.addVar(name="compute_load", lb=row["min_load"], ub=row["max_load"])
display(compute_df)


# In[35]:

def gen_fake_data(c_df):
    num_data_point = 50
    load_ = list(np.arange(0,num_data_point))
    for index, row in c_df.iterrows():
        comp_t = list()
        # slope = zlib.adler32(row["svc_name"].encode('utf-8'))%5+1
        # slope = zlib.adler32((str(row["src_cid"])+row["svc_name"]).encode('utf-8'))%10+1
        # slope = (zlib.adler32(row["svc_name"].encode('utf-8'))%5+1)/(row["src_cid"]+1)
        slope = 0
        intercept = 0
        if row["src_cid"] == 0 and row["svc_name"] == tst.FRONTEND_svc:
            slope = 1
            intercept = 0
        for j in range(num_data_point):
            comp_t.append(pow(load_[j],REGRESSOR_DEGREE)*slope + intercept)
        print(f'** cid,{row["src_cid"]}, service,{row["svc_name"]}, degree({REGRESSOR_DEGREE}), slope({slope}), intercept({intercept})')
        assert len(load_) == len(comp_t)
        # c_df.at[index, "observed_x"] = np.array(load_).reshape(-1, 1)
        c_df.at[index, "observed_x"] = np.array(load_)
        c_df.at[index, "observed_y"] = np.array(comp_t)
    return c_df

compute_df = gen_fake_data(compute_df)
display(compute_df)



# In[38]:

for index, row in compute_df.iterrows():
    feat_transform = make_column_transformer(
        (StandardScaler(), ["observed_x"]),
        # ("passthrough", ["ld"]),
        verbose_feature_names_out=False,
        remainder='drop'
    )
    if REGRESSOR_DEGREE == 1:
        reg = make_pipeline(feat_transform, LinearRegression())
    elif REGRESSOR_DEGREE > 1:
        poly = PolynomialFeatures(degree=REGRESSOR_DEGREE, include_bias=True)
        reg = make_pipeline(feat_transform, poly, LinearRegression())
    temp_df = pd.DataFrame(
        data={
            "observed_x": row["observed_x"],
            "observed_y": row["observed_y"],
        }
    )
    X = temp_df[["observed_x"]]
    y = row["observed_y"]
    X_train, X_test, y_train, y_test = train_test_split(X, y,train_size=0.9, random_state=1)
    reg.fit(X_train, y_train)
    if svc_name != tst.FRONTEND_svc:
        if REGRESSOR_DEGREE == 1:
            if reg["linearregression"].coef_ < 0:
                new_c = np.array([0.])
                reg["linearregression"].coef_ = new_c
                app.logger.info(f"{log_prefix} Service {svc_name}, changed slope {c_} --> {new_c}, intercept: {in_}")
                assert False
        if REGRESSOR_DEGREE == 2:
            # print("c_[2]: ", c_[2])
            if reg["linearregression"].coef_[1] < 0:
                new_c = np.array([0., 0.])
                reg["linearregression"].coef_ = new_c
                app.logger.info(f"{log_prefix} Service {svc_name}, changed slope {c_} --> {new_c}, intercept: {in_}")
                assert False
    c_ = reg["linearregression"].coef_
    in_ = reg["linearregression"].intercept_
    y_pred = reg.predict(X_test)
    r2 =  np.round(r2_score(y_test, y_pred),2)
    app.logger.info(f"{log_prefix} {svc_name}, slope: {c_}, intercept: {in_}")
    compute_df.at[index, 'latency_function'] = reg
    
display(compute_df)


# In[38]:
    
# regressor_dict = dict()
# for cid in range(NUM_CLUSTER):
#     if cid not in regressor_dict:
#         regressor_dict[cid] = dict()
#     cid_df =  ct_obs[ct_obs["cluster_id"]==cid]
#     for svc_name in unique_services:
#         temp_df = cid_df[cid_df["service_name"] == svc_name]
#         X = temp_df[["ld"]]
#         y = temp_df["ct"]
#         display(X)
#         display(y)
#         temp_x = X.copy()
#         for i in range(max(temp_x["ld"])):
#             temp_x.iloc[i, 0] = i
#         X_train, X_test, y_train, y_test = train_test_split(X, y,train_size=0.9, random_state=1)
#         feat_transform = make_column_transformer(
#             (StandardScaler(), ["ld"]),
#             # ("passthrough", ["ld"]),
#             verbose_feature_names_out=False,
#             remainder='drop'
#         )
#         if REGRESSOR_DEGREE == 1:
#             regressor_dict[cid][svc_name] = make_pipeline(feat_transform, LinearRegression())
#         elif REGRESSOR_DEGREE > 1:
#             poly = PolynomialFeatures(degree=REGRESSOR_DEGREE, include_bias=True)
#             regressor_dict[cid][svc_name] = make_pipeline(feat_transform, poly, LinearRegression())
#         regressor_dict[cid][svc_name].fit(X_train, y_train)
#         if svc_name != tst.FRONTEND_svc:
#             if REGRESSOR_DEGREE == 1:
#                 if c_ < 0:
#                     new_c = np.array([0.])
#                     regressor_dict[cid][svc_name]["linearregression"].coef_ = new_c
#                     app.logger.info(f"{log_prefix} Service {svc_name}, changed slope {c_} --> {new_c}, intercept: {in_}")
#                     assert False
#             if REGRESSOR_DEGREE == 2:
#                 # print("c_[2]: ", c_[2])
#                 if c_[1] < 0:
#                     new_c = np.array([0., 0.])
#                     regressor_dict[cid][svc_name]["linearregression"].coef_ = new_c
#                     app.logger.info(f"{log_prefix} Service {svc_name}, changed slope {c_} --> {new_c}, intercept: {in_}")
#                     assert False
#         y_pred = regressor_dict[cid][svc_name].predict(X_test)
#         c_ = regressor_dict[cid][svc_name]["linearregression"].coef_
#         in_ = regressor_dict[cid][svc_name]["linearregression"].intercept_
#         r2 =  np.round(r2_score(y_test, y_pred),2)
#         app.logger.info(f"{log_prefix} {svc_name}, slope: {c_}, intercept: {in_}, R^2: {r2}")


# In[38]:


def plot_latency_function(df):
    idx = 0
    num_subplot_row = NUM_CLUSTER
    num_subplot_col = 5
    fig, (plot_list) = plt.subplots(num_subplot_row, num_subplot_col, figsize=(16,6))
    fig.tight_layout()
    for index, row in df.iterrows():
        temp_df = pd.DataFrame(
            data={
                "observed_x": row["observed_x"],
                "observed_y": row["observed_y"],
            }
        )
        X = temp_df[["observed_x"]]
        y = row["observed_y"]
        row_idx = int(idx/num_subplot_col)
        col_idx = idx%num_subplot_col
        plot_list[row_idx][col_idx].plot(row["observed_x"], row["observed_y"], 'ro', label="observation", alpha=0.1)
        plot_list[row_idx][col_idx].plot(row["observed_x"], row["latency_function"].predict(X), 'bo', label="prediction", alpha=0.1)
        plot_list[row_idx][col_idx].legend()
        plot_list[row_idx][col_idx].set_title(svc_name)
        if row_idx == num_subplot_row-1:
            plot_list[row_idx][col_idx].set_xlabel("ld")
        if col_idx == 0:
            plot_list[row_idx][col_idx].set_ylabel("Compute time")
        idx += 1
    plt.savefig(OUTPUT_DIR+datetime.datetime.now().strftime("%Y%m%d_%H:%M:%S") +"-latency.pdf")
    plt.show()
if PLOT:
    plot_latency_function(compute_df)
    
LOG_TIMESTAMP("train regression model")

# In[42]:


# compute_egress_cost_data = dict()
# for cid in range(NUM_CLUSTER):
#     if cid not in compute_egress_cost_data:
#         compute_egress_cost_data[cid] = dict()
#     for svc_name in unique_services:
#         compute_egress_cost_data[cid][svc_name] = pd.DataFrame(
#             data={
#                 "min_compute_egress_cost": [0],
#                 "max_compute_egress_cost": [0],
#             },
#             index=span_to_compute_arc_var_name(svc_name, cid)
#         )
#         print(f"compute_egress_cost_data[{cid}][{svc_name}]")
#         display(compute_egress_cost_data[cid][svc_name])
        
# compute_time_data = dict()
# for svc_name in unique_services:
#     compute_time_data[svc_name] = pd.DataFrame(
#         data={
#             "min_load":[min_load] * len(per_service_compute_arc[svc_name]),
#             "max_load":[max_load] * len(per_service_compute_arc[svc_name]),
#             "min_compute_time": [0] * len(per_service_compute_arc[svc_name]),
#             # "max_compute_time": [max_compute_time[svc_name]] * len(per_service_compute_arc[svc_name]),
#         },
#         index=per_service_compute_arc[svc_name]
#     )
#     print(f"compute_time_data[{svc_name}]")
#     display(compute_time_data[svc_name])

# compute_time = dict()
# compute_load = dict()
# for svc_name in unique_services:
#     compute_time[svc_name] = gppd.add_vars(model, compute_time_data[svc_name], name="compute_time", lb="min_compute_time")
#     compute_load[svc_name] = gppd.add_vars(model, compute_time_data[svc_name], name="load_for_compute_edge", lb="min_load", ub="max_load")
# print("compute_time")
# print(compute_time)
# print("compute_load")
# print(compute_load)
# model.update()


# In[42]:

compute_time = dict()
compute_load = dict()
display(compute_df["svc_name"])
for index, row in compute_df.iterrows():
    row_to_df = pd.DataFrame([row], index=[index])
    compute_time[index] = gppd.add_vars(model, row_to_df, name="compute_time", lb="min_compute_time")
    compute_load[index] = gppd.add_vars(model, row_to_df, name="load_for_compute_edge", lb="min_load", ub="max_load")
model.update()
print("compute_time")
print(compute_time)
print("compute_load")
print(compute_load)


# In[44]:

m_feats = dict()
for index, row in compute_df.iterrows():
    print("index: ", index)
    m_feats[index] = pd.DataFrame(
        data={
            "observed_x": compute_load[index],
        },
        index=[index]
    )
    # print(m_feats[index])
    # print()
    # print(f"compute_load[{index}]: {compute_load[index]}")
    # print()
    # print(f"compute_time[{index}]: {compute_time[index]}")
    # print("index: ", index)
    # print(f'row["latency_function"]: {row["latency_function"]}')
    # print(f'row["latency_func"]["linearregression"].coef_" {row["latency_function"]["linearregression"].coef_}')
    # print(f'row["latency_func"]["linearregression"].intercept_" {row["latency_function"]["linearregression"].intercept_}')
    # print(f'compute_time[{index}]: {compute_time[index]}')
    pred_constr = add_predictor_constr(model, row["latency_function"], m_feats[index], compute_time[index])
    pred_constr.print_stats()

print(m_feats)

model.update()

# In[44]:


# compute_egress_cost_data = dict()
# for cid in range(NUM_CLUSTER):
#     if cid not in compute_egress_cost_data:
#         compute_egress_cost_data[cid] = dict()
#     for svc_name in unique_services:
#         compute_egress_cost_data[cid][svc_name] = pd.DataFrame(
#             data={
#                 "min_compute_egress_cost": [0],
#                 "max_compute_egress_cost": [0],
#             },
#             index=span_to_compute_arc_var_name(svc_name, cid)
#         )
#         print(f"compute_egress_cost_data[{cid}][{svc_name}]")
#         display(compute_egress_cost_data[cid][svc_name])
        


# In[35]:


## Define names of the variables for network arc in gurobi
source_name = "src_*_*"
destination_name = "dst_*_*"
source_node = source_name+DELIMITER+"*"+DELIMITER+"*"
destination_node = destination_name+DELIMITER+"*"+DELIMITER+"*"

'''
network_arc_var_name
- key: tuple(src_node_name, dst_node_name)
- value: request_size_in_bytes
'''
network_arc_var_name = dict()
for parent_svc, children in callgraph.items():
    if len(children) == 0: # leaf service
        # leaf service to dst
        print(parent_svc + " is leaf service")
        for src_cid in range(NUM_CLUSTER):
            tuple_var_name = spans_to_network_arc_var_name(parent_svc, src_cid, destination_name, "*")
            if tuple_var_name not in network_arc_var_name:
                network_arc_var_name[tuple_var_name] = 0 # arbitrary call size
    for child_svc in children:
        if parent_svc == ENTRANCE:
            for src_cid in range(NUM_CLUSTER):
                # src to ingress gateway
                tuple_var_name = spans_to_network_arc_var_name(source_name, "*", parent_svc, src_cid)
                if tuple_var_name not in network_arc_var_name:
                    network_arc_var_name[tuple_var_name] = 0 # arbitrary call size
                for dst_cid in range(NUM_CLUSTER):
                    tuple_var_name = spans_to_network_arc_var_name(parent_svc, src_cid, child_svc, dst_cid)
                    if tuple_var_name not in network_arc_var_name:
                        # ingress gateway to frontend service
                        network_arc_var_name[tuple_var_name] = 1 # arbitrary call size
        else:
            # service to service
            for src_cid in range(NUM_CLUSTER):
                for dst_cid in range(NUM_CLUSTER):
                    tuple_var_name = spans_to_network_arc_var_name(parent_svc, src_cid, child_svc, dst_cid)
                    if tuple_var_name not in network_arc_var_name:
                        network_arc_var_name[tuple_var_name] = depth_dict[parent_svc]*10 # arbitrary call size
app.logger.info(f"{log_prefix} len(network_arc_var_name): {len(network_arc_var_name)}\n")
for tuple_var_name, _ in network_arc_var_name.items():
    app.logger.debug(f"{log_prefix} {tuple_var_name}")

for cid in range(NUM_CLUSTER):
    check_network_arc_var_name(network_arc_var_name[cid])
if DISPLAY:
    display(network_arc_var_name)


# In[39]:


network_arc_var_name_list = list(network_arc_var_name.keys())
network_arc_var_name_list
network_arc_var_name

list(network_arc_var_name.keys())


# In[41]:


min_load = 0
max_load = sum(NUM_REQUESTS)
print("max_load = sum(NUM_REQUESTS): ", max_load)

min_network_egress_cost = list()
max_network_egress_cost = list()

network_arc_var_name_list = list(network_arc_var_name.keys())
print("network_arc_var_name_list")
print(network_arc_var_name_list)
for network_arc_var in network_arc_var_name_list:
    src_node = network_arc_var[0]
    dst_node = network_arc_var[1]
    src_svc_name = src_node.split(DELIMITER)[0] # A
    dst_svc_name = dst_node.split(DELIMITER)[0] # B
    if src_svc_name == "src_*_*":
        min_network_egress_cost.append(0)
        max_network_egress_cost.append(0)
    elif dst_svc_name == "dst_*_*":
        min_network_egress_cost.append(0)
        max_network_egress_cost.append(0)
    else:
        try:
            src_cid = int(src_node.split(DELIMITER)[1])
        except:
            app.logger.error(f"{log_prefix} Can't parse src_cid {src_svc_name}, {src_node}, {src_node.split(DELIMITER)}")
            assert False
        try:
            dst_cid = int(dst_node.split(DELIMITER)[1])
        except:
            app.logger.error(f"{log_prefix}  Can't parse src_cid {dst_svc_name}, {dst_node}, {dst_node.split(DELIMITER)}")
            assert False
        if src_cid == dst_cid:
            # local routing
            min_network_egress_cost.append(0) 
            max_network_egress_cost.append(0)
        else:
            # remote routing
            min_network_egress_cost.append(network_arc_var_name[network_arc_var])
            max_network_egress_cost.append(network_arc_var_name[network_arc_var])

display(network_arc_var_name)
display(min_network_egress_cost)
display(max_network_egress_cost)

network_egress_cost_data = pd.DataFrame(
    data={
        "min_network_egress_cost": min_network_egress_cost,
        "max_network_egress_cost": max_network_egress_cost,
        # "min_load":[min_load]*len(network_arc_var_name_list),
        # "max_load":[max_load]*len(network_arc_var_name_list),
    },
    index=network_arc_var_name_list
    # index=network_arc_var_name
)
network_egress_cost_data


# In[43]:


min_network_latency = list()
max_network_latency = list()
for network_arc_var in network_arc_var_name_list:
    src_node = network_arc_var[0]
    dst_node = network_arc_var[1]
    
    src_svc_name = src_node.split(DELIMITER)[0]
    dst_svc_name = dst_node.split(DELIMITER)[0]
    if src_svc_name == "src_*_*":
        min_network_latency.append(0)
        max_network_latency.append(0)
    elif dst_svc_name == "dst_*_*":
        min_network_latency.append(0)
        max_network_latency.append(0)
    else:
        try:
            src_idx = int(src_node.split(DELIMITER)[1])
        except:
            print_error(src_svc_name, src_node.split(DELIMITER))
        try:
            dst_idx = int(dst_node.split(DELIMITER)[1])
        except:
            print_error(dst_svc_name, dst_node.split(DELIMITER))
        # Network latency for local routing
        if src_idx == dst_idx:
            app.logger.debug(f"{log_prefix} intra-cluster, {src_node}, {dst_node}")
            min_network_latency.append(INTRA_CLUTER_RTT)
            max_network_latency.append(INTRA_CLUTER_RTT)
        # Network latency for remote routing
        else:
            app.logger.debug(f"{log_prefix} inter-cluster, {src_node}, {dst_node}")
            min_network_latency.append(INTER_CLUSTER_RTT)
            max_network_latency.append(INTER_CLUSTER_RTT)

network_latency_data = pd.DataFrame(
    data={
        "min_network_latency": min_network_latency,
        "max_network_latency": max_network_latency,
        "min_load":[min_load]*len(network_arc_var_name_list),
        "max_load":[max_load]*len(network_arc_var_name_list),
    },
    index=network_arc_var_name_list
    # index=network_arc_var_name
)
LOG_TIMESTAMP("creating egress cost and compute/network latency dataframe")
print("network_latency_data")
display(network_latency_data)



# In[44]:

network_latency = gppd.add_vars(model, network_latency_data, name="network_latency", lb="min_network_latency", ub="max_network_latency")

network_load = gppd.add_vars(model, network_latency_data, name="load_for_network_edge", lb="min_load", ub="max_load")
# network_load = gppd.add_vars(model, network_latency_data, name="load_for_network_edge")

model.update()

network_egress_cost = gppd.add_vars(model, network_egress_cost_data, name="network_egress_cost", lb="min_network_egress_cost", ub="max_network_egress_cost")

compute_egress_cost = dict()
# for svc_name in unique_services:
for index, row in compute_df.iterrows():
    row_to_df = pd.DataFrame([row], index=[index])
    compute_egress_cost[index] = gppd.add_vars(model, row_to_df, name="compute_egress_cost", lb="min_egress_cost", ub="max_egress_cost")
model.update()

# egress cost sum
network_egress_cost_sum = sum(network_egress_cost.multiply(network_load))
compute_egress_cost_sum = 0
# for svc_name in unique_services:
for elem in compute_arc_var_name:
    compute_egress_cost_sum += sum(compute_egress_cost[elem].multiply(compute_load[elem]))
total_egress_sum = network_egress_cost_sum + compute_egress_cost_sum
app.logger.debug(f"{log_prefix} total_egress_sum:")
app.logger.debug(f"{log_prefix} {total_egress_sum}\n")

# total latency sum
network_latency_sum = sum(network_latency.multiply(network_load))

compute_latency_sum = 0
# for svc_name in unique_services:
for elem in compute_arc_var_name:
    compute_latency_sum += sum(compute_time[elem].multiply(m_feats[elem]["observed_x"])) # m_feats[svc_name]["load"] is identical to compute_load[svc_name]
    # print("compute_latency_sum, ", svc_name)
    # display(compute_latency_sum)
# print()
# print("network_latency_sum")
# print(network_latency_sum)
# print()
# print("compute_latency_sum")
# print(compute_latency_sum)
total_latency_sum = network_latency_sum + compute_latency_sum

app.logger.debug(f"{log_prefix} compute_latency_sum:")
app.logger.debug(f"{log_prefix} {compute_latency_sum}\n")

app.logger.debug(f"{log_prefix} network_latency_sum:")
app.logger.debug(f"{log_prefix} {network_latency_sum}\n")

app.logger.debug(f"{log_prefix} total_latency_sum:")
app.logger.debug(f"{log_prefix} {total_latency_sum}\n")

objective = "latency" # latency or egress_cost or multi-objective
if objective == "latency":
    # model.setObjective(total_latency_sum, gp.GRB.MINIMIZE)
    model.setObjective(compute_latency_sum, gp.GRB.MINIMIZE)
elif objective == "egress_cost":
    model.setObjective(total_egress_sum, gp.GRB.MINIMIZE)
elif objective == "multi-objective":
    # NOTE: higher dollar per ms, more important the latency
    # DOLLAR_PER_MS: value of latency
    # lower dollar per ms, less tempting to re-route since bandwidth cost is becoming more important
    # simply speaking, when we have DOLLAR_PER_MS decreased, less offloading.
    model.setObjective(total_latency_sum*DOLLAR_PER_MS + total_egress_sum, gp.GRB.MINIMIZE)
else:
    print_error("unsupported objective, ", objective)
    
model.update()
app.logger.info(f"{log_prefix} model objective: {model.getObjective()}")

# arcs is the keys
# aggregated_load is dictionary
concat_compute_load = pd.Series()
# for svc_name, c_load in compute_load.items():

for elem in compute_arc_var_name:
    concat_compute_load = pd.concat([concat_compute_load, compute_load[elem]], axis=0)
arcs, aggregated_load = gp.multidict(pd.concat([network_load, concat_compute_load], axis=0).to_dict())

###################################################
# max_tput = dict()
# tput = 100000
# for svc_name in unique_services:
#     for cid in range(NUM_CLUSTER):
#         # if repl.service.name != "User":
#         max_tput[svc_name+DELIMITER+str(cid)+DELIMITER+"start"] = tput
#         max_tput[svc_name+DELIMITER+str(cid)+DELIMITER+"end"] = tput
# app.logger.info(f"{log_prefix} max_tput: {max_tput}")

LOG_TIMESTAMP("gurobi add_vars and set objective")


# In[45]:

constraint_setup_start_time = time.time()
###################################################
# Constraint 1: source
source = dict()
TOTAL_NUM_REQUEST = sum(NUM_REQUESTS)
source[source_node] = TOTAL_NUM_REQUEST
src_keys = source.keys()

# source(src_*_*) to *
src_flow = model.addConstrs((gp.quicksum(aggregated_load.select(src, '*')) == source[src] for src in src_keys), name="source")

####################################################################
# * to frontend services start node
if LOAD_IN == True:
    for cid in range(NUM_CLUSTER):
        #############################################################################
        # start_node = tst.FRONTEND_svc + DELIMITER + str(cid) + DELIMITER + "start"
        # end_node = tst.FRONTEND_svc + DELIMITER + str(cid) + DELIMITER + "end"
        start_node = ENTRANCE + DELIMITER + str(cid) + DELIMITER + "start"
        # end_node = INGRESS_GW_NAME + DELIMITER + str(cid) + DELIMITER + "end"
        #############################################################################
        
        per_cluster_load_in = model.addConstr((gp.quicksum(aggregated_load.select('*', start_node)) == NUM_REQUESTS[cid]), name="cluster_"+str(cid)+"_load_in")

# if ENTRANCE == INGRESS_GW_NAME:
#     # # frontend services end node to child nodes
#     for cid in range(NUM_CLUSTER):
#         ##################################
#         # start_node = tst.FRONTEND_svc + DELIMITER + str(cid) + DELIMITER + "start"
#         # end_node = tst.FRONTEND_svc + DELIMITER + str(cid) + DELIMITER + "end"
#         # start_node = INGRESS_GW_NAME + DELIMITER + str(cid) + DELIMITER + "start"
#         end_node = ENTRANCE + DELIMITER + str(cid) + DELIMITER + "end"
#         ##################################
#         per_cluster_load_out = model.addConstr((gp.quicksum(aggregated_load.select(end_node, '*')) == NUM_REQUESTS[cid]), name="cluster_"+str(cid)+"_load_out")
    
####################################################################

model.update()


# In[47]:


###################################################
# Constraint 2: destination
destination = dict()
destination[destination_node] = TOTAL_NUM_REQUEST
dest_keys = destination.keys()
leaf_services = list()
for parent_svc, children in callgraph.items():
    if len(children) == 0: # leaf service
        leaf_services.append(parent_svc)
num_leaf_services = len(leaf_services)
app.logger.debug(f"{log_prefix} num_leaf_services: {num_leaf_services}")
app.logger.debug(f"{log_prefix} leaf_services: {leaf_services}")

dst_flow = model.addConstrs((gp.quicksum(aggregated_load.select('*', dst)) == destination[dst]*num_leaf_services for dst in dest_keys), name="destination")
model.update()

###################################################
# Constraint 3: flow conservation

# Start node in-out flow conservation
for svc_name in unique_services:
    for cid in range(NUM_CLUSTER):
        start_node = svc_name + DELIMITER + str(cid) + DELIMITER + "start"
        node_flow = model.addConstr((gp.quicksum(aggregated_load.select('*', start_node)) == gp.quicksum(aggregated_load.select(start_node, '*'))), name="flow_conservation["+start_node+"]-start_node")
    

# End node in-out flow conservation
# case 1 (start node, end&leaf node): incoming num requests == outgoing num request for all nodes
for parent_svc, children in callgraph.items():
    for cid in range(NUM_CLUSTER):
        if len(children) == 0: # leaf_services:
            end_node = parent_svc + DELIMITER + str(cid) + DELIMITER + "end"
            node_flow = model.addConstr((gp.quicksum(aggregated_load.select('*', end_node)) == gp.quicksum(aggregated_load.select(end_node, '*'))), name="flow_conservation["+end_node+"]-leaf_endnode")

# case 2 (end&non-leaf node): incoming num requests == outgoing num request for all nodes
for parent_svc, children in callgraph.items():
    if len(children) > 0: # non-leaf services:
        for parent_cid in range(NUM_CLUSTER):
            end_node = parent_svc + DELIMITER + str(parent_cid) + DELIMITER + "end"
            for child_svc in children:
                out_sum = 0
                child_list = list()
                for child_cid in range(NUM_CLUSTER):
                    child_start_node = child_svc +DELIMITER + str(child_cid) + DELIMITER+"start"
                    child_list.append(child_start_node)
                    out_sum += aggregated_load.sum(end_node, child_start_node)
                node_flow = model.addConstr((gp.quicksum(aggregated_load.select('*', end_node)) == out_sum), name="flow_conservation["+end_node+"]-nonleaf_endnode")
                app.logger.debug(f"{log_prefix} nonleaf end_node flow conservation")
                app.logger.debug(f"{log_prefix} {end_node}, {child_list}")
model.update()


# In[48]:


###################################################
# Constraint 4: Tree topology
for svc_name in unique_services:
    #####################################
    # if svc_name != tst.FRONTEND_svc:
    if svc_name != ENTRANCE:
    #####################################
        sum_ = 0
        for cid in range(NUM_CLUSTER):
            node_name = svc_name +DELIMITER + str(cid) + DELIMITER+"start"
            sum_ += aggregated_load.sum('*', node_name)
        node_flow = model.addConstr(sum_ == TOTAL_NUM_REQUEST, name="tree_topo_conservation")
model.update()

###################################################
# # Constraint 5: max throughput of service
# max_tput_key = max_tput.keys()
# throughput = model.addConstrs((gp.quicksum(aggregated_load.select('*', n_)) <= max_tput[n_] for n_ in max_tput_key), name="service_capacity")
# constraint_setup_end_time = time.time()
###################################################

# Lazy update for model
LOG_TIMESTAMP("gurobi add constraints and model update")


# In[49]:


varInfo = [(v.varName, v.LB, v.UB) for v in model.getVars() ]
df_var = pd.DataFrame(varInfo) # convert to pandas dataframe
df_var.columns=['Variable Name','LB','UB'] # Add column headers
if OUTPUT_WRITE:
    df_var.to_csv(OUTPUT_DIR+datetime.datetime.now().strftime("%Y%m%d_%H:%M:%S") +"-variable.csv")
if DISPLAY:
    with pd.option_context('display.max_colwidth', None):
        with pd.option_context('display.max_rows', None):
            display(df_var)


constrInfo = [(c.constrName, model.getRow(c), c.Sense, c.RHS) for c in model.getConstrs() ]
df_constr = pd.DataFrame(constrInfo)
df_constr.columns=['Constraint Name','Constraint equation', 'Sense','RHS']
if OUTPUT_WRITE:
    df_constr.to_csv(OUTPUT_DIR+datetime.datetime.now().strftime("%Y%m%d_%H:%M:%S") +"-constraint.csv")
if DISPLAY:
    with pd.option_context('display.max_colwidth', None):
        with pd.option_context('display.max_rows', None):
            display(df_constr)


# In[51]:


## Defining objective function
model.setParam('NonConvex', 2)
solve_start_time = time.time()
model.update()
gurobi_key = open("./gurobi.wls", "r")
options = dict()
for line in gurobi_key:
    line = line.strip()
    # print("line: ", line)
    if line == "":
        continue
    key, value = line.split(",")
    if key == "LICENSEID":
        value = int(value)
    options[key] = value
# print("options: ", options)
env = gp.Env(params=options)
gp.Model(env=env)
model.optimize()
print("*"*20)
print(arcs)
print("*"*20)
# option 3
#model.optimize()
#########################################################
solve_end_time = time.time()
LOG_TIMESTAMP("MODEL OPTIMIZE")

## Not belonging to optimizer critical path
ts = time.time()
## Variable info
varInfo = [(v.varName, v.LB, v.UB) for v in model.getVars() ] # use list comprehension
df_var = pd.DataFrame(varInfo) # convert to pandas dataframe
df_var.columns=['Variable Name','LB','UB'] # Add column headers
num_var = len(df_var)

## Linear constraint info
constrInfo = [(c.constrName, model.getRow(c), c.Sense, c.RHS) for c in model.getConstrs() ]
df_constr = pd.DataFrame(constrInfo)
df_constr.columns=['Constraint Name','Constraint equation', 'Sense','RHS']
num_constr = len(df_constr)
substract_time = time.time() - ts
if DISPLAY:
    display(df_constr)
LOG_TIMESTAMP("get var and constraint")

app.logger.info(f"{log_prefix} model.Status: {model.Status}")
app.logger.info(f"{log_prefix} NUM_REQUESTS: {NUM_REQUESTS}")
if model.Status != GRB.OPTIMAL:
    app.logger.info(f"{log_prefix} XXXXXXXXXXXXXXXXXXXXXXXXXXX")
    app.logger.info(f"{log_prefix} XXXX INFEASIBLE MODEL! XXXX")
    app.logger.info(f"{log_prefix} XXXXXXXXXXXXXXXXXXXXXXXXXXX")
    # with pd.option_context('display.max_colwidth', None):
        # with pd.option_context('display.max_rows', None):
            # display(df_var)
    if DISPLAY:
        display(df_constr)
    
    model.computeIIS()
    model.write("model.ilp")
    print('\nThe following constraints and variables are in the IIS:')
    # for c in model.getConstrs():
    #     if c.IISConstr: print(f'\t{c.constrname}: {model.getRow(c)} {c.Sense} {c.RHS}')
    for v in model.getVars():
        if v.IISLB: print(f'\t{v.varname} ≥ {v.LB}')
        if v.IISUB: print(f'\t{v.varname} ≤ {v.UB}')
    print("OPTIMIZER, INFEASIBLE MODEL")
else:
    app.logger.info(f"{log_prefix} ooooooooooooooooooooooo")
    app.logger.info(f"{log_prefix} oooo SOLVED MODEL! oooo")
    app.logger.info(f"{log_prefix} ooooooooooooooooooooooo")

    ## Print out the result
    optimize_end_time = time.time()
    optimizer_runtime = round((optimize_end_time - optimizer_start_time) - substract_time, 5)
    solve_runtime = round(solve_end_time - solve_start_time, 5)
    # constraint_setup_time = round(constraint_setup_end_time - constraint_setup_start_time, 5)
    app.logger.error(f"{log_prefix} ** Objective: {objective}")
    app.logger.error(f"{log_prefix} ** Num constraints: {num_constr}")
    app.logger.error(f"{log_prefix} ** Num variables: {num_var}")
    app.logger.error(f"{log_prefix} ** Optimization runtime: {optimizer_runtime} ms")
    app.logger.error(f"{log_prefix} ** model.optimize() runtime: {solve_runtime} ms")
    # app.logger.error(f"{log_prefix} ** constraint_setup_time runtime: {} ms".format(constraint_setup_time))
    app.logger.error(f"{log_prefix} ** model.objVal: {model.objVal}")
    app.logger.error(f"{log_prefix} ** model.objVal / total num requests: {model.objVal/TOTAL_NUM_REQUEST}")
    request_flow = pd.DataFrame(columns=["From", "To", "Flow"])
    for arc in arcs:
        if aggregated_load[arc].x > 1e-6:
            temp = pd.DataFrame({"From": [arc[0]], "To": [arc[1]], "Flow": [aggregated_load[arc].x]})
            request_flow = pd.concat([request_flow, temp], ignore_index=True)
    if DISPLAY:
        display(request_flow)
    percentage_df = translate_to_percentage(request_flow)
    if DISPLAY:
        display(percentage_df)
        
    # prettyprint_timestamp()
    # return percentage_df, "OPTIMIZER, MODEL SOLVED"
''' This is end of run_optimizer function'''


# In[52]:

if __name__ == "__main__": ## COMMENT_OUT_FOR_JUPYTER
    num_requests = [100, 500]
    if SLATE_ON:
        app.logger.info(f"{log_prefix} SLATE_ON")
        if REAL_DATA == False:
            raw_traces=None
            trace_file=None
            app.logger.info(f"{log_prefix} No REAL DATA")
        elif USE_TRACE_FILE:
            TRACE_FILE_PATH="wrk_prof_log2_west.txt"
            raw_traces=None
            trace_file=TRACE_FILE_PATH
        elif USE_PRERECORDED_TRACE: ## envoycon demo
            TRACE_PATH="sampled_both_trace.txt"
            df = pd.read_csv(TRACE_PATH)
            raw_traces = sp.df_to_trace(df)
            trace_file=None
        else:
            app.logger.error(f"{log_prefix} SLATE_ON, but no trace file")
            assert False
    else:
        app.logger.info(f"{log_prefix} SLATE_OFF")
        raw_traces=None
        trace_file=None
        
    percentage_df, desc = run_optimizer(raw_traces, trace_file, NUM_REQUESTS=num_requests) ## COMMENT_OUT_FOR_JUPYTER
    # print("percentage_df")
    # display(percentage_df)
    ccr = count_cross_cluster_routing(percentage_df)
    print(f"** cross_cluster_routing: {ccr}")
    if GRAPHVIZ and percentage_df.empty == False:
        plot_request_flow(percentage_df)
# %%
