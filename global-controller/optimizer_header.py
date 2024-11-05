import logging
import config as cfg
# from global_controller import app
import graphviz
import itertools
import pandas as pd
import matplotlib.pyplot as plt
import math
import numpy as np
import time
import zlib
from IPython.display import display
import random
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.preprocessing import StandardScaler
from sklearn.compose import make_column_transformer
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline
from sklearn.metrics import r2_score
import span as sp
import pprint
import hashlib

logging.config.dictConfig(cfg.LOGGING_CONFIG)
logger = logging.getLogger(__name__) # this line should be added to every function


random.seed(1234)

name_cut = 10

timestamp_list = list()
source_node_name = "SOURCE"
destination_node_name = "DESTINATION"
NONE_CID = "XXXX"
NONE_TYPE = "-1"
source_node_fullname = f'{source_node_name}{cfg.DELIMITER}{NONE_CID}{cfg.DELIMITER}end'
destination_node_fullname = f'{destination_node_name}{cfg.DELIMITER}{NONE_CID}{cfg.DELIMITER}end'


# node_color = ["#FFBF00", "#ff6375", "#6973fa", "#AFE1AF"]# yellow, pink, blue, green
node_color_dict = dict()
node_color_dict["XXXX"] = "gray"
node_color_dict['-1'] = "#FFBF00"
node_color_dict['us-west-1'] = "#FFBF00"
node_color_dict['us-east-1'] = "#ff6375"
node_color_dict['us-central-1'] = "green"

edge_color_list = ["red", "blue", "green", "yellow"]
# edge_color_taken = dict()

def calculate_depth(graph, node):
    if node not in graph or not graph[node]:
        logger.debug(f"leaf node: {node}, depth: 1")
        return 1
    children = graph[node]
    child_depths = [calculate_depth(graph, child) for child in children]
    return 1 + max(child_depths)


def get_depth(cg, dep_dict, cur_node, cur_dep):
    dep_dict[cur_node] = cur_dep
    if len(cg[cur_node]) == 0: # leaf
        return
    cur_dep += 1
    for svc in cg[cur_node]:
        get_depth(cg, dep_dict, svc, cur_dep)


def get_depth_in_graph(cg):
    depth_dict = dict()
    root_node = find_root_node(cg)
    get_depth(cg, depth_dict, root_node, 0)
    return depth_dict


# def get_callsize_dict(cg, depth):
#     callsize_dict = dict()
#     for parent in cg:
#         for child in cg[parent]:
#             assert depth[parent] < depth[child]
#             logger.debug(f"depth[{parent}]")
#             callsize_dict[(parent,child)] = ((depth[parent]+1)*10)
#     return callsize_dict

def get_callsize_dict(ep_str_callgraph, endpoint_sizes):
    callsize_dict = dict()
    for parent_endpoint in ep_str_callgraph:
        for child_endpoint in ep_str_callgraph[parent_endpoint]:
            parent_url = parent_endpoint.split(cfg.ep_del)[2]
            child_url = child_endpoint.split(cfg.ep_del)[2]
            if child_url in endpoint_sizes:
                callsize_dict[(parent_endpoint,child_endpoint)] = endpoint_sizes[child_url]
                # logger.info(f"callsize_dict[{parent_endpoint},{child_endpoint}] = {endpoint_sizes[child_url]}")
            else:
                callsize_dict[(parent_endpoint,child_endpoint)] = 1024
                logger.info(f"{parent_endpoint} does not exist in endpoint_sizes. Set to 1024")
    return callsize_dict


def get_compute_arc_var_name(endpoint, cid):
    return (f'{endpoint}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start', f'{endpoint}{cfg.DELIMITER}{cid}{cfg.DELIMITER}end') # tuple
    # return f'{endpoint}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start,{endpoint}{cfg.DELIMITER}{cid}{cfg.DELIMITER}end' # string
    

def create_compute_arc_var_name(all_endpoints):
    compute_arc_var_name = list()
    for cid in all_endpoints:
        for svc_name in all_endpoints[cid]:
            for endpoint in all_endpoints[cid][svc_name]:
                compute_arc_var_name.append(get_compute_arc_var_name(endpoint, cid))
    return compute_arc_var_name


def get_svc(var_name):
    return var_name.split(cfg.DELIMITER)[0]


def get_cid(var_name):
    return var_name.split(cfg.DELIMITER)[1]


def get_node_type(var_name):
    return var_name.split(cfg.DELIMITER)[2]


def is_network_var(var_tuple):
    src_node_type = get_node_type(var_tuple[0])
    dst_node_type = get_node_type(var_tuple[1])
    
    if (src_node_type == "end" and dst_node_type == "start") or (src_node_type == NONE_TYPE) or (dst_node_type == NONE_TYPE):
        return True
    elif var_tuple[0].split(cfg.DELIMITER)[2] == "start" and var_tuple[1].split(cfg.DELIMITER)[2] == "end":
        return False
    else:
        logger.error(f'Wrong var_tuple: {var_tuple}')
        assert False
    

def fake_load_gen(callgraph):
    num_data_point = 50
    load_list = list()
    for ld in range(num_data_point):
        temp_dict = dict()
        for key in callgraph:
            temp_dict[key] = ld
        # TODO
        load_list.append(temp_dict) ## [{'A':load_of_callgraph_A, 'B':load_of_callgraph_B}, ...]
    return np.array(load_list)


def get_slope(svc_name, callgraph):
    ret = dict()
    for key in callgraph:
        if svc_name == "ingress_gw":
            ret[key] = 0
        else:
            ret[key] = 1
            # ret[key] = zlib.adler32(svc_name.encode('utf-8'))%5+1
    return ret


def get_compute_latency(load, svc_name, slope, intercept, target_cg, callgraph):
    if len(load) != len(slope):
        logger.error(f'Wrong length of load({len(load)}) != slope({len(slope)})')
        assert False
    if svc_name == "ingress_gw":
        return 0
    ret = 0
    for key in callgraph:
        ret += pow(load[key], cfg.REGRESSOR_DEGREE) * slope[key]
    # ret += intercept + random.randint(0, 5)
    ret += intercept
    # TODO: the s not being used currently, target_cg. 
    # Hence, the same regression function is used for all callgraphs.
    # Ideally,
    # if = "A, target_cg":
    #     latency_function = XXX
    # elif = "B, target_cg":
    #     latency_function = YYY
    return ret


