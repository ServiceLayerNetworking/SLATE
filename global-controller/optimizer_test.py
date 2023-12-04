#!/usr/bin/env python
# coding: utf-8

# In[31]:
import sys
sys.dont_write_bytecode = True

import time
import numpy as np  
import pandas as pd
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
from IPython.display import display
from global_controller import app
import time_stitching as tst
import config as cfg
import span as sp
import optimizer_header as opt_func
import os
from IPython.display import display

random.seed(1234)

'''
For interactive run with jupyternotebook, comment out following lines "COMMENT_OUT_FOR_JUPYTER".
And adjust the indentation accordingly.
'''


# In[31]:

if not os.path.exists(cfg.OUTPUT_DIR):
    os.mkdir(cfg.OUTPUT_DIR)
    print(f"{cfg.log_prefix} mkdir {cfg.OUTPUT_DIR}")
# else:
#     print(f"{cfg.log_prefix} {cfg.OUTPUT_DIR} already exists")
#     print("If you are using jupyter notebook, you should restart the kernel to load the new config.py")
#     assert False
    
    
# In[31]:

# cluster
NUM_REQUESTS = list()
a = 3
if a == 1:
    NUM_REQUESTS.append({"A": 100, "B": 0})
    NUM_REQUESTS.append({"A": 5, "B": 0})
elif a == 2:
    NUM_REQUESTS.append({"A": 0, "B": 5})
    NUM_REQUESTS.append({"A": 0, "B": 100})
elif a == 3:
    NUM_REQUESTS.append({"A": 10, "B": 30})
    NUM_REQUESTS.append({"A": 20, "B": 40})
elif a == 4:
    NUM_REQUESTS.append({"A": 30, "B": 10})
    NUM_REQUESTS.append({"A": 40, "B": 20})
else:
    print("Invalid a value: ", a)
    assert False
# NUM_REQUESTS.append({"A": 10, "B": 20})
# NUM_REQUESTS.append({"A": 30, "B": 40})
NUM_CLUSTER = len(NUM_REQUESTS)
MAX_LOAD = dict()
for cid in range(NUM_CLUSTER):
    for request_type in NUM_REQUESTS[cid]:
        if request_type not in MAX_LOAD:
            MAX_LOAD[request_type] = 0
        MAX_LOAD[request_type] += NUM_REQUESTS[cid][request_type]
unique_service = dict()
callgraph = dict()
unique_service[0] = {'ingress_gw', 'productpage-v1', 'reviews-v3', 'details-v1'}
unique_service[1] = {'ingress_gw', 'productpage-v1', 'reviews-v3', 'details-v1'}
callgraph["A"] = {'ingress_gw': ['productpage-v1'], 'productpage-v1': ['reviews-v3'], 'reviews-v3':[]}
callgraph["B"] = {'ingress_gw': ['productpage-v1'], 'productpage-v1': ['details-v1'], 'details-v1':[]}
# unique_service[0] = {'ingress_gw', 'productpage-v1'}
# unique_service[1] = {'ingress_gw', 'productpage-v1'}
# callgraph["A"] = {'ingress_gw': ['productpage-v1'], 'productpage-v1': []}
# callgraph["B"] = {'ingress_gw': ['productpage-v1'], 'productpage-v1': []}
assert len(unique_service) == NUM_CLUSTER
all_unique_service = set()
for cid in range(NUM_CLUSTER):
    all_unique_service = all_unique_service.union(unique_service[cid])

## Different call graph.
## NOTE: It is decoupled from the deployment of each service in each cluster
depth_dict = dict()
for key in callgraph:
    depth_dict = opt_func.graph_depth(callgraph[key], depth_dict)
per_svc_max_load = opt_func.calc_max_load_of_each_callgraph(callgraph, MAX_LOAD)
callsize_dict = dict()
for key in callgraph:
    for parent_svc, children in callgraph[key].items():
        for child_svc in children:
            assert depth_dict[parent_svc] > depth_dict[child_svc]
            callsize_dict[(parent_svc,child_svc)] = (depth_dict[parent_svc]+1)


# In[31]:


''' START of run_optimizer function '''
compute_arc_var_name = opt_func.create_compute_arc_var_name(unique_service)
opt_func.check_compute_arc_var_name(compute_arc_var_name)
opt_func.log_timestamp("defining compute_arc_var_name")
if cfg.DISPLAY: display(compute_arc_var_name)
columns=["svc_name", "src_cid", "dst_cid", "call_size"]
for key in callgraph:
    columns.append("max_load_"+key)
for key in callgraph:
    columns.append("min_load_"+key)
for key in callgraph:
    columns.append("observed_x_"+key)
for key in callgraph:
    columns.append("observed_y_"+key)
for key in callgraph:
    columns.append("latency_function_"+key)
for key in callgraph:
    columns.append("min_compute_time_"+key)
compute_df = pd.DataFrame(
    columns=columns,
    data={
    },
    index=compute_arc_var_name
)
if cfg.DISPLAY: display(compute_df)


# In[31]:


svc_list = list()
src_cid_list = list()
dst_cid_list = list()
for var_name in compute_arc_var_name:
    if type(var_name) == tuple:
        svc_list.append(var_name[0].split(cfg.DELIMITER)[0])
        src_cid_list.append(int(var_name[0].split(cfg.DELIMITER)[1]))
        dst_cid_list.append(int(var_name[1].split(cfg.DELIMITER)[1]))
    else:
        svc_list.append(var_name.split(",")[0].split(cfg.DELIMITER)[0])
        src_cid_list.append(int(var_name.split(",")[0].split(cfg.DELIMITER)[1]))
        dst_cid_list.append(int(var_name.split(",")[1].split(cfg.DELIMITER)[1]))
compute_df["svc_name"] = svc_list
compute_df["src_cid"] = src_cid_list
compute_df["dst_cid"] = dst_cid_list
for index, row in compute_df.iterrows():
    for key in callgraph:
        compute_df.at[index, 'max_load_'+key] = per_svc_max_load[row["svc_name"]][key]
        compute_df.at[index, 'min_load_'+key] = 0
        compute_df.at[index, "min_compute_time_"+key] = 0
compute_df["call_size"] = 0
if cfg.DISPLAY: display(compute_df)
if cfg.DISPLAY: print(callgraph)
optimizer_start_time = time.time()
gurobi_model = gp.Model('RequestRouting')


# In[35]:


load_list = opt_func.fake_load_gen(callgraph)
for index, row in compute_df.iterrows():
    for key in callgraph:
        load_of_certain_cg = [ld[key] for ld in load_list]
        compute_df.at[index, "observed_x_"+key] = load_of_certain_cg
        
observed_y = dict()
# Generate fake training data and ground truth
for index, row in compute_df.iterrows():
    if row["svc_name"] not in observed_y:
        observed_y[row["svc_name"]] = dict()
    for target_cg in callgraph:
        # if target_cg not in observed_y[row["svc_name"]]:
        observed_y[row["svc_name"]][target_cg] = list()
        for load_dict in load_list:
            # load_dict = {'A':load_of_callgraph_A, 'B':load_of_callgraph_B}
            # compute_latency is ground truth
            slope = opt_func.get_slope(row['svc_name'], target_cg)
            intercept = 0
            compute_latency = opt_func.gen_compute_latency(load_dict, row["svc_name"], slope, intercept, target_cg, callgraph)
            observed_y[row["svc_name"]][target_cg].append(compute_latency)
        print(row['svc_name'], target_cg, len(observed_y[row["svc_name"]][target_cg]))
            

# Compute latency prediction using regression model for each load point  
for index, row in compute_df.iterrows():
    for target_cg in callgraph:
        compute_df.at[index, "observed_y_"+target_cg] = np.array(observed_y[row["svc_name"]][target_cg])

display(compute_df)

for index, row in compute_df.iterrows():
    print(len(compute_df.at[index, "observed_x_A"]))
    print(len(compute_df.at[index, "observed_x_B"]))
    print(len(compute_df.at[index, "observed_y_A"]))
    print(len(compute_df.at[index, "observed_y_B"]))
    break


# In[38]:


