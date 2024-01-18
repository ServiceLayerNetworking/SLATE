#!/usr/bin/env python
# coding: utf-8

import time
# from global_controller import app
import config as cfg
import optimizer_header as opt_func
import span as sp
import pandas as pd
from IPython.display import display
from collections import deque
import os
from pprint import pprint

# pd.set_option('display.max_rows', None)
pd.set_option('display.max_colwidth', None)
pd.set_option('display.max_columns', None)


""" Trace exampe line (Version 1 wo call size)
2
f85116460cc0c607a484d0521e62fb19 7c30eb0e856124df a484d0521e62fb19 1694378625363 1694378625365
4ef8ed533389d8c9ace91fc1931ca0cd 48fb12993023f618 ace91fc1931ca0cd 1694378625363 1694378625365

<Num requests>
<Trace Id> <Span Id> <Parent Span Id> <Start Time> <End Time>

Root svc will have no parent span id
"""
        
def print_log(msg, obj=None):
    if VERBOSITY >= 1:
        if obj == None:
            print("[LOG] ", end="")
            print(msg)
        else:
            print("[LOG] ", end="")
            print(msg, obj)
        

SPAN_DELIM = " "
SPAN_TOKEN_LEN = 5
## NOTE: deprecated
def create_span(line, svc, load, cid):
    tokens = line.split(SPAN_DELIM)
    if len(tokens) != SPAN_TOKEN_LEN:
        print("Invalid token length in span line. len(tokens):{}, line: {}".format(len(tokens), line))
        assert False
    tid = tokens[0]
    sid = tokens[1]
    psid = tokens[2]
    st = int(tokens[3])
    et = int(tokens[4])
    span = sp.Span(svc, cid, tid, sid, psid, st, et, load, -10)
    return tid, span

DE_in_log=" "
info_kw = "INFO"
info_kw_idx = 2
min_len_tokens = 4

## New
# svc_kw_idx = -1

## Old
svc_kw_idx = -2
load_kw_idx = -1
NUM_CLUSTER = 2

def parse_trace_file(log_path):
    f = open(log_path, "r")
    lines = f.readlines()
    traces_ = dict()
    idx = 0
    while idx < len(lines):
        token = lines[idx].split(DE_in_log)
        if len(token) >= min_len_tokens:
            if token[info_kw_idx] == info_kw:
                try:
                    load_per_tick = int(token[load_kw_idx])
                    service_name = token[svc_kw_idx][:-1]
                    if load_per_tick > 0:
                        print_log("svc name," + service_name + ", load per tick," + str(load_per_tick))
                        while True:
                            idx += 1
                            if lines[idx+1] == "\n":
                                break
                            # TODO: cluster id is supposed to be parsed from the log.
                            for cid in range(NUM_CLUSTER):
                                tid, span = create_span(lines[idx], service_name, load_per_tick, cid)
                                # TODO: The updated trace file is needed.
                                if cid not in traces_:
                                    traces_[cid] = dict()
                                if tid not in traces_[cid]:
                                    traces_[cid][tid] = dict()
                                if service_name not in traces_[cid][tid]:
                                    traces_[cid][tid].append(span)
                                else:
                                    print(service_name + " already exists in trace["+tid+"]")
                                    assert False
                                # print(str(span.span_id) + " is added to " + tid + "len, "+ str(len(traces_[tid])))
                    #######################################################
                except ValueError:
                    print("token["+str(load_kw_idx)+"]: " + token[load_kw_idx] + " is not integer..?\nline: "+lines[idx])
                    assert False
                except Exception as error:
                    print(error)
                    print("line: " + lines[idx])
                    assert False
        idx+=1
    return traces_


def create_span_ver2(row):
    trace_id = row["trace_id"]
    cluster_id = row["cluster_id"]
    svc = row["svc_name"]
    span_id = row["span_id"][:8] # NOTE
    parent_span_id = row["parent_span_id"][:8] # NOTE
    st = row["st"]
    et = row["et"]
    load = row["load"]
    last_load = row["last_load"]
    avg_load = row["avg_load"]
    try:
        rps = row["rps"]
    except:
        rps = 0
    ########################
    # load = row["avg_load"] 
    ########################
    callsize = row["call_size"]
    span = sp.Span(svc, cluster_id, trace_id, span_id, parent_span_id, st, et, load, last_load, avg_load, rps, callsize)
    return span