def plot_latency_function_3d(compute_df, y_axis_target_cg_key):
    idx = 0
    ylim = 0
    num_subplot_row = len(compute_df["src_cid"].unique())
    num_subplot_col = len(compute_df["svc_name"].unique())
    # fig, axs = plt.subplots(num_subplot_row, num_subplot_col, figsize=(16,6))
    
    fig = plt.figure()
    fig.tight_layout()
    for index, row in compute_df.iterrows():
        data = dict()
        for key in callgraph:
            data["observed_x_"+key] = row["observed_x_"+key]
        temp_df = pd.DataFrame(data=data)
        row_idx = int(idx/num_subplot_col)
        col_idx = idx%num_subplot_col
        ax = fig.add_subplot(100 + (row_idx+1)*10 + (col_idx+1), projection='3d')
        ax.scatter(row["observed_x_A"], row["observed_x_B"], row["observed_y_"+y_axis_target_cg_key], c='r', marker='o', label="observation", alpha=0.1)
        ylim = max(ylim, max(row["observed_y_"+y_axis_target_cg_key]), max(row["latency_function"].predict(temp_df)))
        # axs[row_idx][col_idx].legend()
        # axs[row_idx][col_idx].set_title(index[0])
        # if row_idx == num_subplot_row-1:
        #     axs[row_idx][col_idx].set_xlabel("ld")
        # if col_idx == 0:
        #     axs[row_idx][col_idx].set_ylabel("Compute time")
        # idx += 1

    
def plot_latency_function_2d(compute_df, callgraph, y_axis_target_cg_key):
    idx = 0
    ylim = 0
    num_subplot_row = len(compute_df["src_cid"].unique())
    num_subplot_col = len(compute_df["svc_name"].unique())
    fig, axs = plt.subplots(num_subplot_row, num_subplot_col, figsize=(16,6))
    fig.tight_layout()
    for index, row in compute_df.iterrows():
        data = dict()
        for key in callgraph:
            data["observed_x_"+key] = row["observed_x_"+key]
        temp_df = pd.DataFrame(
            data=data
        )
        # X_ = temp_df[["observed_x_A", "observed_x_B"]]
        X_ = temp_df
        row_idx = int(idx/num_subplot_col)
        col_idx = idx%num_subplot_col
        # NOTE: It only plots callgraph A as a x-axis for visualization
        # If you want to plot latency function having all callgraph in x-axis, you need higher dimesnion plot like 3d plot.
        x_axis_cg = "A"
        axs[row_idx][col_idx].plot(row["observed_x_"+x_axis_cg], row["observed_y_"+y_axis_target_cg_key], 'ro', label="observation", alpha=0.1)
        axs[row_idx][col_idx].plot(row["observed_x_"+x_axis_cg], row["latency_function_"+key].predict(X_), 'bo', label="prediction", alpha=0.1)
        ylim = max(ylim, max(row["observed_y_"+y_axis_target_cg_key]), max(row["latency_function_"+key].predict(X_)))
        axs[row_idx][col_idx].legend()
        axs[row_idx][col_idx].set_title(index[0])
        if row_idx == num_subplot_row-1:
            axs[row_idx][col_idx].set_xlabel("Load in " + x_axis_cg + "callgraph")
        if col_idx == 0:
            axs[row_idx][col_idx].set_ylabel("Compute time")
        idx += 1
    for ax in axs.flat:
        ax.set_ylim(0, ylim)
    plt.savefig(cfg.OUTPUT_DIR+"/latency_callgraph"+y_axis_target_cg_key+".pdf")
    plt.show()


def get_network_arc_var_name(src_ep, dst_ep, src_cid, dst_cid):
    assert src_ep != dst_ep
    assert dst_cid != NONE_CID
    return (f'{src_ep}{cfg.DELIMITER}{src_cid}{cfg.DELIMITER}end',f'{dst_ep}{cfg.DELIMITER}{dst_cid}{cfg.DELIMITER}start')


def is_X_child_of_Y(X_svc, Y_svc, callgraph):
    for key in callgraph:
        if Y_svc in callgraph[key]:
            if X_svc in callgraph[key][Y_svc]:
                return True
    return False


def get_cluster_pair(endpoint_to_placement):
    cid_list = all_endpoints.keys()
    cluster_pair = list(itertools.product(cid_list, cid_list))
    return cluster_pair
    
# endpoint_to_placement = {
# {'A,POST,post': {0, 1}, \
#   'A,GET,read': {0, 1}, \
#   'B,GET,read': {0, 1}, \
#   'C,POST,post': {0, 1}}    
def create_network_arc_var_name(endpoint_to_placement):
    cluster_pair = get_cluster_pair(endpoint_to_placement)
    network_arc_var_name = list()
    # [(0, 0), (0, 1), (1, 0), (1, 1)]
    logger.debug("cluster_pair: ", cluster_pair)
    for c_pair in cluster_pair:
        src_cid = c_pair[0]
        dst_cid = c_pair[1]
        for src_svc in unique_service[src_cid]:
            for dst_svc in unique_service[dst_cid]:
                if src_svc != dst_svc and is_X_child_of_Y(X_svc=dst_svc, Y_svc=src_svc, callgraph=callgraph):
                    var_name = get_network_arc_var_name(src_svc, src_cid, dst_svc, dst_cid)
                    if var_name not in network_arc_var_name:
                        network_arc_var_name.append(var_name)

    # SOURCE to ingress_gw
    for cid in range(len(unique_service)):
        for svc in unique_service[cid]:
            if svc == "ingress_gw":
                network_arc_var_name.append((source_node_fullname, f'{svc}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start'))
            ## leaf nodes to DESTINATION are removed since they are redundant
            # if callgraph[svc] == []:
            #     network_arc_var_name.append((f'{svc}{cfg.DELIMITER}{cid}{cfg.DELIMITER}end', destination_node_fullname))
    return network_arc_var_name


def write_arguments_to_file(num_reqs, callgraph, depth_dict, callsize_dict, unique_service):
    num_cluster = len(unique_service)
    temp = ''
    temp += f'{cfg.log_prefix} APP_NAME: {cfg.APP_NAME}\n'
    temp += f'{cfg.log_prefix} NUM_CLUSTER: {num_cluster}\n'
    temp += f'{cfg.log_prefix} callgraph: {callgraph}\n'
    for cid in range(len(num_reqs)):
        temp += f'{cfg.log_prefix} num_reqs[{cid}]: {num_reqs[cid]}\n'
    for cid in unique_service:
        temp += f'{cfg.log_prefix} unique_service[{cid}]: {unique_service[cid]}\n'
    temp += f'{cfg.log_prefix} depth_dict: {depth_dict}\n'
    temp += f'{cfg.log_prefix} callsize_dict: {callsize_dict}\n'
    temp += f'{cfg.log_prefix} REGRESSOR_DEGREE: {cfg.REGRESSOR_DEGREE}\n'
    temp += f'{cfg.log_prefix} INTRA_CLUTER_RTT: {cfg.INTRA_CLUTER_RTT}\n'
    temp += f'{cfg.log_prefix} INTER_CLUSTER_RTT: {cfg.INTER_CLUSTER_RTT}\n'
    temp += f'{cfg.log_prefix} INTER_CLUSTER_EGRESS_COST: {cfg.INTER_CLUSTER_EGRESS_COST}\n'
    temp += f'{cfg.log_prefix} DOLLAR_PER_MS: {cfg.DOLLAR_PER_MS}\n'
    with open(f'{cfg.OUTPUT_DIR}/arguments.txt', 'w') as f:
        f.write(temp)
    