def get_regression_pipeline():
    numeric_features = list()
    for key in callgraph:
        numeric_features.append("observed_x_"+key)
    feat_transform = make_column_transformer(
        (StandardScaler(), numeric_features),
        verbose_feature_names_out=False,
        remainder='drop'
    )
    if cfg.REGRESSOR_DEGREE == 1:
        reg = make_pipeline(feat_transform, LinearRegression())
    elif cfg.REGRESSOR_DEGREE > 1:
        poly = PolynomialFeatures(degree=cfg.REGRESSOR_DEGREE, include_bias=True)
        reg = make_pipeline(feat_transform, poly, LinearRegression())
    return reg

def get_observed_x_df():
    data = dict()
    for key in callgraph:
        data["observed_x_"+key] = row["observed_x_"+key]
    temp_df = pd.DataFrame(
        data=data,
    )
    # X_ = temp_df[["observed_x_A", "observed_x_B"]]
    # display(temp_df)
    # display(X_)
    return temp_df

    
for index, row in compute_df.iterrows():
    for key in callgraph:
        reg = get_regression_pipeline()
        X_ = get_observed_x_df()
        y_ = row["observed_y_"+key]
        X_train, X_test, y_train, y_test = train_test_split(X_, y_, train_size=0.9, random_state=1)
        reg.fit(X_train, y_train)
        if row["svc_name"] != tst.FRONTEND_svc:
            if cfg.REGRESSOR_DEGREE == 1:
                for i in range(len(reg["linearregression"].coef_)):
                    if reg["linearregression"].coef_[i] < 0:
                        new_c = np.array([0.])
                        reg["linearregression"].coef_[i] = new_c
                        print(f'{cfg.log_prefix} Service {row["svc_name"]}, changed slope {reg["linearregression"].coef_[i]} --> {new_c}, intercept: {in_}')
                        assert False
            if cfg.REGRESSOR_DEGREE == 2:
                for i in range(len(reg["linearregression"].coef_)):
                    if reg["linearregression"].coef_[i][1] < 0:
                        new_c = np.array([0., 0.])
                        reg["linearregression"].coef_[i] = new_c
                        print(f'{cfg.log_prefix} Service {row["svc_name"]}, changed slope {reg["linearregression"].coef_[i]} --> {new_c}, intercept: {in_}')
                        assert False
        c_ = reg["linearregression"].coef_
        in_ = reg["linearregression"].intercept_
        y_pred = reg.predict(X_test)
        r2 =  np.round(r2_score(y_test, y_pred),2)
        print(f'Service {row["svc_name"]}, r2: {r2}, slope: {c_}, intercept: {in_}')
        compute_df.at[index, 'latency_function_'+key] = reg
    

# In[38]:


opt_func.plot_latency_function_2d(compute_df, callgraph, "A")
if cfg.PLOT:
    # NOTE: It plots latency function of call graph "A"
    opt_func.plot_latency_function_2d(compute_df, callgraph, "A")
    
opt_func.log_timestamp("train regression model")


# In[42]:


compute_time = dict()
compute_load = dict()
for key in callgraph:
    compute_time[key] = gppd.add_vars(gurobi_model, compute_df, name="compute_time_"+key, lb="min_compute_time_"+key)
for key in callgraph:
    compute_load[key] = gppd.add_vars(gurobi_model, compute_df, name="load_for_compute_edge_"+key, lb="min_load_"+key, ub="max_load_"+key)
gurobi_model.update()


# In[44]:


for index, row in compute_df.iterrows():
    data = dict()
    for key in callgraph:
        data["observed_x_"+key] = compute_load[key][index]
    m_feats = pd.DataFrame(
        data=data,
        index=[index]
    )
    for key in callgraph:
        print(f'callgraph key: {key}')
        print(f'{row["svc_name"]}')
        print(f'index: {index}')
        print(f'm_feats: {m_feats}')
        print(f'{compute_time[key][index]}')
        print(f'{row["latency_function_"+key]}')
        print()
        # (gurobi_model, regression model, x, y)
        pred_constr = add_predictor_constr(gurobi_model, row["latency_function_"+key], m_feats, compute_time[key][index])
gurobi_model.update()


# In[44]:


## Define names of the variables for network arc in gurobi
network_arc_var_name = opt_func.create_network_arc_var_name(unique_service, callgraph)
opt_func.check_network_arc_var_name(network_arc_var_name)

opt_func.plot_full_arc(compute_arc_var_name, network_arc_var_name, callgraph)
if cfg.PLOT:
    for key in callgraph:
        opt_func.plot_arc_var_for_callgraph(network_arc_var_name, unique_service, callgraph, key)