def trace_trimmer(trace_file):
    df = pd.read_csv(trace_file)
    col_len = df.shape[1]
    if col_len == 13:
        col_name = ["trace_id","svc_name","cluster_id","span_id","parent_span_id","load","last_load","avg_load","st","et","rt","call_size"]
    elif col_len == 14:
        col_name = ['a', 'b', "trace_id","svc_name","cluster_id","span_id","parent_span_id","load","last_load","avg_load","st","et","rt","call_size"]
    elif col_len == 15:
        col_name = ['a', 'b', "trace_id","svc_name","cluster_id","span_id","parent_span_id","load","last_load","avg_load", "rps", "st","et","rt","call_size"]
    else:
        print("ERROR trace_trimmer, invalid column length, ", col_len)
        assert False
    print(f"col_len: {col_len}")
    df.columns = col_name
    # df = df.drop('a', axis=1)
    # df = df.drop('b', axis=1)
    df.fillna("", inplace=True)
    df = df[((df["svc_name"] == FRONTEND_svc) & (df["rt"] > 20)) | (df["svc_name"] != FRONTEND_svc)]
    df = df[(df["svc_name"] == REVIEW_V3_svc) & (df["rt"] < 50) | (df["svc_name"] != REVIEW_V3_svc)]
    df[["load"]].apply(lambda x: pd.to_numeric(x, errors='coerce')).dropna()
    df['load'] = df['load'].clip(lower=1)
    df['avg_load'] = df['avg_load'].clip(lower=1)
    df['last_load'] = df['last_load'].clip(lower=1)
    # display(df)
    return df


def parse_trace_file_ver2(log_path):
    df = trace_trimmer(log_path)
    traces_ = dict() # cluster_id -> trace id -> svc_name -> span
    for index, row in df.iterrows():
        span = create_span_ver2(row)
        if span.cluster_id not in traces_:
            traces_[span.cluster_id] = dict()
        if span.trace_id not in traces_[span.cluster_id]:
            traces_[span.cluster_id][span.trace_id] = dict()
        if span.svc_name not in traces_[span.cluster_id][span.trace_id]:
            traces_[span.cluster_id][span.trace_id].append(span)
        else:
            print(span.svc_name + " already exists in trace["+span.trace_id+"]")
    return traces_