def check_compute_arc_var_name(c_arc_var_name):
    for elem in c_arc_var_name:
        if type(elem) == tuple:
            src_node = elem[0]
            dst_node = elem[1]
        else:
            src_node = elem.split(",")[0]
            dst_node = elem.split(",")[1]
        
        src_svc_name = src_node.split(cfg.DELIMITER)[0]
        src_cid = src_node.split(cfg.DELIMITER)[1]
        src_node_type = src_node.split(cfg.DELIMITER)[2]
        dst_svc_name = dst_node.split(cfg.DELIMITER)[0]
        dst_cid = dst_node.split(cfg.DELIMITER)[1]
        dst_node_type = dst_node.split(cfg.DELIMITER)[2]
        
        if src_svc_name != dst_svc_name:
            logger.error(f'src_svc_name != dst_svc_name, {src_svc_name} != {dst_svc_name}')
            assert False
        if src_cid != dst_cid:
            logger.error(f'src_cid != dst_cid, {src_cid} != {dst_cid}')
            assert False
        if src_node_type != "start":
            logger.error(f'src_node_type != "start", {src_node_type} != "start"')
            assert False
        if dst_node_type != "end":
            logger.error(f'dst_node_type != "end", {dst_node_type} != "end"')
            assert False


def is_ingress_gw(target_svc, callgraph):
    for key in callgraph:
        for parent_svc in callgraph[key]:
            if target_svc in callgraph[key][parent_svc]:
                # logger.error(f'{target_svc} is NOT ingress_gw')
                return False
    # logger.error(f'{target_svc} is ingress_gw')
    return True


def get_compute_df_column(ep_str_callgraph_table):
    columns = ["svc_name", "src_cid", "dst_cid", "call_size", "max_load", "min_load", "observed_x", "observed_y", "coef", "min_compute_latency"]
        
    # for cg_key in ep_str_callgraph_table:
    #     columns.append("max_load_"+cg_key)
    # for cg_key in ep_str_callgraph_table:
    #     columns.append("min_load_"+cg_key)
    # for cg_key in ep_str_callgraph_table:
    #     columns.append("observed_x_"+cg_key)
    # for cg_key in ep_str_callgraph_table:
    #     columns.append("observed_y_"+cg_key)
    # for cg_key in ep_str_callgraph_table:
    #     columns.append("latency_function_"+cg_key)
    # for cg_key in ep_str_callgraph_table:
    #     columns.append("min_compute_latency_"+cg_key)
    return columns


# Old version
# def get_regression_pipeline(endpoint_load_dict):
#     numeric_features = list()
#     for ep in endpoint_load_dict:
#         numeric_features.append("observed_x_"+ep)
#     feat_transform = make_column_transformer(
#         # (StandardScaler(), numeric_featuress),
#         ('passthrough', numeric_features),
#         verbose_feature_names_out=False,
#         remainder='drop'
#     )
#     if cfg.REGRESSOR_DEGREE == 1:
#         reg = make_pipeline(feat_transform, LinearRegression())
#     elif cfg.REGRESSOR_DEGREE > 1:
#         '''
#         (X1,X2) transforms to (1,X1,X2,X1^2,X1X2,X2^2)
#         (X1,X2,X3) transforms to (1, X1, X2, X3, X1X2, X1X3, X2X3, X1^2 * X2, X2^2 * X3, X3^2 * X1)
#         '''
#         poly = PolynomialFeatures(degree=cfg.REGRESSOR_DEGREE, include_bias=True)
#         reg = make_pipeline(feat_transform, poly, LinearRegression())
#     return reg


def get_regression_pipeline(load_dict):
    numeric_features = list()
    for key in load_dict:
        numeric_features.append("observed_x_"+key)
    feat_transform = make_column_transformer(
        # (StandardScaler(), numeric_featuress),
        ('passthrough', numeric_features),
        verbose_feature_names_out=False,
        remainder='drop'
    )
    data = dict()
    for key in load_dict:
        data["observed_x_"+key] = load_dict[key]
    df = pd.DataFrame(
        data=data,
    )
    if cfg.REGRESSOR_DEGREE == 1:
        reg = make_pipeline(feat_transform, LinearRegression())
    elif cfg.REGRESSOR_DEGREE > 1:
        '''
        (X1,X2) transforms to (1,X1,X2,X1^2,X1X2,X2^2)
        (X1,X2,X3) transforms to (1, X1, X2, X3, X1X2, X1X3, X2X3, X1^2 * X2, X2^2 * X3, X3^2 * X1)
        '''
        poly = PolynomialFeatures(degree=cfg.REGRESSOR_DEGREE, include_bias=True)
        reg = make_pipeline(feat_transform, poly, LinearRegression())
    return reg, df
    

def fill_compute_df(compute_df, compute_arc_var_name, ep_str_callgraph_table, max_capacity_per_service):
    logger = logging.getLogger(__name__)
    endpoint_list = list()
    svc_name_list = list()
    method_list = list()
    url_list = list()
    src_cid_list = list()
    dst_cid_list = list()
    for var_name in compute_arc_var_name:
        if type(var_name) == tuple:
            ep = var_name[0].split(cfg.DELIMITER)[0]
            svc_name = ep.split(cfg.ep_del)[0]
            method = ep.split(cfg.ep_del)[1]
            url = ep.split(cfg.ep_del)[2]
            endpoint_list.append(ep)
            svc_name_list.append(svc_name)
            method_list.append(method)
            url_list.append(url)
            # src_cid = int(var_name[0].split(cfg.DELIMITER)[1])
            # dst_cid = int(var_name[1].split(cfg.DELIMITER)[1])
            src_cid = var_name[0].split(cfg.DELIMITER)[1]
            dst_cid = var_name[1].split(cfg.DELIMITER)[1]
            assert src_cid == dst_cid
            src_cid_list.append(src_cid)
            dst_cid_list.append(dst_cid)
        else:
            logger.error(f'Wrong var_name type: {type(var_name)}. It must be tuple')
            assert False
            endpoint_list.append(var_name.split(",")[0].split(cfg.DELIMITER)[0])
            src_cid_list.append(int(var_name.split(",")[0].split(cfg.DELIMITER)[1]))
            dst_cid_list.append(int(var_name.split(",")[1].split(cfg.DELIMITER)[1]))
    compute_df["endpoint"] = endpoint_list
    compute_df["svc_name"] = svc_name_list
    compute_df["method"] = method_list
    compute_df["url"] = url_list
    compute_df["src_cid"] = src_cid_list
    compute_df["dst_cid"] = dst_cid_list
    compute_df["call_size"] = 0
    for index, row in compute_df.iterrows():
        # for cg_key in ep_str_callgraph_table:
        logger.debug(f"Set max_load for {row['svc_name']}: {max_capacity_per_service[row['svc_name']][row['src_cid']]}")
        compute_df.at[index, 'max_load'] = max_capacity_per_service[row['svc_name']][row["src_cid"]]
        compute_df.at[index, 'min_load'] = 0
        compute_df.at[index, "min_compute_latency"] = 0
            
            
