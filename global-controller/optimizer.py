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
import argparse
from pprint import pprint
from IPython.display import display
from global_controller import app
import time_stitching as tst
from config import *
import zlib


random.seed(1234)

timestamp_list = list()
temp_timestamp_list = list()
def LOG_TIMESTAMP(event_name):
    timestamp_list.append([event_name, time.time()])
    if len(timestamp_list) > 1:
        dur = round(timestamp_list[-1][1] - timestamp_list[-2][1], 5)
        app.logger.info(f"{log_prefix} Finished, {event_name}, duration,{dur}")


def TEMP_LOG_TIMESTAMP(event_name):
    temp_timestamp_list.append([event_name, time.time()])
    if len(temp_timestamp_list) > 1:
        dur = round(timestamp_list[-1][1] - timestamp_list[-2][1], 5)
        app.logger.info(f"{log_prefix} Finished, {event_name}, duration,{dur}")
        
        
def prettyprint_timestamp():
    app.logger.info(f"{log_prefix}")
    app.logger.info(f"{log_prefix} *")
    app.logger.info(f"{log_prefix} ** timestamp_list(ms)")
    for i in range(1, len(timestamp_list)):
        app.logger.info(f"{log_prefix} {timestamp_list[i][0]}", end=",")


## Deprecated
# def print_log(msg, obj=None):
#     if VERBOSITY >= 1:
#         if obj == None:
#             print("[LOG] ", end="")
#             print(msg)
#         else:
#             print("[LOG] ", end="")
#             print(msg, obj)
    
        
def print_error(msg):
    exit_time = 5
    print("[ERROR] " + msg)
    print("EXIT PROGRAM in")
    for i in reversed(range(exit_time)) :
        print("{} seconds...".format(i))
        time.sleep(1)
    exit()
    

'''
For interactive run with jupyternotebook, comment out following lines "COMMENT OUT FOR JUPYTER".
And adjust the indentation accordingly.
'''

## In[31]:
raw_traces = None
NUM_REQUESTS=[100,1000]

