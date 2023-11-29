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

random.seed(1234)

'''
For interactive run with jupyternotebook, comment out following lines "COMMENT_OUT_FOR_JUPYTER".
And adjust the indentation accordingly.
'''


# In[31]:

if not os.path.exists(cfg.OUTPUT_DIR):
    os.mkdir(cfg.OUTPUT_DIR)
    print(f"{cfg.log_prefix} mkdir {cfg.OUTPUT_DIR}")
else:
    print(f"{cfg.log_prefix} {cfg.OUTPUT_DIR} already exists")
    print("If you are using jupyter notebook, you should restart the kernel to load the new config.py")
    assert False
    
    
# In[31]:

NUM_REQUESTS = [50, 1]
MAX_LOAD = sum(NUM_REQUESTS)
NUM_CLUSTER = len(NUM_REQUESTS)

callgraph = {'ingress_gw': ['productpage-v1'], 'productpage-v1': ['details-v1', 'reviews-v3'], 'ratings-v1': [], 'details-v1': [], 'reviews-v3': ['ratings-v1']}
depth_dict = {'ingress_gw':0, 'productpage-v1': 1, 'details-v1': 2, 'reviews-v3': 2, 'ratings-v1': 3}
unique_service = dict()
unique_service[0] = ['ingress_gw', 'productpage-v1', 'details-v1', 'reviews-v3', 'ratings-v1']
unique_service[1] = ['ingress_gw', 'productpage-v1', 'details-v1', 'reviews-v3', 'ratings-v1']
callsize_dict = dict()
for parent_svc, children in callgraph.items():
    for child_svc in children:
        assert depth_dict[parent_svc] < depth_dict[child_svc]
        callsize_dict[(parent_svc,child_svc)] = (depth_dict[parent_svc]+1)*10


# In[31]:


''' START of run_optimizer function '''
# def run_optimizer(raw_traces=None, trace_file=None, NUM_REQUESTS=[100,900], model_parameter=None): ## COMMENT_OUT_FOR_JUPYTER
compute_arc_var_name = opt_func.create_compute_arc_var_name(unique_service, NUM_CLUSTER)
opt_func.check_compute_arc_var_name(compute_arc_var_name)
opt_func.log_timestamp("defining compute_arc_var_name")
if cfg.DISPLAY: display(compute_arc_var_name)
    
compute_df = pd.DataFrame(
    columns=["svc_name", "src_cid", "dst_cid", "min_compute_time", "min_load", "max_load", "min_egress_cost", "max_egress_cost", "observed_x", "observed_y", "latency_function", "call_size"],
    data={
    },
    index=compute_arc_var_name
)
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
compute_df["min_compute_time"] = 0
# compute_df["max_compute_time"] = math.inf
compute_df["min_load"] = 0
compute_df["max_load"] = MAX_LOAD
compute_df["min_egress_cost"] = 0
compute_df["max_egress_cost"] = 0
compute_df["call_size"] = 0

optimizer_start_time = time.time()
model = gp.Model('RequestRouting')

# In[35]:

opt_func.gen_fake_data(compute_df)


# In[38]:

for index, row in compute_df.iterrows():
    feat_transform = make_column_transformer(
        (StandardScaler(), ["observed_x"]),
        # ("passthrough", ["ld"]),
        verbose_feature_names_out=False,
        remainder='drop'
    )
    if cfg.REGRESSOR_DEGREE == 1:
        reg = make_pipeline(feat_transform, LinearRegression())
    elif cfg.REGRESSOR_DEGREE > 1:
        poly = PolynomialFeatures(degree=cfg.REGRESSOR_DEGREE, include_bias=True)
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
    if row["svc_name"] != tst.FRONTEND_svc:
        if cfg.REGRESSOR_DEGREE == 1:
            if reg["linearregression"].coef_ < 0:
                new_c = np.array([0.])
                reg["linearregression"].coef_ = new_c
                app.logger.info(f'{cfg.log_prefix} Service {row["svc_name"]}, changed slope {c_} --> {new_c}, intercept: {in_}')
                assert False
        if cfg.REGRESSOR_DEGREE == 2:
            # print("c_[2]: ", c_[2])
            if reg["linearregression"].coef_[1] < 0:
                new_c = np.array([0., 0.])
                reg["linearregression"].coef_ = new_c
                app.logger.info(f'{cfg.log_prefix} Service {row["svc_name"]}, changed slope {c_} --> {new_c}, intercept: {in_}')
                assert False
    c_ = reg["linearregression"].coef_
    in_ = reg["linearregression"].intercept_
    y_pred = reg.predict(X_test)
    r2 =  np.round(r2_score(y_test, y_pred),2)
    print(f'{cfg.log_prefix} {row["svc_name"]}, slope: {c_}, intercept: {in_}')
    compute_df.at[index, 'latency_function'] = reg
    