def get_observed_y(callgraph, load_list, compute_df):
    observed_y = dict()
    for index, row in compute_df.iterrows():
        if row["svc_name"] not in observed_y:
            observed_y[row["svc_name"]] = dict()
        for cg_key in callgraph:
            # if cg_key not in observed_y[row["svc_name"]]:
            observed_y[row["svc_name"]][cg_key] = list()
            for load_dict in load_list: # load_dict = {'A':load_of_callgraph_A, 'B':load_of_callgraph_B}
                slope = get_slope(row['svc_name'], callgraph)
                intercept = 0
                compute_latency = get_compute_latency(load_dict, row["svc_name"], slope, intercept, cg_key, callgraph) # compute_latency is ground truth
                logger.debug(f'svc: {row["svc_name"]}, load_dict: {load_dict}, slope: {slope}, compute_latency: {compute_latency}')
                observed_y[row["svc_name"]][cg_key].append(compute_latency)
            logger.debug(row['svc_name'], cg_key, len(observed_y[row["svc_name"]][cg_key]))
    '''
    observed_y[svc_name][cg_key] = a list of compute_latency
    compute_latency: 
    '''
    return observed_y


# Compute latency prediction using regression model for each load point  
def fill_observed_y(compute_df, load_list, callgraph):
    observed_y = get_observed_y(callgraph, load_list, compute_df)
    for index, row in compute_df.iterrows():
        for target_cg in callgraph:
            compute_df.at[index, "observed_y_"+target_cg] = np.array(observed_y[row["svc_name"]][target_cg])
            
def get_observed_x_df(row_, callgraph):
    data = dict()
    for key in callgraph:
        data["observed_x_"+key] = row_["observed_x_"+key]
    temp_df = pd.DataFrame(
        data=data,
    )
    # X_ = temp_df[["observed_x_A", "observed_x_B"]]
    # logger.debug(temp_df)
    # logger.debug(X_)
    return temp_df

# Deprecated
def learn_latency_function(row, callgraph, key):
    X_ = get_observed_x_df(row, callgraph)
    y_ = row["observed_y_"+key]
    X_train, X_test, y_train, y_test = train_test_split(X_, y_, train_size=0.9, random_state=1)
    reg = get_regression_pipeline(callgraph)
    reg.fit(X_train, y_train)
    
    c_ = reg["linearregression"].coef_
    in_ = reg["linearregression"].intercept_
    y_pred = reg.predict(X_test)
    r2 =  np.round(r2_score(y_test, y_pred),2)
    logger.debug(f'reg: {reg}')
    logger.debug(f'Service {row["svc_name"]}, r2: {r2}, slope: {c_}, intercept: {in_}')

    check_negative_relationship(reg)
    return reg

def fill_latency_function(compute_df, callgraph):
    for index, row in compute_df.iterrows():
        for key in callgraph:        
            reg = learn_latency_function(row, callgraph, key)
            compute_df.at[index, 'latency_function_'+key] = reg
            
            
def fill_observed_x(compute_df,load_list, callgraph):
    for index, row in compute_df.iterrows():
        for key in callgraph:
            load_of_certain_cg = [ld[key] for ld in load_list]
            compute_df.at[index, "observed_x_"+key] = load_of_certain_cg
            
            
def fill_observation_in_compute_df(compute_df, callgraph_table):
    # load_list is a list of {cg_key_A: load_of_callgraph_A, cg_key_B: load_of_callgraph_B}
    load_list = fake_load_gen(callgraph_table)
    fill_observed_x(compute_df, load_list, callgraph_table)
    fill_observed_y(compute_df, load_list, callgraph_table)
    fill_latency_function(compute_df, callgraph_table)
    

def create_compute_df(compute_arc_var_name, ep_str_callgraph_table, coef_dict, max_capacity_per_service):
    logger = logging.getLogger(__name__)
    columns = get_compute_df_column(ep_str_callgraph_table)
    compute_df = pd.DataFrame(columns=columns, index=compute_arc_var_name)
    # try:
    fill_compute_df(compute_df, compute_arc_var_name, ep_str_callgraph_table, max_capacity_per_service)
    # except Exception as e:
        # logger.error(f"!!! ERROR !!! fill_compute_df failed: {type(e).__name__}, {e}")
        # assert False
    for index, row in compute_df.iterrows():
        logger.debug(f'{row["svc_name"]}, {row["endpoint"]}')
        try:
            compute_df.at[index, 'coef'] = coef_dict[row['src_cid']][row["svc_name"]][row['endpoint']]
            # compute_df.at[index, 'latency_function'] = latency_func[row['svc_name']][row['endpoint']]
        except Exception as e:
            logger.error(f"!!! ERROR !!! coef_dict[{row['src_cid']}][{row['svc_name']}][{row['endpoint']}] fill_compute_df failed: {type(e).__name__}, {e}")
    return compute_df

def print_gurobi_var(gurobi_model):
    varInfo = [(v.varName, v.LB, v.UB) for v in gurobi_model.getVars() ]
    df_var = pd.DataFrame(varInfo) # convert to pandas dataframe
    df_var.columns=['Variable Name','LB','UB'] # Add column headers
    num_var = len(df_var)
    if cfg.OUTPUT_WRITE:
        df_var.to_csv(cfg.OUTPUT_DIR+"/variable.csv")
    with pd.option_context('display.max_colwidth', None):
        with pd.option_context('display.max_rows', None):
            # logger.debug(f"len(df_var): {len(df_var)}")
            # logger.debug("df_var")
            df_var.to_csv("variable.csv")
            
def print_gurobi_constraint(gurobi_model):
    constrInfo = [(c.constrName, gurobi_model.getRow(c), c.Sense, c.RHS) for c in gurobi_model.getConstrs() ]
    df_constr = pd.DataFrame(constrInfo)
    df_constr.columns=['Constraint Name','Constraint equation', 'Sense','RHS']
    if cfg.OUTPUT_WRITE:
        df_constr.to_csv(cfg.OUTPUT_DIR+"/constraint.csv")
    with pd.option_context('display.max_colwidth', None):
        with pd.option_context('display.max_rows', None):
            # logger.debug(f"len(df_constr): {len(df_constr)}")
            # logger.debug("df_constr")
            df_constr.to_csv("constraint.csv")

# Deprecated
def check_negative_relationship(reg):
    if cfg.REGRESSOR_DEGREE == 1:
        for i in range(len(reg["linearregression"].coef_)):
            if reg["linearregression"].coef_[i] < 0:
                new_c = np.array([0.])
                reg["linearregression"].coef_[i] = new_c
                logger.warning(f'{cfg.log_prefix} Service {row["svc_name"]}, changed slope {reg["linearregression"].coef_[i]} --> {new_c}, intercept: {in_}')
                assert False
    # if cfg.REGRESSOR_DEGREE == 2:
    #     '''
    #     (X1,X2) transforms to (1, X1, X2, X1^2, X1X2, X2^2)
    #     '''
    #     logger.warning(f'Service {row["svc_name"]}, slope: {reg["linearregression"].coef_} {reg}')
    #     for i in range(len(reg["linearregression"].coef_)):
    #         if reg["linearregression"].coef_[i][1] < 0:
    #             new_c = np.array([0., 0.])
    #             reg["linearregression"].coef_[i] = new_c
    #             logger.warning(f'{cfg.log_prefix} Service {row["svc_name"]}, changed slope {reg["linearregression"].coef_[i]} --> {new_c}, intercept: {in_}')
    #             assert False