# In[36]:


columns=["src_svc", "src_cid", "dst_svc", "dst_cid", "min_network_time", "max_network_time"]
for key in callgraph:
    columns.append("max_load_"+key)
for key in callgraph:
    columns.append("min_load_"+key)
for key in callgraph:
     columns.append("min_egress_cost_"+key)
for key in callgraph:
     columns.append("max_egress_cost_"+key)
network_df = pd.DataFrame(
    columns=columns,
    data={
    },
    index=network_arc_var_name
)
if cfg.DISPLAY: display(network_df)


# In[36]:


src_svc_list = list()
dst_svc_list = list()
src_cid_list = list()
dst_cid_list = list()
min_network_time_list = list()
max_network_time_list = list()
min_egress_cost_list = list()
max_egress_cost_list = list()
call_size_list = list()
for var_name in network_arc_var_name:
    # print(var_name)
    if type(var_name) == tuple:
        src_svc = var_name[0].split(cfg.DELIMITER)[0]
        dst_svc = var_name[1].split(cfg.DELIMITER)[0]
        src_cid = int(var_name[0].split(cfg.DELIMITER)[1])
        dst_cid = int(var_name[1].split(cfg.DELIMITER)[1])
    else:
        print("var_name MUST be tuple datatype")
        assert False
    src_svc_list.append(src_svc)
    dst_svc_list.append(dst_svc)
    src_cid_list.append(src_cid)
    dst_cid_list.append(dst_cid)
    n_time = opt_func.get_network_time(src_cid, dst_cid)
    min_network_time_list.append(n_time)
    max_network_time_list.append(n_time)
    e_cost = opt_func.get_egress_cost(src_cid, src_svc, dst_svc, dst_cid, callsize_dict)
    min_egress_cost_list.append(e_cost)
    max_egress_cost_list.append(e_cost)
    
network_df["src_svc"] = src_svc_list
network_df["dst_svc"] = dst_svc_list
network_df["src_cid"] = src_cid_list
network_df["dst_cid"] = dst_cid_list
network_df["min_network_time"] = min_network_time_list
network_df["max_network_time"] = max_network_time_list
for index, row in network_df.iterrows():
    for key in callgraph:
        # if this network arc is in the callgraph
        if row["src_svc"] in callgraph[key] and row["dst_svc"] in callgraph[key][row["src_svc"]]:
            network_df.at[index, 'max_load_'+key] = MAX_LOAD[key]
        else:
            if row["src_svc"] == opt_func.source_node_name:
                network_df.at[index, 'max_load_'+key] = MAX_LOAD[key]
            else:
                network_df.at[index, 'max_load_'+key] = 0
        network_df.at[index, 'min_load_'+key] = 0
for key in callgraph:
    network_df["min_egress_cost_"+key] = min_egress_cost_list
    network_df["max_egress_cost_"+key] = max_egress_cost_list


# In[44]:




network_latency = dict()
for key in callgraph:
    network_latency[key] = gppd.add_vars(gurobi_model, network_df, name="network_latency", lb="min_network_time", ub="max_network_time")
network_load = dict()
for key in callgraph:
    network_load[key] = gppd.add_vars(gurobi_model, network_df, name="load_for_network_edge_"+key, lb="min_load_"+key, ub="max_load_"+key)

network_egress_cost = dict()
for key in callgraph:
    network_egress_cost[key] = gppd.add_vars(gurobi_model, network_df, name="network_egress_cost", lb="min_egress_cost_"+key, ub="max_egress_cost_"+key)
    
gurobi_model.update()

network_egress_cost_sum = 0
for key in callgraph:
    network_egress_cost_sum += sum(network_egress_cost[key].multiply(network_load[key]))

# compute_egress_cost = dict()
# compute_egress_cost = gppd.add_vars(gurobi_model, compute_df, name="compute_egress_cost", lb="min_egress_cost", ub="max_egress_cost")
# compute_egress_cost_sum = sum(compute_egress_cost.multiply(compute_load))
# print("compute_egress_cost_sum")
# print(compute_egress_cost_sum)

