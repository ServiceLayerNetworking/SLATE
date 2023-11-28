import config as cfg
import graphviz
from global_controller import app
import time
import pandas as pd
import math

timestamp_list = list()
source_node_name = "SOURCE"
destination_node_name = "DESTINATION"
none_cid = -1
source_node_fullname = f'{source_node_name}{cfg.DELIMITER}{none_cid}{cfg.DELIMITER}{none_cid}'
destination_node_fullname = f'{destination_node_name}{cfg.DELIMITER}{none_cid}{cfg.DELIMITER}{none_cid}'

def write_arguments_to_file(num_reqs, callgraph, depth_dict, callsize_dict, unique_service):
    num_cluster = len(num_reqs)
    print(f'{cfg.log_prefix} APP_NAME: {cfg.APP_NAME}')
    print(f'{cfg.log_prefix} NUM_CLUSTER: {num_cluster}')
    print(f"{cfg.log_prefix} callgraph: {callgraph}")
    for cid in range(len(num_reqs)):
        print(f"{cfg.log_prefix} num_reqs[{cid}]: {num_reqs[cid]}")
    for cid in range(len(num_reqs)):
        print(f"{cfg.log_prefix} unique_service[{cid}]: {unique_service[cid]}")
    print(f"{cfg.log_prefix} depth_dict: {depth_dict}")
    print(f"{cfg.log_prefix} callsize_dict: {callsize_dict}")
    print(f'{cfg.log_prefix} REGRESSOR_DEGREE: {cfg.REGRESSOR_DEGREE}')
    print(f'{cfg.log_prefix} INTRA_CLUTER_RTT: {cfg.INTRA_CLUTER_RTT}')
    print(f'{cfg.log_prefix} INTER_CLUSTER_RTT: {cfg.INTER_CLUSTER_RTT}')
    print(f'{cfg.log_prefix} INTER_CLUSTER_EGRESS_COST: {cfg.INTER_CLUSTER_EGRESS_COST}')
    print(f'{cfg.log_prefix} DOLLAR_PER_MS: {cfg.DOLLAR_PER_MS}')
    with open(f'{cfg.OUTPUT_DIR}/arguments.txt', 'w') as f:
        f.write(f' APP_NAME: {cfg.APP_NAME}\n')
        f.write(f' NUM_CLUSTER: {num_cluster}\n')
        f.write(f" callgraph: {callgraph}\n")
        for cid in range(len(num_reqs)):
            f.write(f" num_reqs[{cid}]: {num_reqs[cid]}\n")
        for cid in range(len(num_reqs)):
            f.write(f" unique_service[{cid}]: {unique_service[cid]}\n")
        f.write(f" depth_dict: {depth_dict}\n")
        f.write(f" callsize_dict: {callsize_dict}\n")
        f.write(f' REGRESSOR_DEGREE: {cfg.REGRESSOR_DEGREE}\n')
        f.write(f' INTRA_CLUTER_RTT: {cfg.INTRA_CLUTER_RTT}\n')
        f.write(f' INTER_CLUSTER_RTT: {cfg.INTER_CLUSTER_RTT}\n')
        f.write(f' INTER_CLUSTER_EGRESS_COST: {cfg.INTER_CLUSTER_EGRESS_COST}\n')
        f.write(f' DOLLAR_PER_MS: {cfg.DOLLAR_PER_MS}\n')

    
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
        if src_cid != none_cid and dst_cid != none_cid:
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
        if row["flow"] <= 0 or row["weight"] <= 0:
            continue
        src_cid = row["src_cid"]
        dst_cid = row["dst_cid"]
        src_svc = row["src"]
        dst_svc = row["dst"]
        if src_cid == none_cid or  dst_cid == none_cid:
            edge_color = "black"
        else:
            if src_cid == dst_cid:
                edge_color =  local_routing_edge_color # local routing
            else:
                edge_color = remote_routing_edge_color # remote routing
        if src_cid == none_cid:
            src_node_color = src_and_dst_node_color
        else:
            src_node_color = node_color[src_cid]
        if dst_cid == none_cid:
            dst_node_color = src_and_dst_node_color
        else:
            dst_node_color = node_color[dst_cid]
        
        src_node_name = src_svc+str(src_cid)
        dst_node_name = dst_svc+str(dst_cid)
        g_.node(name=src_node_name, label=src_svc[:name_cut], shape='circle', style='filled', fillcolor=src_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        
        g_.node(name=dst_node_name, label=dst_svc[:name_cut], shape='circle', style='filled', fillcolor=dst_node_color, penwidth=node_pw, fontsize=fs, fontname=fn, fixedsize="True", width="0.5")
        
        g_.edge(src_node_name, dst_node_name, label=str(row["flow"]) + " ("+str(int(row["weight"]*100))+"%)", penwidth=edge_pw, style="filled", fontsize=edge_fs_0, fontcolor=edge_color, color=edge_color, arrowsize=edge_arrowsize, minlen=edge_minlen)
            
    g_.render(f'{cfg.OUTPUT_DIR}/call_graph', view = True) # output: call_graph.pdf
    g_
    

def get_compute_arc_var_name(svc_name, cid):
    return (f'{svc_name}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start', f'{svc_name}{cfg.DELIMITER}{cid}{cfg.DELIMITER}end') # tuple
    # return f'{svc_name}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start,{svc_name}{cfg.DELIMITER}{cid}{cfg.DELIMITER}end' # string


def get_network_arc_var_name(src_svc, src_cid, dst_svc, dst_cid):
    assert src_svc != dst_svc
    return (f'{src_svc}{cfg.DELIMITER}{src_cid}{cfg.DELIMITER}end',f'{dst_svc}{cfg.DELIMITER}{dst_cid}{cfg.DELIMITER}start') # tuple


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