## Deprecated
# NOTE: This function is bookinfo specific
def remove_incomplete_trace_in_bookinfo(traces_):
    ##############################
    FRONTEND_svc = "productpage-v1"
    span_id_of_FRONTEND_svc = ""
    REVIEW_V1_svc = "reviews-v1"
    REVIEW_V2_svc = "reviews-v2"
    REVIEW_V3_svc = "reviews-v3"
    RATING_svc = "ratings-v1"
    DETAIL_svc = "details-v1"
    ##############################
    FILTER_REVIEW_V1 = True # False
    FILTER_REVIEW_V2 = True # False
    FILTER_REVIEW_V3 = False# False
    ##############################
    # ratings-v1 and reviews-v1 should not exist in the same trace
    MIN_TRACE_LEN = 3
    MAX_TRACE_LEN = 4
    ret_traces_ = dict()
    what = [0]*9
    weird_span_id = 0
    for cid in traces_:
        if cid not in ret_traces_:
            ret_traces_[cid] = dict()
        for tid, single_trace in traces_[cid].items():
            if FRONTEND_svc not in single_trace or DETAIL_svc not in single_trace:
                # if FRONTEND_svc not in single_trace:
                #     print("no frontend")
                # if DETAIL_svc not in single_trace:
                #     print("no detail")
                # print(f"single_trace: {single_trace}")
                # for svc, span in single_trace.items():
                #     print(svc, " ")
                #     print(span)
                # print()
                what[0] += 1
            elif len(single_trace) < MIN_TRACE_LEN:
                what[1] += 1
            elif len(single_trace) > MAX_TRACE_LEN:
                what[2] += 1
            elif len(single_trace) == MIN_TRACE_LEN and (REVIEW_V1_svc not in single_trace or REVIEW_V2_svc in single_trace or REVIEW_V3_svc in single_trace):
                what[3] += 1
            elif len(single_trace) == MAX_TRACE_LEN and REVIEW_V2_svc not in single_trace and REVIEW_V3_svc not in single_trace:
                what[4] += 1
            elif single_trace[FRONTEND_svc].parent_span_id != span_id_of_FRONTEND_svc:
                print("single_trace[FRONTEND_svc].parent_span_id: ", single_trace[FRONTEND_svc].parent_span_id)
                print("span_id_of_FRONTEND_svc: ", span_id_of_FRONTEND_svc)
                weird_span_id += 1
                what[5] += 1
            elif FILTER_REVIEW_V1 and REVIEW_V1_svc in single_trace:
                if len(single_trace) != 3:
                    print_single_trace(single_trace)
                assert len(single_trace) == 3
                what[6] += 1
            elif FILTER_REVIEW_V2 and REVIEW_V2_svc in single_trace:
                if len(single_trace) != 4:
                    print_single_trace(single_trace)
                assert len(single_trace) == 4
                what[7] += 1
            elif FILTER_REVIEW_V3 and REVIEW_V3_svc in single_trace:
                if len(single_trace) != 4:
                    print_single_trace(single_trace)
                assert len(single_trace) == 4
                what[8] += 1
            else:
                if tid not in ret_traces_[cid]:
                    ret_traces_[cid][tid] = dict()
                ret_traces_[cid][tid] = single_trace
        print(f"weird_span_id: {weird_span_id}")
        print(f"filter stats: {what}")
        print(f"Cluster {cid}")
        print(f"#return trace: {len(ret_traces_[cid])}")
        print(f"#input trace: {len(traces_[cid])}")
    return ret_traces_


def change_to_relative_time(single_trace):
    try:
        sp_cg = single_trace_to_span_callgraph(single_trace)
        root_span = opt_func.find_root_node(sp_cg)
        base_t = root_span.st
    except Exception as error:
        print(error)
        assert False
    for span in single_trace:
        span.st -= base_t
        span.et -= base_t
        assert span.st >= 0
        assert span.et >= 0
        assert span.et >= span.st


def print_single_trace(single_trace):
    print(f"print_sinelg_trace")
    for span in single_trace:
        print(f"{span}")

def print_dag(single_dag):
    for parent_span in single_dag():
        for child_span in single_dag[parent_span]:
            print("{}({})->{}({})".format(parent_span.svc_name, parent_span.span_id, child_span.svc_name, child_span.span_id))
            
'''
Logical callgraph: A->B, A->C

parallel-1
    ----------------------A
        -----------B
           -----C
parallel-2
    ----------------------A
        --------B
             ---------C
sequential
    ----------------------A
        -----B
                 -----C
'''
def is_parallel_execution(span_a, span_b):
    assert span_a.parent_span_id == span_b.parent_span_id
    if span_a.st < span_b.st:
        earlier_start_span = span_a
        later_start_span = span_b
    else:
        earlier_start_span = span_b
        later_start_span = span_a
    if earlier_start_span.et > later_start_span.st and later_start_span.et > earlier_start_span.st: # parallel execution
        if earlier_start_span.st < later_start_span.st and earlier_start_span.et > later_start_span.et: # parallel-1
            return 1
        else: # parallel-2
            return 2
    else: # sequential execution
        return 0
    
    
'''
one call graph maps to one trace
callgraph = {A_span: [B_span, C_span], B_span:[D_span], C_span:[], D_span:[]}
'''

def single_trace_to_span_callgraph(single_trace):
    callgraph = dict()
    for parent_span in single_trace:
        if parent_span not in callgraph:
            callgraph[parent_span] = list()
        for child_span in single_trace:
            if child_span.parent_span_id == parent_span.span_id:
                callgraph[parent_span].append(child_span)
    for parent_span in callgraph:
        callgraph[parent_span] = sorted(callgraph[parent_span], key=lambda x: (x.svc_name, x.method, x.url))
    return callgraph