display(compute_df)


# In[38]:

# if PLOT:
opt_func.plot_latency_function(compute_df, NUM_CLUSTER)
opt_func.log_timestamp("train regression model")

# In[42]:

compute_time = gppd.add_vars(model, compute_df, name="compute_time", lb="min_compute_time")
compute_load = gppd.add_vars(model, compute_df, name="load_for_compute_edge", lb="min_load", ub="max_load")
model.update()
print("compute_time")
print(compute_time)
print("compute_load")
print(compute_load)


# In[44]:

m_feats = dict()
for index, row in compute_df.iterrows():
    # print("index: ", index)
    m_feats[index] = pd.DataFrame(
        data={
            "observed_x": compute_load[index],
        },
        index=[index]
    )
    pred_constr = add_predictor_constr(model, row["latency_function"], m_feats[index], compute_time[index])
    print(index, row["latency_function"])

model.update()

# In[44]:

## Define names of the variables for network arc in gurobi
network_arc_var_name = opt_func.create_network_arc_var_name(unique_service, NUM_CLUSTER, callgraph)
opt_func.check_network_arc_var_name(network_arc_var_name)


# In[36]:
    
network_df = pd.DataFrame(
    columns=["src_svc", "src_cid", "dst_svc", "dst_cid", "min_network_time", "max_network_time", "min_load", "max_load", "min_egress_cost", "max_egress_cost"],
    data={
    },
    index=network_arc_var_name
)
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
    print(var_name)
    if type(var_name) == tuple:
        src_svc = var_name[0].split(cfg.DELIMITER)[0]
        dst_svc = var_name[1].split(cfg.DELIMITER)[0]
    else:
        src_svc = var_name.split(",")[0].split(cfg.DELIMITER)[0]
        dst_svc = var_name.split(",")[1].split(cfg.DELIMITER)[0]
    src_svc_list.append(src_svc)
    dst_svc_list.append(dst_svc)
    if type(var_name) == tuple:
        src_cid = int(var_name[0].split(cfg.DELIMITER)[1])
        dst_cid = int(var_name[1].split(cfg.DELIMITER)[1])
    else:
        src_cid = int(var_name.split(",")[0].split(cfg.DELIMITER)[1])
        dst_cid = int(var_name.split(",")[1].split(cfg.DELIMITER)[1])
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
network_df["min_load"] = 0
network_df["max_load"] = MAX_LOAD
network_df["min_egress_cost"] = min_egress_cost_list
network_df["max_egress_cost"] = max_egress_cost_list

display(network_df)


# In[44]:

network_latency = gppd.add_vars(model, network_df, name="network_latency", lb="min_network_time", ub="max_network_time")
network_load = gppd.add_vars(model, network_df, name="load_for_network_edge", lb="min_load", ub="max_load")
network_egress_cost = gppd.add_vars(model, network_df, name="network_egress_cost", lb="min_egress_cost", ub="max_egress_cost")
compute_egress_cost = gppd.add_vars(model, compute_df, name="compute_egress_cost", lb="min_egress_cost", ub="max_egress_cost")
model.update()