'''
HOW TO USE
write "log_timestamp("event_name")" right after the event.
print_timestamp() in the end of the program.
'''
def log_timestamp(event_name):
    timestamp_list.append([event_name, time.time()])
    if len(timestamp_list) > 1:
        dur = round(timestamp_list[-1][1] - timestamp_list[-2][1], 5)
        logger.debug(f"{cfg.log_prefix} Finished, {event_name}, duration,{dur}")


def print_timestamp():
    logger.debug(f"{cfg.log_prefix} ** timestamp_list(ms)")
    for i in range(1, len(timestamp_list)):
        logger.info(f"{cfg.log_prefix} {timestamp_list[i][0]}, {timestamp_list[i][1] - timestamp_list[i-1][1]}")
        
# Deprecated
def print_error(msg):
    exit_time = 5
    logger.error("[ERROR] " + msg)
    logger.error("EXIT PROGRAM in")
    for i in reversed(range(exit_time)) :
        logger.error("{} seconds...".format(i))
        time.sleep(1)
    assert False


def count_cross_cluster_routing(percent_df):
    remote_routing = 0
    local_routing = 0
    for index, row in percent_df.iterrows():
        src_cid = row["src_cid"]
        dst_cid = row["dst_cid"]
        src_svc = row["src"]
        dst_svc = row["dst"]
        if src_cid != NONE_CID and dst_cid != NONE_CID:
            if src_cid != dst_cid:
                remote_routing += row["flow"]
            else:
                local_routing += row["flow"]
    return remote_routing


def is_service_in_callgraph(svc_name, callgraph, key):
    if svc_name in callgraph[key]:
        return True
    return False


def is_service_in_cluster(svc_name, unique_service, cid):
    if svc_name in unique_service[cid]:
        return True
    return False

'''
{ A: 
    { 
        ingress_gw: {0, 1},
        productpage: {0, 1}, 
        details: {0, 1}, 
        reviews: {0, 1}, 
        ratings: {0, 1} 
    },
 B: 
    {
        ingress_gw: {0, 1},
        productpage: {0, 1}, 
        details: {0, 1}, 
        reviews: {0, 1}, 
        ratings: {0, 1} 
    }
}
'''


def get_edge_type(src_node_type, dst_node_type):
    if src_node_type == "-1" or dst_node_type == "-1":
        return "source"
    elif src_node_type == "start" and dst_node_type == "end":
        return "compute"
    else:
        return "network"
    
def is_local_routing(src_cid, dst_cid):
    if src_cid == dst_cid:
        return True
    else:
        return False
        

def get_network_edge_color(src_cid, dst_cid, key=""):
    # if src_cid == NONE_CID or dst_cid == NONE_CID:
    #     return "black"
    if key == "":
        if src_cid == NONE_CID or dst_cid == NONE_CID:
            return "black"
        if src_cid == dst_cid:
            return "black"
        else:
            return "blue"
    else: # key != ""
        if key == "A":
            # return "#6f00ff" # purple
            return "red"
        elif key == "B":
            return "blue" # blue
        else:
            return "purple"

def get_network_edge_style(src_cid, dst_cid):
    if src_cid == NONE_CID or dst_cid == NONE_CID:
        return "filled"
    if src_cid == dst_cid:
        return "filled"
    else:
        return "dashed"
    