## compute edge egress cost is always 0
# total_egress_sum = network_egress_cost_sum + compute_egress_cost_sum
total_egress_sum = network_egress_cost_sum
gurobi_model.update()
    

# In[44]:
    

network_latency_sum = 0
compute_latency_sum = 0
for key in callgraph:
    network_latency_sum += sum(network_latency[key].multiply(network_load[key]))
    compute_latency_sum += sum(compute_time[key].multiply(compute_load[key]))
total_latency_sum = network_latency_sum + compute_latency_sum

# if cfg.DISPLAY:
print('total_egress_sum')
print(f'{total_egress_sum}\n')

print("compute_latency_sum:")
print(f"{compute_latency_sum}\n")

print("network_latency_sum:")
print(f"{network_latency_sum}\n")

print("total_latency_sum:")
print(f"{total_latency_sum}\n")


# In[44]:

objective = "latency" # latency or egress_cost or multi-objective
# objective = "multi-objective" # latency or egress_cost or multi-objective
if objective == "latency":
    gurobi_model.setObjective(total_latency_sum, gp.GRB.MINIMIZE)
    # gurobi_model.setObjective(compute_latency_sum, gp.GRB.MINIMIZE)
    # gurobi_model.setObjective(network_latency_sum, gp.GRB.MINIMIZE)
elif objective == "egress_cost":
    gurobi_model.setObjective(total_egress_sum, gp.GRB.MINIMIZE)
elif objective == "multi-objective":
    # NOTE: higher dollar per ms, more important the latency
    # DOLLAR_PER_MS: value of latency
    # lower dollar per ms, less tempting to re-route since bandwidth cost is becoming more important
    # simply speaking, when we have DOLLAR_PER_MS decreased, less offloading.
    gurobi_model.setObjective(total_latency_sum*cfg.DOLLAR_PER_MS + total_egress_sum, gp.GRB.MINIMIZE)
else:
    print("unsupported objective, ", objective)
    assert False
    
gurobi_model.update()
print(f"{cfg.log_prefix} model objective: {gurobi_model.getObjective()}")


# In[44]:


# print(help(gp.multidict))
# print(type(network_load))
# print(type(compute_load))

# arggreagated_load: dictionary
# arc: keys

temp = dict()
for key in callgraph:
    temp[key] = pd.concat([network_load[key], compute_load[key]], axis=0)
# concat_df = pd.concat(temp, axis=0)
# print("type(concat_df): ", type(concat_df))
# print("concat_df.to_dict()")
# concat_dict = concat_df.to_dict()
# for k, v in concat_dict.items():
    # print(f"key: {k}\nvalue: {v}")
# print()
arcs = dict()
aggregated_load = dict()
for key in callgraph:
    arcs[key], aggregated_load[key] = gp.multidict(temp[key].to_dict())
if cfg.DISPLAY:
    # print("arcs")
    # print(f'{arcs}\n')
    # print("aggregated_load")
    # print(f'{aggregated_load}\n')
    print("aggregated_load")
    # print(type(aggregated_load))
    for key in callgraph:
        for k, v in aggregated_load[key].items():
            print(f"key: {k}\nvalue: {v}")
            print()
    
opt_func.log_timestamp("gurobi add_vars and set objective")


# In[45]:

    
## Constraint 1: SOURCE
source = dict()
for key in callgraph:
    source[key] = dict()
    source[key][opt_func.source_node_fullname] = MAX_LOAD[key]
for key in callgraph:
    src_keys = source[key].keys()
    src_flow = gurobi_model.addConstrs((gp.quicksum(aggregated_load[key].select(src, '*')) == source[key][src] for src in src_keys), name="source_"+key)
    for cid in unique_service:
        for svc in unique_service[cid]:
            if opt_func.is_ingress_gw(svc, callgraph):
                ingress_gw_start_node = f'{svc}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start'
                per_cluster_load_in = gurobi_model.addConstr((gp.quicksum(aggregated_load[key].select('*', ingress_gw_start_node)) == NUM_REQUESTS[cid][key]), name="cluster_"+str(cid)+"_load_in-"+key)
                if cfg.DISPLAY:
                    print(aggregated_load[key].select('*', ingress_gw_start_node))
                    print("==")
                    print(NUM_REQUESTS[cid][key])
                    print("-"*80)

