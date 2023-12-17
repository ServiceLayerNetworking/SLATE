import config as cfg
from global_controller import app
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


random.seed(1234)

timestamp_list = list()
source_node_name = "SOURCE"
destination_node_name = "DESTINATION"
NONE_CID = -1
NONE_TYPE = "-1"
source_node_fullname = f'{source_node_name}{cfg.DELIMITER}{NONE_CID}{cfg.DELIMITER}{NONE_CID}'
destination_node_fullname = f'{destination_node_name}{cfg.DELIMITER}{NONE_CID}{cfg.DELIMITER}{NONE_CID}'


def calculate_depth(graph, node):
    if node not in graph or not graph[node]:
        print(f"leaf node: {node}, depth: 1")
        return 1
    children = graph[node]
    child_depths = [calculate_depth(graph, child) for child in children]
    return 1 + max(child_depths)


def get_depth(callgraph, key, dep_d, cur_node, cur_dep):
    dep_d[key][cur_node] = cur_dep
    if len(callgraph[key][cur_node]) == 0:
        return
    cur_dep += 1
    for svc in callgraph[key][cur_node]:
        get_depth(callgraph, key, dep_d, svc, cur_dep)
    # if key not in callgraph:
    #     print(f'Wrong key: {key}')
    #     assert False
    # if key not in dep_d:
    #     dep_d[key] = dict()
    # for svc in callgraph[key]:
    #     if svc not in dep_d:
    #         dep_d[svc] = dict()
    #     if svc == root_svc:
    #         dep_d[key][svc] = 1
    #     else:
    #         dep_d[key][svc] = dep_d[key][root_svc] + 1
    #     get_depth(callgraph, svc, dep_d, root_svc)


def get_depth_dict(callgraph):
    depth_dict = dict()
    for key in callgraph:
        root_svc = find_root_node(callgraph, key)
        if key not in depth_dict:
            depth_dict[key] = dict()
        get_depth(callgraph, key, depth_dict, root_svc, 0)
    return depth_dict


def get_callsize_dict(callgraph, depth_dict):
    callsize_dict = dict()
    for key in callgraph:
        for parent_svc, children in callgraph[key].items():
            for child_svc in children:
                assert depth_dict[key][parent_svc] < depth_dict[key][child_svc]
                callsize_dict[(parent_svc,child_svc)] = (depth_dict[key][parent_svc]+1)
    return callsize_dict


def calc_max_load_of_each_callgraph(callgraph, maxload):
    per_svc_max_load = dict()
    for key in callgraph:
        for svc in callgraph[key]:
            if svc not in per_svc_max_load:
                per_svc_max_load[svc] = dict()
            per_svc_max_load[svc][key] = maxload[key]
            
    for key in callgraph:
        for svc in per_svc_max_load:
            if svc not in callgraph[key]:
                per_svc_max_load[svc][key] = 0
    return per_svc_max_load


def get_compute_arc_var_name(svc_name, cid):
    return (f'{svc_name}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start', f'{svc_name}{cfg.DELIMITER}{cid}{cfg.DELIMITER}end') # tuple
    # return f'{svc_name}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start,{svc_name}{cfg.DELIMITER}{cid}{cfg.DELIMITER}end' # string
    

def create_compute_arc_var_name(unique_service):
    compute_arc_var_name = list()
    for cid in unique_service:
        for svc_name in unique_service[cid]:
            compute_arc_var_name.append(get_compute_arc_var_name(svc_name, cid))
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
        print(f'Wrong var_tuple: {var_tuple}')
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
        print(f'Wrong length of load({len(load)}) != slope({len(slope)})')
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


# ## Deprecated
# def gen_fake_data(compute_df, callgraph, y_axis_target_cg_key):
#     # Why there is only one intercept and slope have mulitple values?
#     # because one regression function has one intercept but can have multiple coefficients which is slope in this case.
#     slope_dict = dict()
#     for index, row in compute_df.iterrows():
#         if row["svc_name"] not in slope_dict:
#             slope_dict[row['svc_name']] = dict()
#         # TODO: Currently all callgraphs will use the same slope.
#         # We need a list of slopes whose length is equal to the number of callgraph
#         for key in callgraph:
#             for x_feat_key in callgraph:
#                 slope_dict[row['svc_name']][key] = [get_slope(row["svc_name"], y_axis_target_cg_key)] * len(callgraph)
    