def single_trace_to_endpoint_str_callgraph(single_trace):
    callgraph = dict()
    for parent_span in single_trace:
        parent_ep_str = parent_span.endpoint_str
        if parent_ep_str not in callgraph:
            callgraph[parent_ep_str] = list()
        for child_span in single_trace:
            child_ep_str = child_span.endpoint_str
            if child_span.parent_span_id == parent_span.span_id:
                callgraph[parent_ep_str].append(child_ep_str)
    for parent_ep_str in callgraph:
        callgraph[parent_ep_str].sort()
    tot_num_node_in_topology = 0
    for parent_ep_str in callgraph:
        tot_num_node_in_topology += 1
        for child_ep_str in callgraph[parent_ep_str]:
            tot_num_node_in_topology += 1
    return callgraph, tot_num_node_in_topology

def get_endpoint_to_cg_key_map(traces_):
    endpoint_to_cg_key = dict()
    for cid in traces_:
        for tid, single_trace in traces_[cid].items():
            sp_cg = single_trace_to_span_callgraph(single_trace)
            cg_key = get_callgraph_key(sp_cg)
            for span in single_trace:
                if span.endpoint_str not in endpoint_to_cg_key:
                    endpoint_to_cg_key[span.endpoint_str] = set()
                endpoint_to_cg_key[span.endpoint_str].add(cg_key)
    for ep_str in endpoint_to_cg_key:
        if len(endpoint_to_cg_key[ep_str]) > 1:
            print(f"ERROR: endpoint {ep_str} has more than one callgraph key")
            print(f'endpoint_to_cg_key[{ep_str}]: {endpoint_to_cg_key[ep_str]}')
            assert False
        endpoint_to_cg_key[ep_str] = list(endpoint_to_cg_key[ep_str])[0]
    return endpoint_to_cg_key

def find_root_span_in_trace(single_trace):
    span_cg = single_trace_to_span_callgraph(single_trace)
    root_span = opt_func.find_root_node(span_cg)
    temp = dict()
    root_node = list()
    for ep1 in cg:
        temp[ep1] = "True"
        for ep2 in cg:
            if ep1 in cg[ep2]:
                temp[ep1] = "False"
        if temp[ep1] == "True":
            root_node.append(ep1)
    if len(root_node) == 0:
        print(f'ERROR: cannot find root node in callgraph')
        assert False
    if len(root_node) > 1:
        print(f'ERROR: too many root node in callgraph')
        assert False
    return root_node[0]

def get_all_endpoints(traces):
    all_endpoints = dict()
    for cid in traces:
        if cid not in all_endpoints:
            all_endpoints[cid] = dict()
        for tid in traces[cid]:
            single_trace = traces[cid][tid]
            for span in single_trace:
                if span.svc_name not in all_endpoints[cid]:
                    all_endpoints[cid][span.svc_name] = set()
                all_endpoints[cid][span.svc_name].add(span.endpoint_str)
    return all_endpoints

def traces_to_span_callgraph_table(traces):
    span_callgraph_table = dict()
    for cid in traces:
        for tid in traces[cid]:
            single_trace = traces[cid][tid]
            span_cg = single_trace_to_span_callgraph(single_trace)
            cg_key = get_callgraph_key(span_cg)
            if cg_key not in span_callgraph_table:
                print(f"new callgraph key: {cg_key} in cluster {cid}")
                # NOTE: It is currently overwriting for the existing cg_key
                span_callgraph_table[cg_key] = span_cg
    return span_callgraph_table

def traces_to_endpoint_str_callgraph_table(traces):
    endpoint_callgraph_table = dict()
    for cid in traces:
        for tid in traces[cid]:
            single_trace = traces[cid][tid]
            ep_str_cg, tot_num_node_in_topology = single_trace_to_endpoint_str_callgraph(single_trace)
            cg_key = get_callgraph_key(ep_str_cg)
            # print(f'cg_key: {cg_key}')
            if cg_key not in endpoint_callgraph_table:
                print(f"new callgraph key: {cg_key} in cluster {cid}")
                # NOTE: It is currently overwriting for the existing cg_key
                endpoint_callgraph_table[cg_key] = ep_str_cg
    return endpoint_callgraph_table