''' start of run_optimizer function '''
def run_optimizer(raw_traces=None, NUM_REQUESTS=[100,1000]): ## COMMENT_OUT_FOR_JUPYTER
    if raw_traces == None:
        ## Parse trace file
        # LOG_PATH = "./modified_trace_and_load_log.txt" # outdated
        # traces = tst.parse_file(LOG_PATH)
        # LOG_PATH = "./trace-west_only-load_per_ontick.csv" # Per-OnTick load logging
        LOG_PATH = "./trace-west_only-load_per_req.csv" # Per-request load logging
        traces = tst.parse_trace_file_ver2(LOG_PATH)
        traces, callgraph, depth_dict, trace_df = tst.stitch_time(traces)
        display(trace_df)
        NUM_CLUSTER = len(traces)
    else:
        assert type(raw_traces) == type(dict())
        assert type(NUM_REQUESTS) == type(list())
        if len(raw_traces) == 0:
            app.logger.info(f"{log_prefix} Trace is empty. returns None... Do local routing.")
            return None ## COMMENT_OUT_FOR_JUPYTER
        assert len(raw_traces) == len(NUM_REQUESTS)
        if len(raw_traces) == 1 or len(NUM_REQUESTS) == 1:
            app.logger.info(f"{log_prefix} the number of cluster is ONE. returns None... Do local routing.")
            return None ## COMMENT_OUT_FOR_JUPYTER
        LOG_TIMESTAMP("optimizer start")
        NUM_CLUSTER = len(raw_traces)
        TOTAL_NUM_REQUEST = sum(NUM_REQUESTS)
        app.logger.info(f"{log_prefix} NUMBER OF CLUSTERS: {NUM_CLUSTER}")
        for cid, trace in raw_traces.items():
            if len(raw_traces[cid]) == 0:
                app.logger.info(f"{log_prefix} trace for cluster {cid} is empty.")
        #################################################################
        traces, callgraph, depth_dict = tst.stitch_time(raw_traces)
        #################################################################
        for cid in traces:
            if len(traces[cid]) == 0:
                app.logger.info(f"{log_prefix} Cluster {cid} trace is empty. It is impossible to predict latency function. returns None... Do local routing.")
                return None ## COMMENT_OUT_FOR_JUPYTER
        
    if ENTRANCE == INGRESS_GW_NAME:
        callgraph[INGRESS_GW_NAME] = list()
        for parent_svc, children in callgraph.items():
            if parent_svc == tst.FRONTEND_svc:
                callgraph[INGRESS_GW_NAME].append(parent_svc)
        for parent_svc, child_svc_list in callgraph.items():
            app.logger.debug(f"{log_prefix} {parent_svc}: {child_svc_list}")
    app.logger.info(f"{log_prefix} callgraph")
    app.logger.info(f"{log_prefix} {callgraph}")
    unique_services = list(callgraph.keys())
    app.logger.info(f"{log_prefix} unique_services: {unique_services}")


    ## In[33]:

    def span_to_compute_arc_var_name(svc_name, cid):
        return (svc_name+DELIMITER+str(cid)+DELIMITER+"start", svc_name+DELIMITER+str(cid)+DELIMITER+"end") # return type: tuple

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


    ## In[34]:

    svc_name_list = list()
    compute_arc_var_name = dict()
    per_service_compute_arc = dict()
    for svc_name in unique_services:
        for cid in range(NUM_CLUSTER):
            var_name = span_to_compute_arc_var_name(svc_name, cid)
            compute_arc_var_name[var_name] = list()
            if svc_name not in per_service_compute_arc:
                per_service_compute_arc[svc_name] = list()
            per_service_compute_arc[svc_name].append(var_name)
        
    LOG_TIMESTAMP("defining compute_arc_var_name")
    if DISPLAY:
        display(compute_arc_var_name)


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
        app.logger.info(f"{log_prefix} {tuple_var_name}")

    if ENTRANCE == tst.FRONTEND_svc:
        if tst.REVIEW_V1_svc in unique_services:
            assert len(network_arc_var_name) == 14 # bookinfo, without ingress gw, two cluster set up
        else:
            assert len(network_arc_var_name) == 18 # bookinfo, without ingress gw, two cluster set up
    elif ENTRANCE == INGRESS_GW_NAME:
        if tst.REVIEW_V1_svc in unique_services:
            assert len(network_arc_var_name) == 18 # bookinfo, with ingress gw, two cluster set up
        elif PRODUCTPAGE_ONLY:
            assert len(network_arc_var_name) == 8
        else:
            assert len(network_arc_var_name) == 22 # bookinfo, with ingress gw, two cluster set up
    else:
        assert False


    def check_network_arc_var_name(net_arc_var_n):
        for (src, dst), _ in net_arc_var_n.items():
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
            
    check_network_arc_var_name(network_arc_var_name)
    if DISPLAY:
        display(network_arc_var_name)
        
    ## In[37]:

    load = list()
    comp_t = list()
    service_name_ = list()
    index_ = list()
    cid_list = list()
    ############################
    ## NOTE: Cluster id is arbitrary for now 
    ############################
    if REAL_DATA:
        if SAME_COMPUTE_TIME:
            for cid in traces:
                for tid, spans in traces[cid].items():
                    for svc_name, span in spans.items():
                        for cid in range(NUM_CLUSTER):
                            load.append(span.load)
                            comp_t.append(span.xt)
                            index_.append(span_to_compute_arc_var_name(span.svc_name, cid))
                            service_name_.append(span.svc_name)
                            cid_list.append(cid)
                            ## Adding fake ingress gw latency/load data, same as frontend service
                            if ENTRANCE == INGRESS_GW_NAME:
                                if span.svc_name == tst.FRONTEND_svc:
                                    ###############################################
                                    load.append(span.load)
                                    comp_t.append(0)
                                    ###############################################
                                    index_.append(span_to_compute_arc_var_name(ENTRANCE, cid))
                                    service_name_.append(ENTRANCE)
                                    cid_list.append(cid)
        else:
            for cid in traces:
                for tid, spans in traces[cid].items():
                    for svc_name, span in spans.items():
                        load.append(span.load)
                        # comp_t.append(span.xt)
                        comp_t.append(span.ct)
                        index_.append(span_to_compute_arc_var_name(span.svc_name, span.cluster_id))
                        service_name_.append(span.svc_name)
                        cid_list.append(span.cluster_id)
                        if ENTRANCE == INGRESS_GW_NAME:
                            if span.svc_name == tst.FRONTEND_svc:
                                load.append(span.load)
                                comp_t.append(0)
                                index_.append(span_to_compute_arc_var_name(ENTRANCE, span.cluster_id))
                                service_name_.append(ENTRANCE)
                                cid_list.append(span.cluster_id)
    else:
        num_data_point = 100
        for cid in range(NUM_CLUSTER):
            for svc_name in unique_services:
                ld = list()
                comptime = list()
                load += list(np.arange(0,num_data_point))
                for j in range(num_data_point):
                    if svc_name == INGRESS_GW_NAME:
                        slope = 0
                        intercept = 0
                    else:
                        if SAME_COMPUTE_TIME:
                            slope = 1
                            intercept = 10
                        else:
                            # slope = hash(svc_name)%5 # bug... hash function is NOT deterministic
                            slope = zlib.adler32(svc_name.encode('utf-8'))%5+1
                            intercept = 10
                    ct = pow(load[j],REGRESSOR_DEGREE)*slope + intercept
                    comptime.append(ct)
                    ld.append(load[j])
                    comp_t.append(ct)
                    cid_list.append(cid)
                    service_name_.append(svc_name)
                    index_.append(span_to_compute_arc_var_name(svc_name, cid))
                # print(f"service,{svc_name}, load,{ld}, compute time,{comptime}, degree({REGRESSOR_DEGREE}), slope({slope}), intercept({intercept})")
                print(f"service,{svc_name}, degree({REGRESSOR_DEGREE}), slope({slope}), intercept({intercept})")
            print()

    compute_time_observation = pd.DataFrame(
        data={
            "service_name": service_name_,
            "load": load, 
            "compute_time": comp_t,
            "cluster_id": cid_list,
        },
        index=index_
    )
    if DISPLAY:
        print("compute_time_observation")
        # with pd.option_context('display.max_rows', None):
        # print(compute_time_observation[(compute_time_observation["service_name"]=="details-v1") & (compute_time_observation["cluster_id"]==0)])
        # print(compute_time_observation[(compute_time_observation["service_name"]=="details-v1") & (compute_time_observation["cluster_id"]==1)])
        
        # with pd.option_context('display.max_rows', None):
        display(compute_time_observation)


    # In[38]:


    ## Per-service load-to-compute time modeling.
    idx = 0
    num_subplot_row = 2
    num_subplot_col = 5
    fig, (plot_list) = plt.subplots(num_subplot_row, num_subplot_col, figsize=(16,6))
    fig.tight_layout()

    max_compute_time = dict()
    # max_load = dict()
    # max_compute_time = dict()
    regressor_dict = dict()
    for cid in range(NUM_CLUSTER):
        cid_df =  compute_time_observation[compute_time_observation["cluster_id"]==cid]
        for svc_name in unique_services:
            temp_df = cid_df[cid_df["service_name"] == svc_name]
            frontend_temp_df = cid_df[cid_df["service_name"] == tst.FRONTEND_svc]
            if ALL_PRODUCTPAGE:
                X = frontend_temp_df[["load"]]
                y = frontend_temp_df["compute_time"]
                X.index = temp_df.index
                y.index = temp_df.index
            else:
                X = temp_df[["load"]]
                y = temp_df["compute_time"]
            display(X)
            temp_x = X.copy()
            # for i in range(len(temp_x)):
            print("max(temp_x)")
            print(max(temp_x["load"]))
            for i in range(max(temp_x["load"])):
                temp_x.iloc[i, 0] = i
            print("len(temp_x)")
            print(len(temp_x))
            print("temp_x")
            print(temp_x)
            #############################################
            # if ENTRANCE == INGRESS_GW_NAME and svc_name == ENTRANCE:
            #     max_compute_time[svc_name] = 0
            # else:
            #     max_compute_time[svc_name] = 1000000
            #############################################
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, train_size=0.9, random_state=1
            )
            feat_transform = make_column_transformer(
                (StandardScaler(), ["load"]),
                # ("passthrough", ["load"]),
                verbose_feature_names_out=False,
                remainder='drop'
            )
            if REGRESSOR_DEGREE == 1:
                regressor_dict[svc_name] = make_pipeline(feat_transform, LinearRegression())
                regressor_dict[svc_name].fit(X_train, y_train)
            elif REGRESSOR_DEGREE > 1:
                poly = PolynomialFeatures(degree=REGRESSOR_DEGREE, include_bias=True)
                regressor_dict[svc_name] = make_pipeline(feat_transform, poly, LinearRegression())
                regressor_dict[svc_name].fit(X_train, y_train)
                
            ## Run prediction and compare it with the ground truth to see how accurate the trained model is
            y_pred = regressor_dict[svc_name].predict(X_test)
            c_ = regressor_dict[svc_name]["linearregression"].intercept_,
            in_ = regressor_dict[svc_name]["linearregression"].coef_
            r2 =  np.round(r2_score(y_test, y_pred),2)
            app.logger.info(f"{log_prefix} Service {svc_name}, model slope: {c_}, intercept: {in_}, R^2: {r2}")

            ## Plot
            row_idx = int(idx/num_subplot_col)
            col_idx = idx%num_subplot_col
            # print(row_idx, col_idx)
            # plot_list[row_idx][col_idx].plot(X["load"], y, 'ro', label="observation", alpha=0.1)
            # plot_list[row_idx][col_idx].plot(X["load"], regressor_dict[svc_name].predict(X), 'b.', label="prediction", alpha=0.1)
            plot_list[row_idx][col_idx].plot(X, y, 'ro', label="observation", alpha=0.1)
            # plot_list[row_idx][col_idx].plot(X, regressor_dict[svc_name].predict(X), 'b.', label="prediction", alpha=0.1)
            plot_list[row_idx][col_idx].plot(temp_x, regressor_dict[svc_name].predict(temp_x), 'bo', label="prediction", alpha=0.1)
            plot_list[row_idx][col_idx].legend()
            plot_list[row_idx][col_idx].set_title(svc_name)
            if row_idx == num_subplot_row-1:
                plot_list[row_idx][col_idx].set_xlabel("load")
            if col_idx == 0:
                plot_list[row_idx][col_idx].set_ylabel("Compute time")
            idx += 1
        
        
    LOG_TIMESTAMP("train regression model")


    # ### Define network egress cost

    # In[39]:


    network_arc_var_name_list = list(network_arc_var_name.keys())
    network_arc_var_name_list
    network_arc_var_name


    # In[40]:


    list(network_arc_var_name.keys())


    # In[41]:


    min_load = 0
    max_load = sum(NUM_REQUESTS)
    print("max_load = sum(NUM_REQUESTS): ", max_load)

    min_network_egress_cost = list()
    max_network_egress_cost = list()

    network_arc_var_name_list = list(network_arc_var_name.keys())
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


    # ### Define compute cost

    # In[42]:


    min_compute_egress_cost = list()
    max_compute_egress_cost = list()
    compute_arc_var_name_list = list(compute_arc_var_name.keys())
    for src_repl, dst_repl in compute_arc_var_name_list:
        # compute edge does not involve any networking
        min_compute_egress_cost.append(0)
        max_compute_egress_cost.append(0)
                    
    compute_egress_cost_data = dict()
    for svc_name in unique_services:
        compute_egress_cost_data[svc_name] = pd.DataFrame(
            data={
                "min_compute_egress_cost": [0] * len(per_service_compute_arc[svc_name]),
                "max_compute_egress_cost": [0] * len(per_service_compute_arc[svc_name]),
                # "min_load":[min_load] * len(per_service_compute_arc[svc_name]),
                # "max_load":[max_load] * len(per_service_compute_arc[svc_name]),
            },
            index=per_service_compute_arc[svc_name]
        )

    compute_time_data = dict()
    for svc_name in unique_services:
        compute_time_data[svc_name] = pd.DataFrame(
            data={
                "min_load":[min_load] * len(per_service_compute_arc[svc_name]),
                "max_load":[max_load] * len(per_service_compute_arc[svc_name]),
                "min_compute_time": [0] * len(per_service_compute_arc[svc_name]),
                # "max_compute_time": [max_compute_time[svc_name]] * len(per_service_compute_arc[svc_name]),
            },
            index=per_service_compute_arc[svc_name]
        )
    app.logger.info(f"{log_prefix} max_load: \n{max_load}\n")

    # ### Define network latency

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
                app.logger.info(f"{log_prefix} intra-cluster, {src_node}, {dst_node}")
                min_network_latency.append(intra_cluster_network_rtt)
                max_network_latency.append(intra_cluster_network_rtt)
            # Network latency for remote routing
            else:
                app.logger.info(f"{log_prefix} inter-cluster, {src_node}, {dst_node}")
                min_network_latency.append(inter_cluster_network_rtt)
                max_network_latency.append(inter_cluster_network_rtt)

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
    app.logger.debug(f"{log_prefix} network_latency_data")
    app.logger.debug(f"{log_prefix} {network_latency_data}\n")


    # In[44]:


    ## Optimizer runtime timestamp, start time
    optimizer_start_time = time.time()
    model = gp.Model('RequestRouting')
    # Add variables for the regression
    compute_time = dict()
    compute_load = dict()
    for svc_name in unique_services:
        app.logger.info(f"{log_prefix} {svc_name}")
        # compute_time[svc_name] = gppd.add_vars(model, compute_time_data[svc_name], name="compute_time", lb="min_compute_time", ub="max_compute_time")
        compute_time[svc_name] = gppd.add_vars(model, compute_time_data[svc_name], name="compute_time", lb="min_compute_time")
        compute_load[svc_name] = gppd.add_vars(model, compute_time_data[svc_name], name="load_for_compute_edge", lb="min_load", ub="max_load")
        # compute_time[svc_name] = gppd.add_vars(model, compute_time_data[svc_name], name="compute_time")
        # compute_load[svc_name] = gppd.add_vars(model, compute_time_data[svc_name], name="load_for_compute_edge")
    model.update()

    m_feats = dict()
    idx = 0
    for svc_name in unique_services:
        m_feats[svc_name] = pd.DataFrame(
            data={
                "load": compute_load[svc_name],
            },
            index=per_service_compute_arc[svc_name]
        )
        pred_constr = add_predictor_constr(model, regressor_dict[svc_name], m_feats[svc_name], compute_time[svc_name])
        if idx == 0:
            pred_constr.print_stats()
        idx += 1
    model.update()

    network_latency = gppd.add_vars(model, network_latency_data, name="network_latency", lb="min_network_latency", ub="max_network_latency")

    network_load = gppd.add_vars(model, network_latency_data, name="load_for_network_edge", lb="min_load", ub="max_load")
    # network_load = gppd.add_vars(model, network_latency_data, name="load_for_network_edge")

    model.update()

    network_egress_cost = gppd.add_vars(model, network_egress_cost_data, name="network_egress_cost", lb="min_network_egress_cost", ub="max_network_egress_cost")

    compute_egress_cost = dict()
    for svc_name in unique_services:
        compute_egress_cost[svc_name] = gppd.add_vars(model, compute_egress_cost_data[svc_name], name="compute_egress_cost", lb="min_compute_egress_cost", ub="max_compute_egress_cost")
    model.update()

    # egress cost sum
    network_egress_cost_sum = sum(network_egress_cost.multiply(network_load))
    compute_egress_cost_sum = 0
    for svc_name in unique_services:
        compute_egress_cost_sum += sum(compute_egress_cost[svc_name].multiply(compute_load[svc_name]))
    total_egress_sum = network_egress_cost_sum + compute_egress_cost_sum
    app.logger.debug(f"{log_prefix} total_egress_sum:")
    app.logger.debug(f"{log_prefix} {total_egress_sum}\n")

    # total latency sum
    network_latency_sum = sum(network_latency.multiply(network_load))

    compute_latency_sum = 0
    for svc_name in unique_services:
        compute_latency_sum += sum(compute_time[svc_name].multiply(m_feats[svc_name]["load"])) # m_feats[svc_name]["load"] is identical to compute_load[svc_name]
        # print("compute_latency_sum, ", svc_name)
        # display(compute_latency_sum)
    total_latency_sum = network_latency_sum + compute_latency_sum

    app.logger.debug(f"{log_prefix} compute_latency_sum:")
    app.logger.debug(f"{log_prefix} {compute_latency_sum}\n")

    app.logger.debug(f"{log_prefix} network_latency_sum:")
    app.logger.debug(f"{log_prefix} {network_latency_sum}\n")

    app.logger.debug(f"{log_prefix} total_latency_sum:")
    app.logger.debug(f"{log_prefix} {total_latency_sum}\n")

    objective = "multi-objective" # latency or egress_cost or multi-objective
    if objective == "latency":
        model.setObjective(total_latency_sum, gp.GRB.MINIMIZE)
    elif objective == "egress_cost":
        model.setObjective(total_egress_sum, gp.GRB.MINIMIZE)
    elif objective == "multi-objective":
        # NOTE: higher dollar per millisecond, more important the latency
        # dollar_per_millisecond = 0.00001
        dollar_per_millisecond = 1
        # model.setObjective((dollar_per_millisecond*total_latency_sum) + total_egress_sum, gp.GRB.MINIMIZE)
        model.setObjective(total_latency_sum + (total_egress_sum/dollar_per_millisecond), gp.GRB.MINIMIZE)
    else:
        print_error("unsupported objective, ", objective)
        
    # model.update()
    app.logger.info(f"{log_prefix} model objective: {model.getObjective()}")

    # arcs is the keys
    # aggregated_load is dictionary
    concat_compute_load = pd.Series()
    for svc_name, c_load in compute_load.items():
        concat_compute_load = pd.concat([concat_compute_load, compute_load[svc_name]], axis=0)
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


    aggregated_load


    # In[46]:


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
    #########################################################
    # option 1
    #with gp.Env(params=options) as env, gp.Model(env=env) as model:
    #    # Formulate problem
    #    model.optimize()

    # option 2 # it requires gurobi.lic file
    # Where should we store the gurobi.lic file?
    # - https://support.gurobi.com/hc/en-us/articles/360013417211
    # How can we use gurobi WLS license?
    # - https://support.gurobi.com/hc/en-us/articles/13232844297489-How-do-I-set-up-a-Web-License-Service-WLS-client-license-

    options = {
        "WLSACCESSID": "550eb070-b4aa-491d-b81e-38edc474fa10",
        "WLSSECRET": "aea5168e-aa53-44e6-a8f0-8676d3ecc701",
        "LICENSEID": 2415150,
    }
    env = gp.Env(params=options)
    gp.Model(env=env)
    model.optimize()

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
    LOG_TIMESTAMP("get var and constraint")

    app.logger.info(f"{log_prefix} model.Status: {model.Status}")

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
    else:
        app.logger.info(f"{log_prefix} ooooooooooooooooooooooo")
        app.logger.info(f"{log_prefix} oooo MODEL SOLVED! oooo")
        app.logger.info(f"{log_prefix} ooooooooooooooooooooooo")
        print()
        
        ## Model solved!
        ## Print out the result
        optimize_end_time = time.time()
        optimizer_runtime = round((optimize_end_time - optimizer_start_time) - substract_time, 5)
        solve_runtime = round(solve_end_time - solve_start_time, 5)
        # constraint_setup_time = round(constraint_setup_end_time - constraint_setup_start_time, 5)
        app.logger.info(f"{log_prefix} *"*50)
        app.logger.info(f"{log_prefix} ** Objective: {objective}")
        app.logger.info(f"{log_prefix} ** Num constraints: {num_constr}")
        app.logger.info(f"{log_prefix} ** Num variables: {num_var}")
        app.logger.info(f"{log_prefix} ** Optimization runtime: {optimizer_runtime} ms")
        app.logger.info(f"{log_prefix} ** model.optimize() runtime: {solve_runtime} ms")
        # app.logger.info(f"{log_prefix} ** constraint_setup_time runtime: {} ms".format(constraint_setup_time))
        app.logger.info(f"{log_prefix} ** model.objVal: {model.objVal}")
        app.logger.info(f"{log_prefix} ** model.objVal / total num requests: {model.objVal/TOTAL_NUM_REQUEST}")
        
        app_name = "bookinfo"
        request_flow = pd.DataFrame(columns=["From", "To", "Flow"])
        for arc in arcs:
            if aggregated_load[arc].x > 1e-6:
                temp = pd.DataFrame({"From": [arc[0]], "To": [arc[1]], "Flow": [aggregated_load[arc].x]})
                request_flow = pd.concat([request_flow, temp], ignore_index=True)
        if DISPLAY:
            display(request_flow)
        if OUTPUT_WRITE:
            now = datetime.datetime.now()
            request_flow.to_csv(OUTPUT_DIR + now.strftime("%Y%m%d_%H:%M:%S") + "-"+app_name+"-model_solution.csv")
            LOG_TIMESTAMP("file write model output")
            
        ## Performance log write
        ## old
        # app.logger.debug(f"{log_prefix} @@, App, num_constr, num_gurobi_var, compute_arc_var_name_list, network_arc_var_name_list, NUM_CLUSTER, depth, total_num_svc, fan_out_degree, no_child_constant, REGRESSOR_DEGREE,  optimizer_runtime, solve_runtime")
        
        ## new
        # app.logger.debug(f"{log_prefix} @@, app_name, num_constr, num_gurobi_var, compute_arc_var_name_list, network_arc_var_name_list, NUM_CLUSTER, total_num_svc, REGRESSOR_DEGREE, optimizer_runtime, solve_runtime")
        
        app.logger.debug(f"{log_prefix} @@, ",end="")
        print(app_name + "," +str(num_constr) + "," +str(num_var) + "," +str(len(compute_arc_var_name_list)) + "," +str(len(network_arc_var_name_list)) + "," +str(NUM_CLUSTER) + "," +str(len(unique_services)) + "," +str(REGRESSOR_DEGREE) + "," +str(optimizer_runtime) + "," +str(solve_runtime) + ",",end="")
                # str(fan_out_degree) + "," + \
                # str(no_child_constant) + "," + \
                # str(depth) + "," + \
                # total_num_svc_in_each_depth, \
                # constraint_setup_time, \
                # NUM_REQUEST, \
        # prettyprint_timestamp()

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
                    print(src_svc)
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
            weight_list = list()
            for index, row in percentage_df.iterrows():
                weight_list.append(row['flow']/row['total'])
            percentage_df["weight"] = weight_list
            return percentage_df
            
        percentage_df = translate_to_percentage(request_flow)
        if DISPLAY:
            display(percentage_df)
        # return percentage_df
    