def plot_dict_detail(target_dict, cg, g_):
    node_pw = "1"
    edge_pw = "0.5"
    fs = "8"
    edge_fs_0 = "10"
    fn="times bold italic"
    edge_arrowsize="0.5"
    edge_minlen="1"
    for elem in target_dict:
        src = elem[0]
        dst = elem[1]
        src_svc = src.split(cfg.DELIMITER)[0]
        src_cid = int(src.split(cfg.DELIMITER)[1])
        src_node_type = src.split(cfg.DELIMITER)[2]
        dst_svc = dst.split(cfg.DELIMITER)[0]
        dst_cid = int(dst.split(cfg.DELIMITER)[1])
        dst_node_type = dst.split(cfg.DELIMITER)[2]
        g_.node(name=src, label=src_svc[:name_cut], shape='circle', style='filled', fillcolor=node_color_dict[src_cid], penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        g_.node(name=dst, label=dst_svc[:name_cut], shape='circle', style='filled', fillcolor=node_color_dict[dst_cid], penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        if get_edge_type(src_node_type, dst_node_type) == "source":
            edge_color = "black"
        elif get_edge_type(src_node_type, dst_node_type) == "compute":
            edge_color = "gray"
        elif get_edge_type(src_node_type, dst_node_type) == "network":
            edge_color = get_network_edge_color(src_cid, dst_cid)
        else:
            logger.error(f'Wrong edge type: {src_node_type}->{dst_node_type}')
            assert False
        g_.edge(src, dst, penwidth=edge_pw, style="filled", fontsize=edge_fs_0, fontcolor=edge_color, color=edge_color, arrowsize=edge_arrowsize, minlen=edge_minlen)


def plot_full_arc(compute_arc, network_arc, callgraph):
    g_ = graphviz.Digraph()
    plot_dict_detail(compute_arc, callgraph, g_)
    plot_dict_detail(network_arc, callgraph, g_)
    # g_.render(f'{cfg.OUTPUT_DIR}/temp1', view = True)
    g_.render(f'{cfg.OUTPUT_DIR}/temp1')
    # output: call_graph.pdf
    g_
    
    
def plot_dict_wo_compute_edge(target_dict, g_):
    node_pw = "1"
    edge_pw = "0.5"
    fs = "8"
    edge_fs = "10"
    fn="times bold italic"
    edge_arrowsize="0.5"
    edge_minlen="1"
    for elem in target_dict:
        src = elem[0]
        dst = elem[1]
        src_svc = src.split(cfg.DELIMITER)[0]
        dst_svc = dst.split(cfg.DELIMITER)[0]
        # src_node_type = src.split(cfg.DELIMITER)[2]
        # dst_node_type = dst.split(cfg.DELIMITER)[2]
        # src_cid = int(src.split(cfg.DELIMITER)[1])
        # dst_cid = int(dst.split(cfg.DELIMITER)[1])
        src_cid = src.split(cfg.DELIMITER)[1]
        dst_cid = dst.split(cfg.DELIMITER)[1]
        src_node = src_svc+str(src_cid)
        dst_node = dst_svc+str(dst_cid)
        src_node_color = node_color_dict[src_cid]
        dst_node_color = node_color_dict[dst_cid]
        # src_node
        g_.node(name=src_node, label=src_svc[:name_cut], shape='circle', style='filled', fillcolor=src_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        # dst_node
        g_.node(name=dst_node, label=dst_svc[:name_cut], shape='circle', style='filled', fillcolor=dst_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        # # transparent edge for structured plot
        # edge_color = "white" # transparent
        # g_.edge(src_node, dst_node, color=edge_color, penwidth=edge_pw, style="filled", fontsize=edge_fs, fontcolor="black", arrowsize=edge_arrowsize, minlen=edge_minlen)
        

def plot_call_graph_path(callgraph, target_cg_key, unique_service, g_):
    edge_pw = "0.5"
    edge_fs_0 = "10"
    edge_arrowsize="0.5"
    edge_minlen="1"
    for cg_key in callgraph:
        for src_svc, children in callgraph[cg_key].items():
            for dst_svc in children:
                cluster_pair = get_cluster_pair(unique_service)
                for c_pair in cluster_pair:
                    src_cid = c_pair[0]
                    dst_cid = c_pair[1]
                    src_node = src_svc+str(src_cid)
                    dst_node = dst_svc+str(dst_cid)
                    if src_svc in unique_service[src_cid] and dst_svc in unique_service[dst_cid]:
                        if cg_key == target_cg_key:
                            edge_color = get_callgraph_edge_color(cg_key)
                        else:
                            edge_color = "white"
                        g_.edge(src_node, dst_node, color = edge_color, penwidth=edge_pw, style="filled", fontsize=edge_fs_0, fontcolor="black", arrowsize=edge_arrowsize, minlen=edge_minlen)

def get_callgraph_edge_color(cg_key):
    idx = hashlib.md5(b"cg_key")%len(edge_color_list)
    return edge_color_list(idx)

def plot_arc_var_for_callgraph(network_arc, unique_service, callgraph, key):
    g_ = graphviz.Digraph()
    plot_dict_wo_compute_edge(network_arc, g_)
    plot_call_graph_path(callgraph, key, unique_service, g_)
    g_.render(f'{cfg.OUTPUT_DIR}/callgraph-'+key, view = True) # output: call_graph.pdf
    g_
    
    
def plot_callgraph_request_flow(percent_df, network_arc):
    g_ = graphviz.Digraph()
    # plot_dict_wo_compute_edge(network_arc, g_)
    node_pw = "1"
    edge_pw = "0.5"
    fs = "8"
    edge_fs = "10"
    fn="times bold italic"
    edge_arrowsize="0.5"
    edge_minlen="1"
    for index, row in percent_df.iterrows():
        if row["flow"] <= 0 or row["weight"] <= 0:
            continue
        src_cid = row["src_cid"]
        dst_cid = row["dst_cid"]
        src_svc = row["src_svc"]
        dst_svc = row["dst_svc"]
        edge_color = get_network_edge_color(src_cid, dst_cid)
        edge_style = get_network_edge_style(src_cid, dst_cid)
        src_node_color = node_color_dict[src_cid]
        dst_node_color = node_color_dict[dst_cid]
        src_node_name = src_svc+str(src_cid)
        dst_node_name = dst_svc+str(dst_cid)
        # src_node
        g_.node(name=src_node_name, label=src_node_name[:name_cut], shape='circle', style='filled', fillcolor=src_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        # dst_node
        g_.node(name=dst_node_name, label=dst_node_name[:name_cut], shape='circle', style='filled', fillcolor=dst_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        # edge from src_node to dst_node        
        g_.edge(src_node_name, dst_node_name, label=f'{round(row["flow"],1)}({round(row["weight"], 2)})', penwidth=edge_pw, style=edge_style, fontsize=edge_fs, fontcolor=edge_color, color=edge_color, arrowsize=edge_arrowsize, minlen=edge_minlen)
    # result_string = ''.join(cg_key_list)
    # g_.render(f'{cfg.OUTPUT_DIR}/wl_{workload}-cg_{result_string}', view = True)
    g_.render(f'graphviz', view = True)
    g_


def plot_merged_request_flow(concat_df, workload, network_arc):
    g_ = graphviz.Digraph()
    plot_dict_wo_compute_edge(network_arc, g_)
    node_pw = "1"
    edge_pw = "0.5"
    fs = "8"
    edge_fs = "10"
    fn="times bold italic"
    edge_arrowsize="0.5"
    edge_minlen="1"
    weight = dict()
    num_req = dict()
    for index, row in concat_df.iterrows():
        if row["flow"] <= 0 or row["weight"] <= 0:
            continue
        src_cid = int(row["src_cid"])
        dst_cid = int(row["dst_cid"])
        src_svc = row["src"]
        dst_svc = row["dst"]
        edge_color = get_network_edge_color(src_cid, dst_cid)
        edge_style = get_network_edge_style(src_cid, dst_cid)
        src_node_color = node_color_dict[src_cid]
        dst_node_color = node_color_dict[dst_cid]
        src_node_name = src_svc+str(src_cid)
        dst_node_name = dst_svc+str(dst_cid)
        # src_node
        g_.node(name=src_node_name, label=src_svc[:name_cut], shape='circle', style='filled', fillcolor=src_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        # dst_node
        g_.node(name=dst_node_name, label=dst_svc[:name_cut], shape='circle', style='filled', fillcolor=dst_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        # edge from src_node to dst_node        
        g_.edge(src_node_name, dst_node_name, label=f'{row["flow"]}({round(row["weight"], 2)})', penwidth=edge_pw, style=edge_style, fontsize=edge_fs, fontcolor=edge_color, color=edge_color, arrowsize=edge_arrowsize, minlen=edge_minlen)
    g_.render(f'{cfg.OUTPUT_DIR}/wl_{workload}-cg_merged', view = True)
    g_


def is_normal_node(svc_name):
    if svc_name != source_node_name and svc_name != destination_node_name:
        return True
    else:
        return False

def check_network_arc_var_name(net_arc_var):
    for elem in net_arc_var:
        if type(elem) == tuple:
            src_node = elem[0]
            dst_node = elem[1]
        else:
            src_node = elem.split(",")[0]
            dst_node = elem.split(",")[1]
        
        src_svc_name = src_node.split(cfg.DELIMITER)[0]
        dst_svc_name = dst_node.split(cfg.DELIMITER)[0]
        src_cid = src_node.split(cfg.DELIMITER)[1]
        dst_cid = dst_node.split(cfg.DELIMITER)[1]
        src_node_type = src_node.split(cfg.DELIMITER)[2]
        dst_node_type = dst_node.split(cfg.DELIMITER)[2]
        
        if src_svc_name == dst_svc_name:
            logger.error(f'src_svc_name == dst_svc_name, {src_svc_name} == {dst_svc_name}')
            assert False
        # if src_cid == dst_cid:
        #     logger.error(f'src_cid == dst_cid, {src_cid} == {dst_cid}')
        #     assert False
        if is_normal_node(src_svc_name) and src_node_type != "end":
            logger.error(f'{src_node_type} != "end"')
            logger.error(src_node)
            assert False
        if is_normal_node(dst_svc_name) and dst_node_type != "start":
            logger.error(f'{dst_node_type} != "end"')
            logger.error(dst_node)
            assert False


# Deprecated by inter_cluster_latency config in env.txt file. check global_controller.read_config_file function
# def get_network_latency(src_cid, dst_cid):
#     if src_cid == NONE_CID or dst_cid == NONE_CID:
#         return 0
#     if src_cid == dst_cid:
#         return cfg.intra_CLUSTER_NETWORK_LATENCY
#     else:
#         return cfg.INTER_CLUSTER_NETWORK_LATENCY


def get_egress_cost(src, src_cid, dst, dst_cid, callsize_dict):
    if src_cid == dst_cid or src == source_node_name or dst == destination_node_name:
        return 0
    else:
        return cfg.INTER_CLUSTER_EGRESS_COST * callsize_dict[(src,dst)]


def get_end_node_name(svc_name, cid):
    return f'{svc_name}{cfg.DELIMITER}{cid}{cfg.DELIMITER}end'


def get_start_node_name(svc_name, cid):
    return f'{svc_name}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start'


def translate_to_percentage(df_req_flow):
    logger = logging.getLogger(__name__)
    i = 0
    logger.debug(f'translate_to_percentage {i}')
    i+=1
    src_endpoint_list = list()
    dst_endpoint_list = list()
    src_svc_list = list()
    dst_svc_list = list()
    src_cid_list = list()
    dst_cid_list = list()
    flow_list = list()
    src_and_dst_index = list()
    # edge_name_list = list()
    # edge_dict = dict()
    logger.debug(f'translate_to_percentage {i}')
    i+=1
    for index, row in df_req_flow.iterrows():
        logger.debug(f'translate_to_percentage {i}, {row["From"]}, {row["To"]}')
        i+=1
        src_endpoint = row["From"].split(cfg.DELIMITER)[0]
        dst_endpoint = row["To"].split(cfg.DELIMITER)[0]
        # src_cid = int(row["From"].split(cfg.DELIMITER)[1])
        # dst_cid = int(row["To"].split(cfg.DELIMITER)[1])
        src_cid = row["From"].split(cfg.DELIMITER)[1]
        dst_cid = row["To"].split(cfg.DELIMITER)[1]
        src_node_type = row["From"].split(cfg.DELIMITER)[2]
        dst_node_type = row["To"].split(cfg.DELIMITER)[2]
        if src_endpoint == source_node_name or dst_endpoint == destination_node_name or (src_node_type == "end" and dst_node_type == "start"):
            # if src_endpoint != source_node_name:
            #     src_cid = int(src_cid)
            # if dst_endpoint != destination_node_name:
            #     dst_cid = int(dst_cid)
            src_and_dst_index.append((src_endpoint, src_cid, dst_endpoint))
            src_endpoint_list.append(src_endpoint)
            dst_endpoint_list.append(dst_endpoint)
            src_svc_list.append(src_endpoint.split(cfg.ep_del)[0])
            dst_svc_list.append(dst_endpoint.split(cfg.ep_del)[0])
            src_cid_list.append(src_cid)
            dst_cid_list.append(dst_cid)
            flow_list.append(int(math.ceil(row["Flow"])))
            # edge_name = src_endpoint+","+dst_endpoint
            # edge_name_list.append(edge_name)
            # if edge_name not in edge_dict:
            #     edge_dict[edge_name] = list()
            # edge_dict[edge_name].append([src_cid,dst_cid,row["Flow"]])
    logger.debug(f'translate_to_percentage {i}, for loop done')
    i+=1
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
    logger.debug(f'translate_to_percentage {i} created percentage_df')
    i+=1
    percentage_df.index.name = "index_col"
    group_by_sum = percentage_df.groupby(['index_col']).sum()
    logger.debug(group_by_sum)
    logger.debug(f'translate_to_percentage {i} group_by done')
    i+=1
    total_list = list()
    for index, row in percentage_df.iterrows():
        total = group_by_sum.loc[[index]]["flow"].tolist()[0]
        total_list.append(total)
    logger.debug(f'translate_to_percentage {i}')
    i+=1
    percentage_df["total"] = total_list
    weight_list = list()
    for index, row in percentage_df.iterrows():
        try:
            weight_list.append(row['flow']/row['total'])
        except Exception as e:
            weight_list.append(0)
            logger.warning(f'translate_to_percentage Error: {type(e).__name__}, {e}')
    logger.debug(f'translate_to_percentage {i}, calculated weight_list')
    i+=1
    percentage_df["weight"] = weight_list
    # percentage_df = percentage_df.reset_index(drop=True)
    logger.debug(f'translate_to_percentage is done')
    return percentage_df


# 
def print_result_flow(callgraph, aggregated_load):
    for key in callgraph:
        for k, v in aggregated_load[key].items():
            logger.debug(f"var_name: {v.getAttr('VarName').split('[')[0].split('_')[2]}")
            logger.debug(f"type: {v.getAttr('VarName').split('[')[0].split('_')[-1]}")
            logger.debug(f"valie: {v.getAttr('X')}")


def print_all_gurobi_var(gurobi_model, callgraph):
    for var in gurobi_model.getVars():
        logger.debug(f'{var}, {var.x}')


def get_result_latency(gurobi_model, callgraph):
    result_latency = dict()
    for key in callgraph:
        result_latency[key] = dict()
        result_latency[key]["compute"] = 0
        result_latency[key]["network"] = 0
        
    for v in gurobi_model.getVars():
        prefix_var_name = v.getAttr("VarName").split('[')[0]
        if prefix_var_name.split('_')[1] == "latency":
            logger.debug(f'{v}, {v.getAttr("X")}')
            cg_key = prefix_var_name.split('_')[-1]
            which_latency = prefix_var_name.split('_')[0]
            result_latency[cg_key][which_latency] += v.getAttr("X")
    return result_latency


'''
end_to_end_latency modeling
'''


'''
XX callgraph["A"] = {'ingress_gw': ['productpage-v1'],
                    'productpage-v1': ['reviews-v3', 'details-v1'],
                    'reviews-v3': [],
                    'details-v1': []}
                  
XX svc_order["A"] = ['ingress_gw', 'productpage-v1', 'reviews-v3', 'details-v1']

svc_to_cid["A"] = {
    'ingress_gw': [0,1]
    'productpage-v1': [0,1]
    'reviews-v3': [0,1]
    'details-v1': [0,1]
}

all_combination["A"]: [[0,0,0,0], [0,0,0,1], ... ]
'''

## recursive, dfs
# A->B->C
#     ->D
# unpack_list = [[A,B], [B,C], [B,D]]
# unpack_list will have DFS order
def unpack_callgraph_in_dfs_order(callgraph, key, cur_node, unpack_list):
    if len(callgraph[key][cur_node]) == 0:
        return
    for child_node in callgraph[key][cur_node]:
        unpack_list.append([cur_node, child_node])
        unpack_callgraph_in_dfs_order(callgraph, key, child_node, unpack_list)


def is_root(cg, query_node):
    assert query_node in cg
    for svc in cg:
        # If the query node is some node's child, it is not root node.
        if query_node in cg[svc]:
            return False
    return True

def remove_too_many_cross_cluster_routing_path(all_combinations, threshold):
    def count_ccr(path):
        ccr = 0
        for i in range(len(path)-1):
            if path[i] != path[i+1]:
                ccr += 1
        return ccr
    new_all_combinations = list()
    for path in all_combinations:
        if count_ccr(path) <= threshold:
            new_all_combinations.append(path)
        # else:
        #     logger.debug(f'path: {path} has too many cross cluster routing, {count_ccr(path)} > {threshold}')
    return new_all_combinations

'''
callgraph[key][parent_svc] is a list. A list has the order.
1. root node
2. iterate a list of child services of root node
3. dfs 
The svc_order is defined from the start of the search by the root node.
And the order matters in svc_order. 
The order in svc_order MUST be same as the order in combination data structure.
'''
## recursive, dfs (depth first search)
# A->B->C
#     ->D
# svc_order = {cg_key_1: 
#                       {A: 0}, {B: 1}, {C: 2}, {D: 3}
#              }
# svc_order[cg_key_1][A] = 0
# svc_order[cg_key_1][B] = 1
# svc_order[cg_key_1][C] = 2
# svc_order[cg_key_1][D] = 3
def get_dfs_svc_order(callgraph, key, parent_svc, svc_order, idx):
    if len(callgraph[key][parent_svc]) == 0:
        # logger.debug(f'{parent_svc} is leaf')
        svc_order[key][parent_svc] = idx
        return
    svc_order[key][parent_svc] = idx
    for child_svc in callgraph[key][parent_svc]:
        idx += 1
        get_dfs_svc_order(callgraph, key, child_svc, svc_order, idx)


## for loop traverse
def svc_to_cid(svc_order, unique_service):
    svc_to_placement = list()
    for svc in svc_order:
        svc_to_placement.append(list())
    # for i in range(len(svc_order)):
    for svc, idx in svc_order.items():
        for cid in unique_service:
            if svc in unique_service[cid]: # check whether it is in the cluster
                svc_to_placement[idx].append(cid)
    return svc_to_placement

def get_root_status(cg):
    status = {node: True for node in cg}
    for node, children in cg.items():
        for child in children:
            if child in status:
                status[child] = False
    return status

def find_root_node(cg):
    # logger = logging.getLogger(__name__)
    # temp = dict()
    # root_node = list()
    # for parent_node in cg:
    #     temp[parent_node] = "True"
    #     for child_node in cg:
    #         if parent_node in cg[child_node]:
    #             temp[parent_node] = "False"
    #     if temp[parent_node] == "True":
    #         root_node.append(parent_node)
    # if len(root_node) == 0:
    #     logger.debug(f'ERROR: cannot find root node in callgraph')
    #     return False
    # if len(root_node) > 1:
    #     logger.error(f'ERROR: too many root node in callgraph')
    #     logger.error(f"root_node: {root_node}")
    #     logger.error(cg)
    #     return False
    # return root_node[0]
    root_nodes = [node for node, is_root in get_root_status(cg).items() if is_root]
    if len(root_nodes) != 1:
        logging.error(f'ERROR: Invalid root node count in callgraph: {len(root_nodes)}')
        return False
    return root_nodes[0]

    
def create_path(svc_order, comb, unpack_list, callgraph, key):
    # logger.debug('Target path')
    # logger.debug(f'- comb: {comb}')
    assert len(svc_order) == len(comb)
    path = list()
    
    ## Add compute arc to the path
    for svc, cid in zip(svc_order, comb):
        compute_arc_var_name = get_compute_arc_var_name(svc, cid)
        path.append(compute_arc_var_name)
        
    ## Add network arc to the path
    for pair in unpack_list:
        src_svc = pair[0]
        dst_svc = pair[1]
        src_cid = comb[svc_order[src_svc]]
        dst_cid = comb[svc_order[dst_svc]]
        logger.debug(f'Add path: {src_svc},{src_cid} -> {dst_svc},{dst_cid}')
        if is_root(callgraph[key], src_svc):
            network_arc_var_name = get_network_arc_var_name(source_node_name, NONE_CID, src_svc, src_cid)
            path.append(network_arc_var_name)
        network_arc_var_name = get_network_arc_var_name(src_svc, src_cid, dst_svc, dst_cid)
        path.append(network_arc_var_name)
    return path


def merge_callgraph(callgraph):
    merged_callgraph = dict()
    for key in callgraph:
        for parent_svc in callgraph[key]:
            if parent_svc not in merged_callgraph:
                merged_callgraph[parent_svc] = list()
            for child_svc in callgraph[key][parent_svc]:
                if child_svc in merged_callgraph[parent_svc]:
                    continue
                merged_callgraph[parent_svc].append(child_svc)
    return merged_callgraph

def get_root_node_max_rps(root_node_rps):
    root_node_max_rps = dict()
    for cid in root_node_rps:
        for ep in root_node_rps[cid]:
            if ep not in root_node_max_rps:
                root_node_max_rps[ep] = 0
            root_node_max_rps[ep] += root_node_rps[cid][ep]
    return root_node_max_rps


## Being developed not done yet due to some issue
def normalize_weight_wrt_ingress_gw(norm_inout_weight, request_in_out_weight, cur_node, last_weight):
    if request_in_out_weight[cur_node] == {}:
        return
    for child_svc in request_in_out_weight[cur_node]:
        norm_inout_weight[cur_node][child_svc] = last_weight*request_in_out_weight[cur_node][child_svc]
        normalize_weight_wrt_ingress_gw(norm_inout_weight, request_in_out_weight, child_svc, norm_inout_weight[cur_node][child_svc])
        
def norm(request_in_out_weight, demonimator):
    norm_inout_weight = dict()
    for parent in request_in_out_weight:
        norm_inout_weight[parent] = dict()
        for child in request_in_out_weight[parent]:
            norm_inout_weight[parent][child] = 0
    normalize_weight_wrt_ingress_gw(norm_inout_weight, request_in_out_weight, demonimator, 1)
    return norm_inout_weight
    
def merge(request_in_out_weight, norm_inout_weight, max_load):
    merged_in_out_weight = dict()
    for key in norm_inout_weight:
        for parent_svc in norm_inout_weight[key]:
            if parent_svc not in merged_in_out_weight:
                merged_in_out_weight[parent_svc] = dict()
            for child_svc in norm_inout_weight[key][parent_svc]:
                if child_svc in merged_in_out_weight[parent_svc]:
                    continue
                temp = request_in_out_weight[key][parent_svc][child_svc]*(max_load[key]/sum(max_load.values()))
                # logger.debug(f'merged_in_out_weight[{parent_svc}][{child_svc}] += {request_in_out_weight[key][parent_svc][child_svc]}*({max_load[key]}/{sum(max_load.values())})')
                for other_cg_key in norm_inout_weight:
                    if parent_svc in norm_inout_weight[other_cg_key] and child_svc in norm_inout_weight[other_cg_key][parent_svc] and other_cg_key != key:
                        temp += request_in_out_weight[other_cg_key][parent_svc][child_svc]*(max_load[other_cg_key]/sum(max_load.values()))
                        # logger.debug(f'merged_in_out_weight[{parent_svc}][{child_svc}] += {request_in_out_weight[other_cg_key][parent_svc][child_svc]}*({max_load[other_cg_key]}/{sum(max_load.values())})')
                merged_in_out_weight[parent_svc][child_svc] = temp
    return merged_in_out_weight