def file_write_callgraph_table(sp_callgraph_table):
    with open(f"{cfg.OUTPUT_DIR}/callgraph_table.csv", 'w') as file:
        file.write("cluster_id,parent_svc, parent_method, parent_url, child_svc, child_method, child_url\n")
        for cg_key in sp_callgraph_table:
            file.write(cg_key)
            file.write("\n")
            cg = sp_callgraph_table[cg_key]
            for parent_span in cg:
                for child_span in cg[parent_span]:
                    temp = f"{parent_span.svc_name}, {parent_span.method}, {parent_span.url}, {child_span.svc_name}, {child_span.method}, {child_span.url}\n"
                    file.write(temp)
                            

def bfs_callgraph(start_node, cg_key, ep_cg):
    visited = set()
    queue = deque([start_node])
    while queue:
        cur_node = queue.popleft()
        if cur_node not in visited:
            visited.add(cur_node)
            if type(cur_node) == type("asdf"):
                # print(f"cur_node: {cur_node}")
                # print(cg_key)
                cg_key.append(cur_node.split(sp.ep_del)[0])
                cg_key.append(cur_node.split(sp.ep_del)[1])
                cg_key.append(cur_node.split(sp.ep_del)[2])
            elif type(cur_node) == sp.Span:
                cg_key.append(cur_node.svc_name)
                cg_key.append(cur_node.method)
                cg_key.append(cur_node.url)
            else:
                print(f"ERROR: invalid type of cur_node: {type(cur_node)}")
                assert False
            for child_ep in ep_cg[cur_node]:
                if child_ep not in visited:
                    queue.extend([child_ep])


def find_root_span(cg):
    for parent_span in cg:
        for child_span in cg[parent_span]:
            if sp.are_they_same_endpoint(parent_span, child_span):
                break
        return parent_span
    print(f'ERROR: cannot find root node in callgraph')
    assert False


def get_callgraph_key(cg):
    root_node = opt_func.find_root_node(cg)
    cg_key = list()
    bfs_callgraph(root_node, cg_key, cg)
    # print(f'cg_key: {cg_key}')
    cg_key_str = sp.ep_del.join(cg_key)
    # for elem in cg_key:
    #     cg_key_str += elem + ","
    return cg_key_str


def calc_exclusive_time(single_trace):
    for parent_span in single_trace:
        child_span_list = list()
        for span in single_trace:
            if span.parent_span_id == parent_span.span_id:
                child_span_list.append(span)
        if len(child_span_list) == 0:
            exclude_child_rt = 0
        elif  len(child_span_list) == 1:
            exclude_child_rt = child_span_list[0].rt
        else: # else is redundant but still I leave it there to make the if/else logic easy to follow
            for i in range(len(child_span_list)):
                for j in range(i+1, len(child_span_list)):
                    is_parallel = is_parallel_execution(child_span_list[i], child_span_list[j])
                    if is_parallel == 1 or is_parallel == 2: # parallel execution
                        # TODO: parallel-1 and parallel-2 should be dealt with individually.
                        exclude_child_rt = max(child_span_list[i].rt, child_span_list[j].rt)
                    else: 
                        # sequential execution
                        exclude_child_rt = child_span_list[i].rt + child_span_list[j].rt
        parent_span.xt = parent_span.rt - exclude_child_rt
        # print(f"Service: {parent_span.svc_name}, Response time: {parent_span.rt}, Exclude_child_rt: {exclude_child_rt}, Exclusive time: {parent_span.xt}")
        if parent_span.xt < 0.0:
            # print(f"ERROR: parent_span,{parent_span.svc_name}, span_id,{parent_span.span_id} exclusive time cannot be negative value: {parent_span.xt}")
            # print(f"ERROR: st,{parent_span.st}, et,{parent_span.et}, rt,{parent_span.rt}, xt,{parent_span.xt}")
            # print("trace")
            # for span in single_trace:
            #     print(span)
            return False
        ###########################################
        # if parent_span.svc_name == FRONTEND_svc:
        #     parent_span.xt = parent_span.rt
        # else:
        #     parent_span.xt = 0
        ###########################################
    return True

def print_traces(traces_):
    for cid in traces_:
        for tid in traces_[cid]:
            for single_trace in traces_[cid][tid]:
                print(f"======================= ")
                print(f"Trace: " + str(tid))
                for span in single_trace:
                    print(f"{span}")
                print(f"======================= ")