''' This is end of run_optimizer function'''


# In[52]:

if GRAPHVIZ and model.Status == GRB.OPTIMAL:
    g_ = graphviz.Digraph()
    # The node() method takes a name identifier as first argument and an optional label.
    # The edge() method takes the names of start node and end node
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
    total_num_remote_routing = 0
    for index, row in percentage_df.iterrows():
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
        
        g_.edge(src_node_name, dst_node_name, label=str(row["flow"]) + ", ("+str(int(row["weight"])*100)+"%)", penwidth=edge_pw, style="filled", fontsize=edge_fs_0, fontcolor=edge_color, color=edge_color, arrowsize=edge_arrowsize, minlen=edge_minlen)
            
        if src_cid != dst_cid:
            total_num_remote_routing += row["flow"]
            
    app.logger.info(f"{log_prefix} ** total_num_remote_routing: ", total_num_remote_routing)
    app.logger.info(f"{log_prefix} *"*50)   
    now =datetime .datetime.now()
    g_.render(OUTPUT_DIR + now.strftime("%Y%m%d_%H:%M:%S") + "_" + app_name+ '_call_graph', view = True) # output: call_graph.pdf
    g_
        
if __name__ == "__main__": ## COMMENT_OUT_FOR_JUPYTER
    run_optimizer(raw_traces=None, NUM_REQUESTS=[100,1000]) ## COMMENT_OUT_FOR_JUPYTER
# %%