#     observed_y_of_target_cg = list()
#     for index, row in compute_df.iterrows():
#         for key in callgraph:
#             for ld in load_list:
#                 observed_y_of_target_cg.append(create_compute_time(y_axis_target_cg_key, ld, slope_dict['svc_name'][key], intercept_=0))
#         # print(f'** cid,{row["src_cid"]}, service,{row["svc_name"]}, degree({cfg.REGRESSOR_DEGREE}), slope({slope_dict['svc_name']}), intercept({intercept})')
#         assert len(load_list) == len(observed_y_of_target_cg)
#         # If you want to use polynomial regression, you need to reshape it to (-1, 1)
#         # compute_df.at[index, "observed_x"] = np.array(load_list).reshape(-1, 1)
#         compute_df.at[index, "observed_y_of_target_cg_"+y_axis_target_cg_key] = np.array(observed_y_of_target_cg)
#         for key in callgraph:
#             # requests from different callgraph have different latency function
#             load_of_certain_cg = [ld[key] for ld in load_list]
#             compute_df.at[index, "observed_x_"+key] = np.array(load_of_certain_cg)
#     # return compute_df


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


def get_network_arc_var_name(src_svc, src_cid, dst_svc, dst_cid):
    assert src_svc != dst_svc
    if src_cid == NONE_CID:
        if src_svc != source_node_name:
            print(f'Wrong src_svc for NONE_CID:  {src_svc}, {src_cid}')
            assert False
        return (f'{source_node_fullname}', f'{dst_svc}{cfg.DELIMITER}{dst_cid}{cfg.DELIMITER}start')
    assert dst_cid != NONE_CID
    return (f'{src_svc}{cfg.DELIMITER}{src_cid}{cfg.DELIMITER}end',f'{dst_svc}{cfg.DELIMITER}{dst_cid}{cfg.DELIMITER}start') # tuple


def is_X_child_of_Y(X_svc, Y_svc, callgraph):
    for key in callgraph:
        if Y_svc in callgraph[key]:
            if X_svc in callgraph[key][Y_svc]:
                return True
    return False


def get_cluster_pair(unique_service):
    cid_list = list(range(len(unique_service)))
    cluster_pair = list(itertools.product(cid_list, cid_list))
    return cluster_pair
    

def create_network_arc_var_name(unique_service, callgraph):
    network_arc_var_name = list()
    cluster_pair = get_cluster_pair(unique_service)
    print("cluster_pair: ", cluster_pair) # [(0, 0), (0, 1), (1, 0), (1, 1)]
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
    print(temp)
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


def is_ingress_gw(target_svc, callgraph):
    for key in callgraph:
        for parent_svc in callgraph[key]:
            if target_svc in callgraph[key][parent_svc]:
                # print(f'{target_svc} is NOT ingress_gw')
                return False
    # print(f'{target_svc} is ingress_gw')
    return True


def get_compute_df_column(callgraph):
    columns = ["svc_name", "src_cid", "dst_cid", "call_size"]
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
        columns.append("min_compute_latency_"+key)
    return columns


def get_observed_y(callgraph, load_list, compute_df):
    obs_y = dict()
    for index, row in compute_df.iterrows():
        if row["svc_name"] not in obs_y:
            obs_y[row["svc_name"]] = dict()
        for target_cg in callgraph:
            # if target_cg not in obs_y[row["svc_name"]]:
            obs_y[row["svc_name"]][target_cg] = list()
            for load_dict in load_list: # load_dict = {'A':load_of_callgraph_A, 'B':load_of_callgraph_B}
                slope = get_slope(row['svc_name'], callgraph)
                intercept = 0
                compute_latency = get_compute_latency(load_dict, row["svc_name"], slope, intercept, target_cg, callgraph) # compute_latency is ground truth
                print(f'svc: {row["svc_name"]}, load_dict: {load_dict}, slope: {slope}, compute_latency: {compute_latency}')
                obs_y[row["svc_name"]][target_cg].append(compute_latency)
            print(row['svc_name'], target_cg, len(obs_y[row["svc_name"]][target_cg]))
    return obs_y