gurobi_model.update()


# In[47]:

## Constraint 2: destination
# destination = dict()
# destination[opt_func.destination_node_fullname] = MAX_LOAD
# dest_keys = destination.keys()
# leaf_services = list()
# for parent_svc, children in callgraph.items():
#     if len(children) == 0: # leaf service
#         leaf_services.append(parent_svc)
# num_leaf_services = len(leaf_services)
# app.logger.debug(f"{cfg.log_prefix} num_leaf_services: {num_leaf_services}")
# app.logger.debug(f"{cfg.log_prefix} leaf_services: {leaf_services}")
# dst_flow = gurobi_model.addConstrs((gp.quicksum(aggregated_load.select('*', dst)) == destination[dst]*num_leaf_services for dst in dest_keys), name="destination")
# for dst in dest_keys:
#     print(aggregated_load.select('*', dst))
# gurobi_model.update()


# In[47]:

## Constraint 3: flow conservation
# Start node in-out flow conservation
for key in callgraph:
    for svc in callgraph[key]:
        for cid in unique_service:
            if svc in unique_service[cid]:
                start_node = svc + cfg.DELIMITER + str(cid) + cfg.DELIMITER + "start"
                node_flow = gurobi_model.addConstr((gp.quicksum(aggregated_load[key].select('*', start_node)) == gp.quicksum(aggregated_load[key].select(start_node, '*'))), name="flow_conservation-start_node-"+key)
                # if cfg.DISPLAY:
                print(aggregated_load[key].select('*', start_node))
                print("==")
                print(aggregated_load[key].select(start_node, '*'))
                print("-"*50)
        
        
# In[47]:


# End node in-out flow conservation
# case 1 (leaf node to destination): incoming num requests == outgoing num request for all nodes
# for parent_svc, children in callgraph.items():
#     for cid in range(NUM_CLUSTER):
#         if len(children) == 0: # leaf_services:
#             end_node = parent_svc + cfg.DELIMITER + str(cid) + cfg.DELIMITER + "end"
#             node_flow = gurobi_model.addConstr((gp.quicksum(aggregated_load.select('*', end_node)) == gp.quicksum(aggregated_load.select(end_node, '*'))), name="flow_conservation["+end_node+"]-leaf_endnode")
#             print("*"*50)
#             print(aggregated_load.select('*', end_node))
#             print('==')
#             print(aggregated_load.select(end_node, '*'))
#             print("-"*50)
#             print("*"*50)

# In[47]:


# case 2 
# For non-leaf node and end node, incoming to end node == sum of outgoing
for key in callgraph:
    for parent_svc, children in callgraph[key].items():
        if len(children) > 0: # non-leaf services:
            for parent_cid in unique_service:
                if parent_svc in unique_service[parent_cid]:
                    end_node = opt_func.end_node_name(parent_svc, parent_cid)
                    for child_svc in children:
                        outgoing_sum = 0
                        child_list = list()
                        for child_cid in unique_service:
                            if child_svc in unique_service[child_cid]:
                                child_start_node = opt_func.start_node_name(child_svc, child_cid)
                                child_list.append(child_start_node)
                                outgoing_sum += aggregated_load[key].sum(end_node, child_start_node)
                        node_flow = gurobi_model.addConstr((gp.quicksum(aggregated_load[key].select('*', end_node)) == outgoing_sum), name="flow_conservation-nonleaf_endnode-"+key)
                        if cfg.DISPLAY:
                            print(aggregated_load[key].select('*', end_node))
                            print('==')
                            print(outgoing_sum)
                            print("-"*80)
gurobi_model.update()


# In[48]:


## Constraint 4: Tree topology
service_to_cid = dict()
for cid in unique_service:
    for svc_name in unique_service[cid]:
        if svc_name not in service_to_cid:
            service_to_cid[svc_name] = list()
        service_to_cid[svc_name].append(cid)
        
for key in callgraph:
    for svc_name in service_to_cid:
        if svc_name != cfg.ENTRANCE and svc_name in callgraph[key]:
            incoming_sum = 0
            for cid in service_to_cid[svc_name]:
                start_node = opt_func.start_node_name(svc_name, cid)
                incoming_sum += aggregated_load[key].sum('*', start_node)
            node_flow = gurobi_model.addConstr(incoming_sum == MAX_LOAD[key], name="tree_topo_conservation_"+key)
            if cfg.DISPLAY:
                print(incoming_sum)
                print('==')
                print(MAX_LOAD[key])
                print("-"*50)