# Deprecated
# def inject_arbitrary_callsize(traces_, depth_dict):
#     for cid in traces_:
#         for tid, single_trace in traces_[cid].items():
#             for span in single_trace:
#                 span.depth = depth_dict[svc]
#                 span.call_size = depth_dict[svc]*10

def print_callgraph(callgraph):
    print(f"callgraph key: {get_callgraph_key(callgraph)}")
    for parent_span in callgraph:
        for child_span in callgraph[parent_span]:
            print("{}->{}".format(parent_span.get_class(), child_span.get_class()))

def print_callgraph_table(callgraph_table):
    print("print_callgraph_table")
    for cid in callgraph_table:
        for cg_key in callgraph_table[cid]:
            print(f"cg_key: {cg_key}")
            for cg in callgraph_table[cid][cg_key]:
                pprint(cg)
                # print_callgraph(cg)
            print()


def set_depth_of_span(cg, parent_svc, children, depth_d, prev_dep):
    if len(children) == 0:
        # print(f"Leaf service {parent_svc}, Escape recursive function")
        return
    for child_svc in children:
        if child_svc not in depth_d:
            depth_d[child_svc] = prev_dep + 1
            # print(f"Service {child_svc}, depth, {depth_d[child_svc]}")
        set_depth_of_span(cg, child_svc, cg[child_svc], depth_d, prev_dep+1)


def analyze_critical_path_time(single_trace):
    # print(f"Critical Path Analysis")
    for span in single_trace:
        sorted_children = sorted(span.child_spans, key=lambda x: x.et, reverse=True)
        if len(span.critical_child_spans) != 0:
            print(f"critical_path_analysis, {span}")
            print(f"critical_path_analysis, critical_child_spans:", end="")
            for ch_sp in span.critical_child_spans:
                print(f"{ch_sp}")
        cur_end_time = span.et
        total_critical_children_time = 0
        for child_span in sorted_children:
            if child_span.et < cur_end_time:
                span.critical_child_spans.append(child_span)
                total_critical_children_time += child_span.rt
                cur_end_time = child_span.st
        span.ct = span.rt - total_critical_children_time
        # assert span.ct >= 0.0
        if span.ct < 0.0:
            return False
    return True


def trace_to_df(traces_):
    list_of_unfold_span = list()
    colname = list()
    for cid in traces_:
        for tid, single_trace in traces_[cid].items():
            for span in single_trace:
                unfold_span = span.unfold()
                if len(colname) == 0:
                    colname = unfold_span.keys()
                    # print("colname, ", colname)
                # print(f"unfold_span: {unfold_span}")
                list_of_unfold_span.append(unfold_span)
    df = pd.DataFrame(list_of_unfold_span)
    df.sort_values(by=["trace_id"])
    df.reset_index(drop=True)
    return df


def get_placement_from_trace(traces):
    placement = dict()
    for cid in traces:
        if cid not in placement:
            placement[cid] = set()
        for tid, single_trace in traces[cid].items():
            for span in single_trace:
                placement[cid].add(span.svc_name)
    return placement


def stitch_time(traces):
    ret_traces = dict()
    for cid in traces:
        for tid in traces[cid]:
            ret = stitch_trace(traces[cid][tid])
            if ret == True:
                if cid not in ret_traces:
                    ret_traces[cid] = dict()
                ret_traces[cid][tid] = traces[cid][tid]
    # df = trace_to_df(traces)
    # print_all_trace(traces)
    
    return ret_traces


def stitch_trace(trace):
    ep_str_cg, tot_num_node_in_topology = single_trace_to_endpoint_str_callgraph(trace)
    # print(f"tot_num_node_in_topology: {tot_num_node_in_topology}")
    root_ep_str = opt_func.find_root_node(ep_str_cg)
    # print(f"root_ep: {root_ep_str}")
    # pprint(f"ep_str_cg: {ep_str_cg}")
    # exit()
    change_to_relative_time(trace)
    xt_ret = calc_exclusive_time(trace)
    ct_ret = analyze_critical_path_time(trace)
    if xt_ret == False or ct_ret == False:
        return False
    return True