# egress cost sum
compute_egress_cost_sum = sum(compute_egress_cost.multiply(compute_load))
network_egress_cost_sum = sum(network_egress_cost.multiply(network_load))
print("network_egress_cost_sum")
print(network_egress_cost_sum)
print("compute_egress_cost_sum")
print(compute_egress_cost_sum)
model.update()
    

# In[44]:
    
total_egress_sum = network_egress_cost_sum + compute_egress_cost_sum

network_latency_sum = sum(network_latency.multiply(network_load))
compute_latency_sum = sum(compute_time.multiply(compute_load))
total_latency_sum = network_latency_sum + compute_latency_sum


print('total_egress_sum')
print(f'{total_egress_sum}\n')

print("compute_latency_sum:")
print(f"{compute_latency_sum}\n")

print("network_latency_sum:")
print(f"{network_latency_sum}\n")

print("total_latency_sum:")
print(f"{total_latency_sum}\n")


# In[44]:

# objective = "latency" # latency or egress_cost or multi-objective
objective = "multi-objective" # latency or egress_cost or multi-objective
if objective == "latency":
    model.setObjective(total_latency_sum, gp.GRB.MINIMIZE)
    # model.setObjective(compute_latency_sum, gp.GRB.MINIMIZE)
elif objective == "egress_cost":
    model.setObjective(total_egress_sum, gp.GRB.MINIMIZE)
elif objective == "multi-objective":
    # NOTE: higher dollar per ms, more important the latency
    # DOLLAR_PER_MS: value of latency
    # lower dollar per ms, less tempting to re-route since bandwidth cost is becoming more important
    # simply speaking, when we have DOLLAR_PER_MS decreased, less offloading.
    model.setObjective(total_latency_sum*cfg.DOLLAR_PER_MS + total_egress_sum, gp.GRB.MINIMIZE)
else:
    print("unsupported objective, ", objective)
    assert False
    
model.update()
app.logger.info(f"{cfg.log_prefix} model objective: {model.getObjective()}")

# arcs is the keys
# aggregated_load is dictionary
# aggregated_load = dict()
# concat_compute_load = pd.Series()
# for elem in compute_arc_var_name:
#     concat_compute_load = pd.concat([concat_compute_load, compute_load[elem]], axis=0)
# arcs, aggregated_load = gp.multidict(pd.concat([network_load, concat_compute_load], axis=0).to_dict())
print(help(gp.multidict))
print(type(network_load))
print(type(compute_load))
arcs, aggregated_load = gp.multidict(pd.concat([network_load, compute_load], axis=0).to_dict())
print("arcs")
print(f'{arcs}\n')
print("aggregated_load")
print(f'{aggregated_load}\n')
opt_func.log_timestamp("gurobi add_vars and set objective")


# In[45]:

print(type(aggregated_load))
for k, v in aggregated_load.items():
    print(f"key: {k}, value: {v}")
    
## Constraint 1: source
source = dict()
source[opt_func.source_node_fullname] = MAX_LOAD
src_keys = source.keys()
# source(src_*_*) to *
src_flow = model.addConstrs((gp.quicksum(aggregated_load.select(src, '*')) == source[src] for src in src_keys), name="source")
# SOURCE to frontend services
for cid in range(NUM_CLUSTER):
    start_node = f'{cfg.ENTRANCE}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start'
    per_cluster_load_in = model.addConstr((gp.quicksum(aggregated_load.select('*', start_node)) == NUM_REQUESTS[cid]), name="cluster_"+str(cid)+"_load_in")
    print("start_node: ", start_node)
    print(aggregated_load.select('*', start_node))
    print(NUM_REQUESTS[cid])
model.update()


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
# dst_flow = model.addConstrs((gp.quicksum(aggregated_load.select('*', dst)) == destination[dst]*num_leaf_services for dst in dest_keys), name="destination")
# for dst in dest_keys:
#     print(aggregated_load.select('*', dst))
# model.update()


# In[47]:

## Constraint 3: flow conservation
# Start node in-out flow conservation
for cid in range(NUM_CLUSTER):
    for svc_name in unique_service[cid]:
        start_node = svc_name + cfg.DELIMITER + str(cid) + cfg.DELIMITER + "start"
        node_flow = model.addConstr((gp.quicksum(aggregated_load.select('*', start_node)) == gp.quicksum(aggregated_load.select(start_node, '*'))), name="flow_conservation["+start_node+"]-start_node")
        print(aggregated_load.select('*', start_node))
        print("==")
        print(aggregated_load.select(start_node, '*'))
        print("-"*50)
# End node in-out flow conservation
# case 1 (leaf node to destination): incoming num requests == outgoing num request for all nodes
# for parent_svc, children in callgraph.items():
#     for cid in range(NUM_CLUSTER):
#         if len(children) == 0: # leaf_services:
#             end_node = parent_svc + cfg.DELIMITER + str(cid) + cfg.DELIMITER + "end"
#             node_flow = model.addConstr((gp.quicksum(aggregated_load.select('*', end_node)) == gp.quicksum(aggregated_load.select(end_node, '*'))), name="flow_conservation["+end_node+"]-leaf_endnode")
#             print("*"*50)
#             print(aggregated_load.select('*', end_node))
#             print('==')
#             print(aggregated_load.select(end_node, '*'))
#             print("-"*50)
#             print("*"*50)

# case 2 (non-leaf node AND end node): <incoming to end node == outgoing>
for parent_svc, children in callgraph.items():
    if len(children) > 0: # non-leaf services:
        for parent_cid in range(NUM_CLUSTER):
            end_node = parent_svc + cfg.DELIMITER + str(parent_cid) + cfg.DELIMITER + "end"
            for child_svc in children:
                out_sum = 0
                child_list = list()
                for child_cid in range(NUM_CLUSTER):
                    child_start_node = child_svc +cfg.DELIMITER + str(child_cid) + cfg.DELIMITER+"start"
                    child_list.append(child_start_node)
                    out_sum += aggregated_load.sum(end_node, child_start_node)
                node_flow = model.addConstr((gp.quicksum(aggregated_load.select('*', end_node)) == out_sum), name="flow_conservation["+end_node+"]-nonleaf_endnode")
                print(aggregated_load.select('*', end_node))
                print('==')
                print(out_sum)
                print("-"*50)
                app.logger.debug(f"{cfg.log_prefix} nonleaf end_node flow conservation")
                app.logger.debug(f"{cfg.log_prefix} {end_node}, {child_list}")
model.update()


# In[48]:


## Constraint 4: Tree topology
service_to_cid = dict()
for cid in range(NUM_CLUSTER):
    for svc_name in unique_service[cid]:
        if svc_name not in service_to_cid:
            service_to_cid[svc_name] = list()
        service_to_cid[svc_name].append(cid)
for svc_name in service_to_cid:
    if svc_name != cfg.ENTRANCE:
        incoming_sum = 0
        for cid in service_to_cid[svc_name]:
            node_name = svc_name +cfg.DELIMITER + str(cid) + cfg.DELIMITER+"start"
            incoming_sum += aggregated_load.sum('*', node_name)
        node_flow = model.addConstr(incoming_sum == MAX_LOAD, name="tree_topo_conservation")
model.update()


# In[48]:


# # Constraint 5: max throughput of service
# max_tput = dict()
# for cid in range(NUM_CLUSTER):
#     for svc_name in unique_service[cid]:
#         max_tput[svc_name+cfg.DELIMITER+str(cid)+cfg.DELIMITER+"start"] = MAX_LOAD
#         max_tput[svc_name+cfg.DELIMITER+str(cid)+cfg.DELIMITER+"end"] = MAX_LOAD
# app.logger.info(f"{cfg.log_prefix} max_tput: {max_tput}")
# max_tput_key = max_tput.keys()
# throughput = model.addConstrs((gp.quicksum(aggregated_load.select('*', n_)) <= max_tput[n_] for n_ in max_tput_key), name="service_capacity")
# constraint_setup_end_time = time.time()