gurobi_model.update()


# In[48]:


# # Constraint 5: max throughput of service
# max_tput = dict()
# for cid in range(NUM_CLUSTER):
#     for svc_name in unique_service[cid]:
#         max_tput[svc_name+cfg.DELIMITER+str(cid)+cfg.DELIMITER+"start"] = MAX_LOAD
#         max_tput[svc_name+cfg.DELIMITER+str(cid)+cfg.DELIMITER+"end"] = MAX_LOAD
# app.logger.info(f"{cfg.log_prefix} max_tput: {max_tput}")
# max_tput_key = max_tput.keys()
# throughput = gurobi_model.addConstrs((gp.quicksum(aggregated_load.select('*', n_)) <= max_tput[n_] for n_ in max_tput_key), name="service_capacity")
# constraint_setup_end_time = time.time()



# In[51]:

opt_func.log_timestamp("gurobi add constraints and model update")

## Defining objective function
gurobi_model.setParam('NonConvex', 2)
solve_start_time = time.time()
gurobi_model.update()
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
gurobi_model.optimize()
solve_end_time = time.time()
opt_func.log_timestamp("MODEL OPTIMIZE")

## Not belonging to optimizer critical path
ts = time.time()
varInfo = [(v.varName, v.LB, v.UB) for v in gurobi_model.getVars() ]
df_var = pd.DataFrame(varInfo) # convert to pandas dataframe
df_var.columns=['Variable Name','LB','UB'] # Add column headers
num_var = len(df_var)
constrInfo = [(c.constrName, gurobi_model.getRow(c), c.Sense, c.RHS) for c in gurobi_model.getConstrs() ]
df_constr = pd.DataFrame(constrInfo)
df_constr.columns=['Constraint Name','Constraint equation', 'Sense','RHS']
num_constr = len(df_constr)
if cfg.OUTPUT_WRITE:
    df_var.to_csv(cfg.OUTPUT_DIR+"/variable.csv")
    df_constr.to_csv(cfg.OUTPUT_DIR+"/constraint.csv")
with pd.option_context('display.max_colwidth', None):
    with pd.option_context('display.max_rows', None):
        print("df_var")
        display(df_var)
        print()
        print("df_constr")
        display(df_constr)
substract_time = time.time() - ts
opt_func.log_timestamp("get var and constraint")

opt_func.write_arguments_to_file(NUM_REQUESTS, callgraph, depth_dict, callsize_dict, unique_service)


if gurobi_model.Status != GRB.OPTIMAL:
    app.logger.info(f"{cfg.log_prefix} XXXXXXXXXXXXXXXXXXXXXXXXXXX")
    app.logger.info(f"{cfg.log_prefix} XXXX INFEASIBLE MODEL! XXXX")
    app.logger.info(f"{cfg.log_prefix} XXXXXXXXXXXXXXXXXXXXXXXXXXX")
    if cfg.DISPLAY:
        display(df_constr)
    
    gurobi_model.computeIIS()
    gurobi_model.write("gurobi_model.ilp")
    print('\nThe following constraints and variables are in the IIS:')
    # for c in gurobi_model.getConstrs():
    #     if c.IISConstr: print(f'\t{c.constrname}: {gurobi_model.getRow(c)} {c.Sense} {c.RHS}')
    for v in gurobi_model.getVars():
        if v.IISLB: print(f'\t{v.varname} ≥ {v.LB}')
        if v.IISUB: print(f'\t{v.varname} ≤ {v.UB}')
    print("OPTIMIZER, INFEASIBLE MODEL")
