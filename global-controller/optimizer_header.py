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

timestamp_list = list()
source_node_name = "SOURCE"
destination_node_name = "DESTINATION"
NONE_CID = -1
source_node_fullname = f'{source_node_name}{cfg.DELIMITER}{NONE_CID}{cfg.DELIMITER}{NONE_CID}'
destination_node_fullname = f'{destination_node_name}{cfg.DELIMITER}{NONE_CID}{cfg.DELIMITER}{NONE_CID}'


def calculate_depth(graph, node):
    if node not in graph or not graph[node]:
        print(f"leaf node: {node}, depth: 1")
        return 1
    children = graph[node]
    child_depths = [calculate_depth(graph, child) for child in children]
    return 1 + max(child_depths)

def graph_depth(graph, depth_dict):
    max_depth = 0
    for node in graph:
        node_depth = calculate_depth(graph, node)
        depth_dict[node] = node_depth
        max_depth = max(max_depth, node_depth)
    return depth_dict


def calc_max_load_of_each_callgraph(callgraph, maxload):
    per_svc_max_load = dict()
    for key in callgraph:
        for parent_svc, children in callgraph[key].items():
            if parent_svc not in per_svc_max_load:
                per_svc_max_load[parent_svc] = dict()
            per_svc_max_load[parent_svc][key] = maxload[key]
            
    for key in callgraph:
        for svc, ml in per_svc_max_load.items():
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


def gen_fake_data(compute_df, callgraph):
    def latency(x_list, s_list, ic):
        ret = 0
        for x, s, in zip(x_list, s_list):
            ret += pow(x, cfg.REGRESSOR_DEGREE)*s
        lat = ret + ic
        print(lat)
        return lat
    
    num_data_point = 50
    load_ = list(np.arange(0,num_data_point))
    for index, row in compute_df.iterrows():
        compute_latency = list()
        slope_list = [zlib.adler32(row["svc_name"].encode('utf-8'))%5+1]*len(callgraph)
        intercept = 10
        for j in range(num_data_point):
            # NOTE: there is always one compute latency per service that we want to figure out
            lat = latency([load_[j], load_[j]], slope_list, intercept)
            compute_latency.append(lat)
        print(f'** cid,{row["src_cid"]}, service,{row["svc_name"]}, degree({cfg.REGRESSOR_DEGREE}), slope({slope_list}), intercept({intercept})')
        assert len(load_) == len(compute_latency)
        # If you want to use polynomial regression, you need to reshape it to (-1, 1)
        # compute_df.at[index, "observed_x"] = np.array(load_).reshape(-1, 1)
        compute_df.at[index, "observed_y"] = np.array(compute_latency)
        for key in callgraph:
            # requests from different callgraph have different latency function
            compute_df.at[index, "observed_x_"+key] = np.array(load_)
    # return compute_df


def plot_latency_function_3d(compute_df):
    idx = 0
    ylim = 0
    num_subplot_row = len(compute_df["src_cid"].unique())
    num_subplot_col = len(compute_df["svc_name"].unique())
    # fig, axs = plt.subplots(num_subplot_row, num_subplot_col, figsize=(16,6))
    
    fig = plt.figure()
    fig.tight_layout()
    for index, row in compute_df.iterrows():
        temp_df = pd.DataFrame(
            data={
                "observed_x_A": row["observed_x_A"],
                "observed_x_B": row["observed_x_B"],
                "observed_y": row["observed_y"],
            }
        )
        X_ = temp_df[["observed_x_A", "observed_x_B"]]
        row_idx = int(idx/num_subplot_col)
        col_idx = idx%num_subplot_col
        ax = fig.add_subplot(100 + (row_idx+1)*10 + (col_idx+1), projection='3d')
        ax.scatter(row["observed_x_A"], row["observed_x_B"], row["observed_y"], c='r', marker='o', label="observation", alpha=0.1)
        ylim = max(ylim, max(row["observed_y"]), max(row["latency_function"].predict(X_)))
        # axs[row_idx][col_idx].legend()
        # axs[row_idx][col_idx].set_title(index[0])
        # if row_idx == num_subplot_row-1:
        #     axs[row_idx][col_idx].set_xlabel("ld")
        # if col_idx == 0:
        #     axs[row_idx][col_idx].set_ylabel("Compute time")
        # idx += 1

    