opt_func.log_timestamp("gurobi add constraints and model update")


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
solve_end_time = time.time()
opt_func.log_timestamp("MODEL OPTIMIZE")

## Not belonging to optimizer critical path
ts = time.time()
varInfo = [(v.varName, v.LB, v.UB) for v in model.getVars() ]
df_var = pd.DataFrame(varInfo) # convert to pandas dataframe
df_var.columns=['Variable Name','LB','UB'] # Add column headers
num_var = len(df_var)
constrInfo = [(c.constrName, model.getRow(c), c.Sense, c.RHS) for c in model.getConstrs() ]
df_constr = pd.DataFrame(constrInfo)
df_constr.columns=['Constraint Name','Constraint equation', 'Sense','RHS']
num_constr = len(df_constr)
if cfg.OUTPUT_WRITE:
    df_var.to_csv(cfg.OUTPUT_DIR+"/variable.csv")
    df_constr.to_csv(cfg.OUTPUT_DIR+"/constraint.csv")
if cfg.DISPLAY:
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


if model.Status != GRB.OPTIMAL:
    app.logger.info(f"{cfg.log_prefix} XXXXXXXXXXXXXXXXXXXXXXXXXXX")
    app.logger.info(f"{cfg.log_prefix} XXXX INFEASIBLE MODEL! XXXX")
    app.logger.info(f"{cfg.log_prefix} XXXXXXXXXXXXXXXXXXXXXXXXXXX")
    if cfg.DISPLAY:
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
    app.logger.error(f"{cfg.log_prefix} ** model.objVal: {model.objVal}")
    app.logger.error(f"{cfg.log_prefix} ** model.objVal / total num requests: {model.objVal/MAX_LOAD}")
    request_flow = pd.DataFrame(columns=["From", "To", "Flow"])
    for arc in arcs:
        if aggregated_load[arc].x > 1e-6:
            temp = pd.DataFrame({"From": [arc[0]], "To": [arc[1]], "Flow": [aggregated_load[arc].x]})
            request_flow = pd.concat([request_flow, temp], ignore_index=True)
    if cfg.DISPLAY:
        display(request_flow)
    percentage_df = opt_func.translate_to_percentage(request_flow)
    if cfg.DISPLAY:
        display(percentage_df)
    if percentage_df.empty == False:
        percentage_df.to_csv(cfg.OUTPUT_DIR+"/routing.csv")
        opt_func.plot_request_flow(percentage_df)
    # opt_func.prettyprint_timestamp()
    # return percentage_df, "OPTIMIZER, MODEL SOLVED"
''' END of run_optimizer function'''


# In[52]:

if __name__ == "__main__": ## COMMENT_OUT_FOR_JUPYTER
    num_requests = [100, 500]
    if SLATE_ON:
        app.logger.info(f"{cfg.log_prefix} SLATE_ON")
        if REAL_DATA == True:
            traces = tst.parse_trace_file_ver2(trace_file)
            traces, callgraph, depth_dict = tst.stitch_time(traces)
            NUM_CLUSTER = len(traces)
        elif REAL_DATA == False:
            raw_traces=None
            trace_file=None
            app.logger.info(f"{cfg.log_prefix} No REAL DATA")
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
            app.logger.error(f"{cfg.log_prefix} SLATE_ON, but no trace file")
            assert False
    else:
        app.logger.info(f"{cfg.log_prefix} SLATE_OFF")
        raw_traces=None
        trace_file=None
        
    percentage_df, desc = run_optimizer(raw_traces, trace_file, NUM_REQUESTS=num_requests) ## COMMENT_OUT_FOR_JUPYTER
    # print("percentage_df")
    # display(percentage_df)
    ccr = opt_func.count_cross_cluster_routing(percentage_df)
    print(f"** cross_cluster_routing: {ccr}")
    if GRAPHVIZ and percentage_df.empty == False:
        opt_func.plot_request_flow(percentage_df)
# %%