else:
    app.logger.info(f"{cfg.log_prefix} ooooooooooooooooooooooo")
    app.logger.info(f"{cfg.log_prefix} oooo SOLVED MODEL! oooo")
    app.logger.info(f"{cfg.log_prefix} ooooooooooooooooooooooo")

    ## Print out the result
    optimize_end_time = time.time()
    optimizer_runtime = round((optimize_end_time - optimizer_start_time) - substract_time, 5)
    solve_runtime = round(solve_end_time - solve_start_time, 5)
    app.logger.error(f"{cfg.log_prefix} ** Objective: {objective}")
    app.logger.error(f"{cfg.log_prefix} ** Num constraints: {num_constr}")
    app.logger.error(f"{cfg.log_prefix} ** Num variables: {num_var}")
    app.logger.error(f"{cfg.log_prefix} ** Optimization runtime: {optimizer_runtime} ms")
    app.logger.error(f"{cfg.log_prefix} ** model.optimize() runtime: {solve_runtime} ms")
    app.logger.error(f"{cfg.log_prefix} ** model.objVal: {gurobi_model.objVal}")
    # app.logger.error(f"{cfg.log_prefix} ** gurobi_model.objVal / total num requests: {gurobi_model.objVal/MAX_LOAD}")
    request_flow = dict()
    for key in callgraph:
        request_flow[key] = pd.DataFrame(columns=["Callgraph", "From", "To", "Flow"])
    for key in callgraph:
        for arc in arcs[key]:
            if aggregated_load[key][arc].x > 1e-6:
                temp = pd.DataFrame({"Callgraph":key, "From": [arc[0]], "To": [arc[1]], "Flow": [aggregated_load[key][arc].x]})
                request_flow[key] = pd.concat([request_flow[key], temp], ignore_index=True)
    if cfg.DISPLAY:
        for key in callgraph:
            display(request_flow[key])
    percentage_df = dict()
    for key in callgraph:
        percentage_df[key] = opt_func.translate_to_percentage(request_flow[key])
    for key in callgraph:
        print(f"percentage_df[{key}]")
        display(percentage_df[key])
        if percentage_df[key].empty == False:
            percentage_df[key].to_csv(f'{cfg.OUTPUT_DIR}/routing-{key}.csv')
            # opt_func.plot_callgraph_request_flow(percentage_df, key, unique_service, callgraph, network_arc_var_name)
    opt_func.plot_all_request_flow(percentage_df, unique_service, callgraph, network_arc_var_name)
            # opt_func.plot_request_flow(percentage_df[key])
    # opt_func.prettyprint_timestamp()
    # return percentage_df, "OPTIMIZER, MODEL SOLVED"
    # load_for_compute_edge_A[('productpage_v1#0#st
    for v in gurobi_model.getVars():
        print(f'{v}, {v.x}')
''' END of run_optimizer function'''


# In[52]:


# if __name__ == "__main__": ## COMMENT_OUT_FOR_JUPYTER
#     num_requests = [100, 500]
#     if SLATE_ON:
#         app.logger.info(f"{cfg.log_prefix} SLATE_ON")
#         if REAL_DATA == True:
#             traces = tst.parse_trace_file_ver2(trace_file)
#             traces, callgraph, depth_dict = tst.stitch_time(traces)
#             NUM_CLUSTER = len(traces)
#         elif REAL_DATA == False:
#             raw_traces=None
#             trace_file=None
#             app.logger.info(f"{cfg.log_prefix} No REAL DATA")
#         elif USE_TRACE_FILE:
#             TRACE_FILE_PATH="wrk_prof_log2_west.txt"
#             raw_traces=None
#             trace_file=TRACE_FILE_PATH
#         elif USE_PRERECORDED_TRACE: ## envoycon demo
#             TRACE_PATH="sampled_both_trace.txt"
#             df = pd.read_csv(TRACE_PATH)
#             raw_traces = sp.df_to_trace(df)
#             trace_file=None
#         else:
#             app.logger.error(f"{cfg.log_prefix} SLATE_ON, but no trace file")
#             assert False
#     else:
#         app.logger.info(f"{cfg.log_prefix} SLATE_OFF")
#         raw_traces=None
#         trace_file=None
        
#     percentage_df, desc = run_optimizer(raw_traces, trace_file, NUM_REQUESTS=num_requests) ## COMMENT_OUT_FOR_JUPYTER
#     # print("percentage_df")
#     # display(percentage_df)
#     ccr = opt_func.count_cross_cluster_routing(percentage_df)
#     print(f"** cross_cluster_routing: {ccr}")
#     if GRAPHVIZ and percentage_df.empty == False:
#         opt_func.plot_request_flow(percentage_df)
# %%