def plot_latency_function_2d(compute_df):
    idx = 0
    ylim = 0
    num_subplot_row = len(compute_df["src_cid"].unique())
    num_subplot_col = len(compute_df["svc_name"].unique())
    fig, axs = plt.subplots(num_subplot_row, num_subplot_col, figsize=(16,6))
    fig.tight_layout()
    for index, row in compute_df.iterrows():
        temp_df = pd.DataFrame(
            data={
                "observed_x_A": row["observed_x_A"],
                "observed_x_B": row["observed_x_B"],
                "observed_y": row["observed_y"],
            }
        )
        X = temp_df[["observed_x_A", "observed_x_B"]]
        row_idx = int(idx/num_subplot_col)
        col_idx = idx%num_subplot_col
        axs[row_idx][col_idx].plot(row["observed_x_A"], row["observed_y"], 'ro', label="observation", alpha=0.1)
        axs[row_idx][col_idx].plot(row["observed_x_A"], row["latency_function"].predict(X), 'bo', label="prediction", alpha=0.1)
        ylim = max(ylim, max(row["observed_y"]), max(row["latency_function"].predict(X)))
        axs[row_idx][col_idx].legend()
        axs[row_idx][col_idx].set_title(index[0])
        if row_idx == num_subplot_row-1:
            axs[row_idx][col_idx].set_xlabel("ld")
        if col_idx == 0:
            axs[row_idx][col_idx].set_ylabel("Compute time")
        idx += 1
    for ax in axs.flat:
        ax.set_ylim(0, ylim)
    plt.savefig(cfg.OUTPUT_DIR+"/latency.pdf")
    plt.show()


def get_network_arc_var_name(src_svc, src_cid, dst_svc, dst_cid):
    assert src_svc != dst_svc
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
            #     network_arc_var_name.append((f'{svc}{cfg.DELIMITER}{cid}{cfg.DELIMITER}end', opt_func.destination_node_fullname))
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


            
def log_timestamp(event_name):
    timestamp_list.append([event_name, time.time()])
    if len(timestamp_list) > 1:
        dur = round(timestamp_list[-1][1] - timestamp_list[-2][1], 5)
        app.logger.debug(f"{cfg.log_prefix} Finished, {event_name}, duration,{dur}")


def prettyprint_timestamp():
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
        

def get_network_edge_color(src_cid, dst_cid):
    if src_cid == NONE_CID or dst_cid == NONE_CID:
        return "black"
    elif src_cid == dst_cid:
        return "black"
    else:
        return "blue"
    
def get_node_color(cid):
    if cid == NONE_CID:
        return "gray"
    # yellow, pink, blue, green
    node_color = ["#FFBF00", "#ff6375", "#6973fa", "#AFE1AF"]
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
    g_.render(f'{cfg.OUTPUT_DIR}/callgraph', view = True) # output: call_graph.pdf
    g_


def plot_request_flow(percent_df, key, unique_service, callgraph, network_arc):
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
    for index, row in percent_df[key].iterrows():
        if row["flow"] <= 0 or row["weight"] <= 0:
            continue
        src_cid = row["src_cid"]
        dst_cid = row["dst_cid"]
        src_svc = row["src"]
        dst_svc = row["dst"]
        edge_color = get_network_edge_color(src_cid, dst_cid)
        src_node_color = get_node_color(src_cid)
        dst_node_color = get_node_color(dst_cid)
        src_node_name = src_svc+str(src_cid)
        dst_node_name = dst_svc+str(dst_cid)
        # src_node
        g_.node(name=src_node_name, label=src_svc[:name_cut], shape='circle', style='filled', fillcolor=src_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        # dst_node
        g_.node(name=dst_node_name, label=dst_svc[:name_cut], shape='circle', style='filled', fillcolor=dst_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        # edge from src_node to dst_node        
        g_.edge(src_node_name, dst_node_name, label=str(row["flow"]) + " ("+str(int(row["weight"]*100))+"%)", penwidth=edge_pw, style="filled", fontsize=edge_fs, fontcolor=edge_color, color=edge_color, arrowsize=edge_arrowsize, minlen=edge_minlen)
            
    g_.render(f'{cfg.OUTPUT_DIR}/call_graph-{key}', view = True) # output: call_graph.pdf
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


def get_network_time(src_cid, dst_cid):
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