# Compute latency prediction using regression model for each load point  
def fill_observed_y(compute_df, observed_y, callgraph):
    for index, row in compute_df.iterrows():
        for target_cg in callgraph:
            compute_df.at[index, "observed_y_"+target_cg] = np.array(observed_y[row["svc_name"]][target_cg])
            
def get_regression_pipeline(callgraph):
    numeric_features = list()
    for key in callgraph:
        numeric_features.append("observed_x_"+key)
    feat_transform = make_column_transformer(
        # (StandardScaler(), numeric_featuress),
        ('passthrough', numeric_features),
        verbose_feature_names_out=False,
        remainder='drop'
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
    return reg

def get_observed_x_df(row_, callgraph):
    data = dict()
    for key in callgraph:
        data["observed_x_"+key] = row_["observed_x_"+key]
    print(data)
    temp_df = pd.DataFrame(
        data=data,
    )
    # X_ = temp_df[["observed_x_A", "observed_x_B"]]
    # display(temp_df)
    # display(X_)
    return temp_df

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
    print(f'reg: {reg}')
    print(f'Service {row["svc_name"]}, r2: {r2}, slope: {c_}, intercept: {in_}')

    check_negative_relationship(reg)
    return reg
    

def fill_compute_df(compute_df, compute_arc_var_name, callgraph, callsize_dict, NUM_REQUESTS, load_list, MAX_LOAD):
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
    compute_df["call_size"] = 0
    per_svc_max_load = calc_max_load_of_each_callgraph(callgraph, MAX_LOAD)
    for index, row in compute_df.iterrows():
        for key in callgraph:
            compute_df.at[index, 'max_load_'+key] = per_svc_max_load[row["svc_name"]][key]
            compute_df.at[index, 'min_load_'+key] = 0
            compute_df.at[index, "min_compute_latency_"+key] = 0
            load_of_certain_cg = [ld[key] for ld in load_list]
            compute_df.at[index, "observed_x_"+key] = load_of_certain_cg
            
    observed_y = get_observed_y(callgraph, load_list, compute_df)
    fill_observed_y(compute_df, observed_y, callgraph)
    
    for index, row in compute_df.iterrows():
        for key in callgraph:        
            reg = learn_latency_function(row, callgraph, key)
            compute_df.at[index, 'latency_function_'+key] = reg
    

def create_compute_df(unique_service, callgraph, callsize_dict, NUM_REQUESTS, MAX_LOAD):
    compute_arc_var_name = create_compute_arc_var_name(unique_service)
    check_compute_arc_var_name(compute_arc_var_name)
    columns = get_compute_df_column(callgraph)
    compute_df = pd.DataFrame(columns=columns, index=compute_arc_var_name)
    load_list = fake_load_gen(callgraph)
    fill_compute_df(compute_df, compute_arc_var_name, callgraph, callsize_dict, NUM_REQUESTS, load_list, MAX_LOAD)
    return compute_df


def check_negative_relationship(reg):
    if cfg.REGRESSOR_DEGREE == 1:
        for i in range(len(reg["linearregression"].coef_)):
            if reg["linearregression"].coef_[i] < 0:
                new_c = np.array([0.])
                reg["linearregression"].coef_[i] = new_c
                print(f'{cfg.log_prefix} Service {row["svc_name"]}, changed slope {reg["linearregression"].coef_[i]} --> {new_c}, intercept: {in_}')
                assert False
    # if cfg.REGRESSOR_DEGREE == 2:
    #     '''
    #     (X1,X2) transforms to (1, X1, X2, X1^2, X1X2, X2^2)
    #     '''
    #     print(f'Service {row["svc_name"]}, slope: {reg["linearregression"].coef_} {reg}')
    #     for i in range(len(reg["linearregression"].coef_)):
    #         if reg["linearregression"].coef_[i][1] < 0:
    #             new_c = np.array([0., 0.])
    #             reg["linearregression"].coef_[i] = new_c
    #             print(f'{cfg.log_prefix} Service {row["svc_name"]}, changed slope {reg["linearregression"].coef_[i]} --> {new_c}, intercept: {in_}')
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
        app.logger.debug(f"{cfg.log_prefix} Finished, {event_name}, duration,{dur}")


def print_timestamp():
    app.logger.info(f"{cfg.log_prefix} ** timestamp_list(ms)")
    for i in range(1, len(timestamp_list)):
        app.logger.info(f"{cfg.log_prefix} {timestamp_list[i][0]}, {timestamp_list[i][1] - timestamp_list[i-1][1]}")
        
        
def print_error(msg):
    exit_time = 5
    print("[ERROR] " + msg)
    print("EXIT PROGRAM in")
    for i in reversed(range(exit_time)) :
        print("{} seconds...".format(i))
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
    
def get_node_color(cid):
    if cid == NONE_CID:
        return "gray"
    # yellow, pink, blue, green
    node_color = ["#FFBF00", "#ff6375", "#6973fa", "#AFE1AF"]
    if type(cid) != type(1):
        print(f'Wrong type of cid: {type(cid)}, {cid}')
    return node_color[cid]

    
def get_callgraph_edge_color(key):
    edge_color_dict = {"A": "red", "B": "blue", "C": "green", "D": "yellow"}
    return edge_color_dict[key]


def plot_dict_detail(target_dict, cg, g_):
    node_pw = "1"
    edge_pw = "0.5"
    fs = "8"
    edge_fs_0 = "10"
    fn="times bold italic"
    edge_arrowsize="0.5"
    edge_minlen="1"
    node_color = ["#FFBF00", "#ff6375", "#6973fa", "#AFE1AF"] # yellow, pink, blue, green
    name_cut = 6
    for elem in target_dict:
        src = elem[0]
        dst = elem[1]
        src_svc = src.split(cfg.DELIMITER)[0]
        src_cid = int(src.split(cfg.DELIMITER)[1])
        src_node_type = src.split(cfg.DELIMITER)[2]
        dst_svc = dst.split(cfg.DELIMITER)[0]
        dst_cid = int(dst.split(cfg.DELIMITER)[1])
        dst_node_type = dst.split(cfg.DELIMITER)[2]
        g_.node(name=src, label=src_svc[:name_cut], shape='circle', style='filled', fillcolor=node_color[src_cid], penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        g_.node(name=dst, label=dst_svc[:name_cut], shape='circle', style='filled', fillcolor=node_color[dst_cid], penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        if get_edge_type(src_node_type, dst_node_type) == "source":
            edge_color = "black"
        elif get_edge_type(src_node_type, dst_node_type) == "compute":
            edge_color = "gray"
        elif get_edge_type(src_node_type, dst_node_type) == "network":
            edge_color = get_network_edge_color(src_cid, dst_cid)
        else:
            print(f'Wrong edge type: {src_node_type}->{dst_node_type}')
            assert False
        g_.edge(src, dst, penwidth=edge_pw, style="filled", fontsize=edge_fs_0, fontcolor=edge_color, color=edge_color, arrowsize=edge_arrowsize, minlen=edge_minlen)


def plot_full_arc(compute_arc, network_arc, callgraph):
    g_ = graphviz.Digraph()
    plot_dict_detail(compute_arc, callgraph, g_)
    plot_dict_detail(network_arc, callgraph, g_)
    g_.render(f'{cfg.OUTPUT_DIR}/temp1', view = True)
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
    name_cut = 6
    for elem in target_dict:
        src = elem[0]
        dst = elem[1]
        src_svc = src.split(cfg.DELIMITER)[0]
        src_cid = int(src.split(cfg.DELIMITER)[1])
        # src_node_type = src.split(cfg.DELIMITER)[2]
        dst_svc = dst.split(cfg.DELIMITER)[0]
        dst_cid = int(dst.split(cfg.DELIMITER)[1])
        # dst_node_type = dst.split(cfg.DELIMITER)[2]
        src_node = src_svc+str(src_cid)
        dst_node = dst_svc+str(dst_cid)
        src_node_color = get_node_color(src_cid)
        dst_node_color = get_node_color(dst_cid)
        edge_color = "white" # transparent
        # src_node
        g_.node(name=src_node, label=src_svc[:name_cut], shape='circle', style='filled', fillcolor=src_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        # dst_node
        g_.node(name=dst_node, label=dst_svc[:name_cut], shape='circle', style='filled', fillcolor=dst_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        # # transparent edge for structured plot
        # g_.edge(src_node, dst_node, color=edge_color, penwidth=edge_pw, style="filled", fontsize=edge_fs, fontcolor="black", arrowsize=edge_arrowsize, minlen=edge_minlen)
        

def plot_call_graph_path(callgraph, target_key, unique_service, g_):
    edge_pw = "0.5"
    edge_fs_0 = "10"
    edge_arrowsize="0.5"
    edge_minlen="1"
    for key in callgraph:
        for src_svc, children in callgraph[key].items():
            for dst_svc in children:
                cluster_pair = get_cluster_pair(unique_service)
                for c_pair in cluster_pair:
                    src_cid = c_pair[0]
                    dst_cid = c_pair[1]
                    src_node = src_svc+str(src_cid)
                    dst_node = dst_svc+str(dst_cid)
                    if src_svc in unique_service[src_cid] and dst_svc in unique_service[dst_cid]:
                        if key == target_key:
                            edge_color = get_callgraph_edge_color(key)
                        else:
                            edge_color = "white"
                        g_.edge(src_node, dst_node, color = edge_color, penwidth=edge_pw, style="filled", fontsize=edge_fs_0, fontcolor="black", arrowsize=edge_arrowsize, minlen=edge_minlen)
    
    
def plot_arc_var_for_callgraph(network_arc, unique_service, callgraph, key):
    g_ = graphviz.Digraph()
    plot_dict_wo_compute_edge(network_arc, g_)
    plot_call_graph_path(callgraph, key, unique_service, g_)
    g_.render(f'{cfg.OUTPUT_DIR}/callgraph-'+key, view = True) # output: call_graph.pdf
    g_
    
    
def plot_callgraph_request_flow(percent_df, cg_key_list, workload, network_arc):
    g_ = graphviz.Digraph()
    plot_dict_wo_compute_edge(network_arc, g_)
    node_pw = "1"
    edge_pw = "0.5"
    fs = "8"
    edge_fs = "10"
    fn="times bold italic"
    edge_arrowsize="0.5"
    edge_minlen="1"
    name_cut = 6
    for cg_key in cg_key_list:
        for index, row in percent_df[cg_key].iterrows():
            if row["flow"] <= 0 or row["weight"] <= 0:
                continue
            src_cid = row["src_cid"]
            dst_cid = row["dst_cid"]
            src_svc = row["src"]
            dst_svc = row["dst"]
            edge_color = get_network_edge_color(src_cid, dst_cid, cg_key)
            edge_style = get_network_edge_style(src_cid, dst_cid)
            src_node_color = get_node_color(src_cid)
            dst_node_color = get_node_color(dst_cid)
            src_node_name = src_svc+str(src_cid)
            dst_node_name = dst_svc+str(dst_cid)
            # src_node
            g_.node(name=src_node_name, label=src_svc[:name_cut], shape='circle', style='filled', fillcolor=src_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
            # dst_node
            g_.node(name=dst_node_name, label=dst_svc[:name_cut], shape='circle', style='filled', fillcolor=dst_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
            # edge from src_node to dst_node        
            g_.edge(src_node_name, dst_node_name, label=f'{round(row["flow"],1)}({round(row["weight"], 2)})', penwidth=edge_pw, style=edge_style, fontsize=edge_fs, fontcolor=edge_color, color=edge_color, arrowsize=edge_arrowsize, minlen=edge_minlen)
    result_string = ''.join(cg_key_list)
    g_.render(f'{cfg.OUTPUT_DIR}/wl_{workload}-cg_{result_string}', view = True)
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
    name_cut = 6
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
        src_node_color = get_node_color(src_cid)
        dst_node_color = get_node_color(dst_cid)
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
            print(f'src_svc_name == dst_svc_name, {src_svc_name} == {dst_svc_name}')
            assert False
        # if src_cid == dst_cid:
        #     print(f'src_cid == dst_cid, {src_cid} == {dst_cid}')
        #     assert False
        if is_normal_node(src_svc_name) and src_node_type != "end":
            print(f'{src_node_type} != "end"')
            print(src_node)
            assert False
        if is_normal_node(dst_svc_name) and dst_node_type != "start":
            print(f'{dst_node_type} != "end"')
            print(dst_node)
            assert False


def get_network_latency(src_cid, dst_cid):
    if src_cid == NONE_CID or dst_cid == NONE_CID:
        return 0
    if src_cid == dst_cid:
        return cfg.INTRA_CLUTER_RTT
    else:
        return cfg.INTER_CLUSTER_RTT


def get_egress_cost(src_cid, src_svc, dst_svc, dst_cid, callsize_dict):
    if src_cid == dst_cid or src_svc == source_node_name or dst_svc == destination_node_name:
        return 0
    else:
        return cfg.INTER_CLUSTER_EGRESS_COST * callsize_dict[(src_svc,dst_svc)]


def end_node_name(svc_name, cid):
    return f'{svc_name}{cfg.DELIMITER}{cid}{cfg.DELIMITER}end'


def start_node_name(svc_name, cid):
    return f'{svc_name}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start'


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
        src_svc = row["From"].split(cfg.DELIMITER)[0]
        dst_svc = row["To"].split(cfg.DELIMITER)[0]
        src_cid = int(row["From"].split(cfg.DELIMITER)[1])
        dst_cid = int(row["To"].split(cfg.DELIMITER)[1])
        src_node_type = row["From"].split(cfg.DELIMITER)[2]
        dst_node_type = row["To"].split(cfg.DELIMITER)[2]
        if src_svc == source_node_name or dst_svc == destination_node_name or (src_node_type == "end" and dst_node_type == "start"):
            if src_svc != source_node_name:
                src_cid = int(src_cid)
            if dst_svc != destination_node_name:
                dst_cid = int(dst_cid)
            src_and_dst_index.append((src_svc, src_cid, dst_svc))
            src_list.append(src_svc)
            dst_list.append(dst_svc)
            src_cid_list.append(src_cid)
            dst_cid_list.append(dst_cid)
            flow_list.append(int(math.ceil(row["Flow"])))
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
    if cfg.DISPLAY:
        display(group_by_sum)
    
    total_list = list()
    for index, row in percentage_df.iterrows():
        total = group_by_sum.loc[[index]]["flow"].tolist()[0]
        total_list.append(total)
    percentage_df["total"] = total_list
    weight_list = list()
    for index, row in percentage_df.iterrows():
        try:
            weight_list.append(row['flow']/row['total'])
        except Exception as e:
            weight_list.append(0)
    percentage_df["weight"] = weight_list
    return percentage_df


def print_result_flow(callgraph, aggregated_load):
    for key in callgraph:
        for k, v in aggregated_load[key].items():
            print(f"var_name: {v.getAttr('VarName').split('[')[0].split('_')[2]}")
            print(f"type: {v.getAttr('VarName').split('[')[0].split('_')[-1]}")
            print(f"valie: {v.getAttr('X')}")


def print_all_gurobi_var(gurobi_model, callgraph):
    for var in gurobi_model.getVars():
        print(f'{var}, {var.x}')


def get_result_latency(gurobi_model, callgraph):
    result_latency = dict()
    for key in callgraph:
        result_latency[key] = dict()
        result_latency[key]["compute"] = 0
        result_latency[key]["network"] = 0
        
    for v in gurobi_model.getVars():
        prefix_var_name = v.getAttr("VarName").split('[')[0]
        if prefix_var_name.split('_')[1] == "latency":
            print(f'{v}, {v.getAttr("X")}')
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
def unpack_callgraph(callgraph, key, cur_node, unpack_list):
    if len(callgraph[key][cur_node]) == 0:
        return
    for child_node in callgraph[key][cur_node]:
        unpack_list.append([cur_node, child_node])
        unpack_callgraph(callgraph, key, child_node, unpack_list)


def is_root(callgraph, key, query_node):
    assert query_node in callgraph[key]
    for svc in callgraph[key]:
        # If the query node is some node's child, it is not root node.
        if query_node in callgraph[key][svc]:
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
        #     print(f'path: {path} has too many cross cluster routing, {count_ccr(path)} > {threshold}')
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
def get_svc_order(callgraph, key, parent_svc, svc_order, idx):
    if len(callgraph[key][parent_svc]) == 0:
        # print(f'{parent_svc} is leaf')
        svc_order[key][parent_svc] = idx
        return
    svc_order[key][parent_svc] = idx
    for child_svc in callgraph[key][parent_svc]:
        idx += 1
        get_svc_order(callgraph, key, child_svc, svc_order, idx)


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

def find_root_node(callgraph, key):
    for svc in callgraph[key]:
        for child_svc in callgraph[key][svc]:
            if svc in callgraph[key][child_svc]:
                break
        return svc
    print(f'ERROR: cannot find root node in callgraph[{key}]')
    assert False
    
def create_path(svc_order, comb, unpack_list, callgraph, key):
    # print('Target path')
    # print(f'- comb: {comb}')
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
        print(f'Add path: {src_svc},{src_cid} -> {dst_svc},{dst_cid}')
        if is_root(callgraph, key, src_svc):
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

def get_max_load(num_requests):
    max_load = dict()
    for cid in range(len(num_requests)):
        for request_type in num_requests[cid]:
            if request_type not in max_load:
                max_load[request_type] = 0
            max_load[request_type] += num_requests[cid][request_type]
    return max_load

def norm(in_out_weight):
    def normalize_weight_wrt_ingress_gw(norm_inout_weight_, in_out_weight_, cur_node, last_weight):
        if in_out_weight_[cur_node] == {}:
            return
        for child_svc in in_out_weight_[cur_node]:
            norm_inout_weight_[cur_node][child_svc] = last_weight*in_out_weight_[cur_node][child_svc]
            normalize_weight_wrt_ingress_gw(norm_inout_weight_, in_out_weight_, child_svc, norm_inout_weight_[cur_node][child_svc])
            
    norm_inout_weight = dict()
    for parent_svc in in_out_weight:
        norm_inout_weight[parent_svc] = dict()
        for child_svc in in_out_weight[parent_svc]:
            norm_inout_weight[parent_svc][child_svc] = 0
    normalize_weight_wrt_ingress_gw(norm_inout_weight, in_out_weight, "ingress_gw", 1)
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
                # print(f'merged_in_out_weight[{parent_svc}][{child_svc}] += {request_in_out_weight[key][parent_svc][child_svc]}*({max_load[key]}/{sum(max_load.values())})')
                for other_cg_key in norm_inout_weight:
                    if parent_svc in norm_inout_weight[other_cg_key] and child_svc in norm_inout_weight[other_cg_key][parent_svc] and other_cg_key != key:
                        temp += request_in_out_weight[other_cg_key][parent_svc][child_svc]*(max_load[other_cg_key]/sum(max_load.values()))
                        # print(f'merged_in_out_weight[{parent_svc}][{child_svc}] += {request_in_out_weight[other_cg_key][parent_svc][child_svc]}*({max_load[other_cg_key]}/{sum(max_load.values())})')
                merged_in_out_weight[parent_svc][child_svc] = temp
    return merged_in_out_weight