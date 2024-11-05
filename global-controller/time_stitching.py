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
from global_controller import app
import logging

logging.config.dictConfig(cfg.LOGGING_CONFIG)
logger = logging.getLogger(__name__)

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



def single_trace_to_span_callgraph(single_trace):
    callgraph = dict()
    for parent_span in single_trace['span']:
        if parent_span not in callgraph:
            callgraph[parent_span] = list()
        for child_span in single_trace['span']:
            if child_span.parent_span_id == parent_span.span_id:
                callgraph[parent_span].append(child_span)
    for parent_span in callgraph:
        callgraph[parent_span] = sorted(callgraph[parent_span], key=lambda x: (x.svc_name, x.method, x.url))
    return callgraph


def print_single_trace(single_trace):
    logger.info(f"print_sinelg_trace")
    for span in single_trace['span']:
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

# def single_trace_to_span_callgraph(single_trace):
#     callgraph = dict()
#     for parent_span in single_trace:
#         if parent_span not in callgraph:
#             callgraph[parent_span] = list()
#         for child_span in single_trace:
#             if child_span.parent_span_id == parent_span.span_id:
#                 callgraph[parent_span].append(child_span)
#     for parent_span in callgraph:
#         callgraph[parent_span] = sorted(callgraph[parent_span], key=lambda x: (x.svc_name, x.method, x.url))
#     return callgraph


def count_num_node_in_callgraph(callgraph):
    node_set = set()
    for parent_ep_str in callgraph:
        node_set.add(parent_ep_str)
        for child_ep_str in callgraph[parent_ep_str]:
            node_set.add(child_ep_str)
    return len(node_set)

def get_all_endpoints(given_traces):
    all_endpoints = dict()
    for region in given_traces:
        if region not in all_endpoints:
            all_endpoints[region] = dict()
        for load_bucket in given_traces[region]:
            for tid in given_traces[region][load_bucket]:
                single_trace = given_traces[region][load_bucket][tid]
                for span in single_trace['span']:
                    if span.svc_name not in all_endpoints[region]:
                        all_endpoints[region][span.svc_name] = set()
                    all_endpoints[region][span.svc_name].add(span.endpoint_str)
    return all_endpoints


# def traces_to_span_callgraph_table(traces):
#     span_callgraph_table = dict()
#     for cid in traces:
#         for tid in traces[cid]:
#             single_trace = traces[cid][tid]
#             span_cg = single_trace_to_span_callgraph(single_trace)
#             cg_key = get_callgraph_key(span_cg)
#             if cg_key not in span_callgraph_table:
#                 logger.info(f"new callgraph key: {cg_key} in cluster {cid}")
#                 # NOTE: It is currently overwriting for the existing cg_key
#                 span_callgraph_table[cg_key] = span_cg
#     return span_callgraph_table


import hashlib

def static_hash(value):
    value_bytes = str(value).encode('utf-8')
    hash_object = hashlib.sha256()
    hash_object.update(value_bytes)
    return hash_object.hexdigest()


def traces_to_endpoint_str_callgraph_table(traces): # being used by global_controller.py
    ep_str_callgraph_table = dict()
    cg_key_hashmap = dict()
    for region in traces:
        for load_bucket in traces[region]:
            for tid in traces[region][load_bucket]:
                single_trace = traces[region][load_bucket][tid]
                ep_str_cg = single_trace_to_endpoint_str_callgraph(single_trace)
                cg_key = get_callgraph_key(ep_str_cg)
                if cg_key == False:
                    continue
                hash_key = static_hash(cg_key)[:8]
                cg_key_hashmap[hash_key] = cg_key
                # print(f'cg_key: {cg_key}')
                # if cg_key not in ep_str_callgraph_table:
                if hash_key not in ep_str_callgraph_table:
                    logger.info(f"new callgraph key: {hash_key}, {cg_key} in cluster {region}")
                    # NOTE: It is currently overwriting for the existing cg_key
                    ep_str_callgraph_table[hash_key] = ep_str_cg
    return ep_str_callgraph_table
    # return ep_str_callgraph_table, cg_key_hashmap

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
            if type(cur_node) == type("string"):
                # print(f"cur_node: {cur_node}")
                # print(cg_key)
                # cg_key.append(cur_node.split(cfg.ep_del)[0])
                # cg_key.append(cur_node.split(cfg.ep_del)[1])
                # cg_key.append(cur_node.split(cfg.ep_del)[2])
                cg_key.append(cur_node)
                # logger.info(f"[TIME_ST] cur_node: {cur_node}")
            # elif type(cur_node) == sp.Span:
            #     cg_key.append(cur_node.svc_name)
            #     cg_key.append(cur_node.method)
            #     cg_key.append(cur_node.url)
            else:
                logger.error(f"ERROR: invalid type of cur_node: {type(cur_node)}")
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
    logger.error(f'cannot find root node in callgraph')
    assert False


def get_callgraph_key(cg):
    root_node = opt_func.find_root_node(cg)
    if root_node == False:
        return False
    cg_key = list()
    bfs_callgraph(root_node, cg_key, cg)
    # print(f'cg_key: {cg_key}')
    # logger.info(f"[TIME_ST] cg_key: {cg_key}")
    cg_key_str = cfg.between_ep.join(cg_key)
    # logger.info(f"[TIME_ST] cg_key_str: {cg_key_str}")
    # for elem in cg_key:
    #     cg_key_str += elem + ","
    return cg_key_str


def print_traces(traces):
    for cid in traces:
        for load_bucket in traces[cid]:
            for tid in traces[cid][load_bucket]:
                single_trace = traces[cid][load_bucket][tid]
                print(f"======================= ")
                for span in single_trace['span']:
                    print(f"{span}")
                print(f"======================= ")


# Deprecated
# def inject_arbitrary_callsize(traces_, depth_dict):
#     for cid in traces_:
#         for tid, single_trace in traces_[cid].items():
#             for span in single_trace:
#                 span.depth = depth_dict[svc]
#                 span.call_size = depth_dict[svc]*10

# def print_callgraph(callgraph):
#     print(f"callgraph key: {get_callgraph_key(callgraph)}")
#     for parent_span in callgraph:
#         for child_span in callgraph[parent_span]:
#             print("{}->{}".format(parent_span.get_class(), child_span.get_class()))

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
    for span in single_trace['span']:
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

def trace_to_unfolded_df(traces):
    ## new
    # temp_gen = (
    #     span.unfold()
    #     for region_traces in traces.values()
    #     for load_bucket_traces in region_traces.values()
    #     for single_trace in load_bucket_traces.values()
    #     for span in single_trace['span']
    # )
    
    ## To avoid unfold function call
    temp_gen = (
        {
            "method": span.method,
            "url": span.url,
            "svc_name": span.svc_name,
            "endpoint": span.endpoint,
            "endpoint_str": span.endpoint_str,
            "span_id": span.span_id,
            "parent_span_id": span.parent_span_id,
            "trace_id": span.trace_id,
            "cluster_id": span.cluster_id,
            "rps_dict": span.rps_dict,
            "num_inflight_dict": span.num_inflight_dict,
            "st": span.st,
            "et": span.et,
            "rt": span.rt,
            "xt": span.xt,
            "ct": span.ct,
            "child_spans": span.child_spans,
            "critical_child_spans": span.critical_child_spans,
            "call_size": span.call_size,
            "depth": span.depth,
            "time": span.time,
            "rps": span.rps,
            "load_bucket": span.load_bucket
        }
        for region_traces in traces.values()
        for load_bucket_traces in region_traces.values()
        for single_trace in load_bucket_traces.values()
        for span in single_trace['span']
    )

    df = pd.DataFrame(temp_gen)
    return df
    
    ## old
    # temp = list()
    # for region in traces:
    #     for load_bucket in traces[region]:
    #         for tid in traces[region][load_bucket]:
    #             single_trace = traces[region][load_bucket][tid]
    #             for span in single_trace['span']:
    #                 temp.append(span.unfold())
    # df = pd.DataFrame(temp)
    # # df.sort_values(by=["trace_id"])
    # # df.reset_index(drop=True)
    # return df


def trace_to_df(traces):
    list_of_span_str = list()
    for region in traces:
        for load_bucket in traces[region]:
            for tid in traces[region][load_bucket]:
                single_trace = traces[region][load_bucket][tid]
                for span in single_trace['span']:
                    list_of_span_str.append(str(span))
    col = ["cluster_id","svc_name","method","url","trace_id","span_id","parent_span_id","st","et","rt","xt","ct","call_size"]
    df = pd.DataFrame(list_of_span_str, columns=col)
    df.sort_values(by=["trace_id"])
    df.reset_index(drop=True)
    return df


def get_placement_from_trace(given_traces):
    placement = dict()
    for region in given_traces:
        if region not in placement:
            placement[region] = set()
        for load_bucket in given_traces[region]:
            for tid in given_traces[region][load_bucket]:
                single_trace = given_traces[region][load_bucket][tid]
                for span in single_trace['span']:
                    placement[region].add(span.svc_name)
    return placement


def filter_by_num_endpoint(given_traces, num_endpoint):
    ret_traces = dict()
    for region in given_traces:
        num_broken_trace = 0
        for load_bucket in given_traces[region]:
            for tid in given_traces[region][load_bucket]:
                single_trace = given_traces[region][load_bucket][tid]
                if len(single_trace['span']) == num_endpoint:
                    broken_trace = False
                    for span in single_trace['span']:
                        if len(span.rps_dict) != 1: # limitation
                            logger.info(f"len(span.rps_dict), {len(span.rps_dict)} != 1, {span.rps_dict}")
                            broken_trace = True
                            break
                    if broken_trace:
                        num_broken_trace += 1
                        continue
                    if region not in ret_traces:
                        ret_traces[region] = dict()
                    if load_bucket not in ret_traces[region]:
                        ret_traces[region][load_bucket] = dict()
                    ret_traces[region][load_bucket][tid] = single_trace
                # else:
                #     logger.debug(f"filtered out trace {tid}, number of endpoint is {len(traces[region][tid])} != {num_endpoint}")
        # success = len(ret_traces[region])
        # total = len(given_traces[region])
        # success_ratio = success/total
        # logger.debug(f"given_traces[{region}], {len(given_traces[region])}, num_broken_trace[{region}], {num_broken_trace}, success_ratio, {success_ratio}")
        # num_broken_trace = 0
    return ret_traces


def stitch_time(given_traces):
    ret_traces = {}
    timestamp = {"callgraph": 0, "findroot": 0, "relativetime": 0, "exclusivetime": 0}
    for region, loads in given_traces.items():
        region_traces = ret_traces.setdefault(region, {})
        for load_bucket, tids in loads.items():
            load_traces = region_traces.setdefault(load_bucket, {})
            for tid, single_trace in tids.items():
                ret, temp = stitch_trace(single_trace, tid)
                timestamp["callgraph"] += temp[0]
                timestamp["findroot"] += temp[1]
                timestamp["relativetime"] += temp[2]
                timestamp["exclusivetime"] += temp[3]
                if ret:
                    load_traces[tid] = single_trace
                else:
                    logging.debug(f"stitch_trace failed for trace {tid}")
    logger.info(f"stitch_time, timestamp: {timestamp}")
    return ret_traces


def stitch_trace(single_trace, tid):
    # logger.info(f"start stitch_trace, tid: {tid}")
    # if detect_cycle(single_trace):
    #     logging.error(f"Circular reference detected in trace {tid}")
    #     assert False
    # logger.info(f"start single_trace_to_endpoint_str_callgraph, {tid}")
    temp = list()
    ts = time.time()
    ep_str_cg = single_trace_to_endpoint_str_callgraph(single_trace)
    temp.append(time.time()-ts)
    # logger.info(f"end single_trace_to_endpoint_str_callgraph, {tid}")
    # logger.info(f"start find_root_node, {tid}")
    ts = time.time()
    root_ep_str = opt_func.find_root_node(ep_str_cg)
    if root_ep_str == False:
        return False # too many root nodes or no root node
    temp.append(time.time()-ts)
    # logger.info(f"end find_root_node, {tid}")
    # logger.info(f"start change_to_relative_time, {tid}")
    ts = time.time()
    relative_time_ret = change_to_relative_time(single_trace, tid)
    temp.append(time.time()-ts)
    # logger.info(f"end change_to_relative_time, {tid}")
    # logger.info(f"start calc_exclusive_time, {tid}")
    ts = time.time()
    xt_ret = calc_exclusive_time(single_trace)
    temp.append(time.time()-ts)
    # logger.info(f"end calc_exclusive_time, {tid}")
    # ct_ret = analyze_critical_path_time(single_trace)
    ct_ret = True
    # logger.info(f"ends stitch_trace, tid: {tid}")
    if xt_ret == False or ct_ret == False or relative_time_ret == False:
        return False
    return True, temp

def detect_cycle(single_trace):
    """
    Detect if there's a circular reference in the parent-child relationships
    within single_trace based on parent_span_id.
    """
    visited = set()
    stack = set()
    def dfs(span_id):
        if span_id in stack:
            return True  # Found a cycle
        if span_id in visited:
            return False
        visited.add(span_id)
        stack.add(span_id)
        child_spans = [span for span in single_trace['span'] if span.parent_span_id == span_id]
        for child_span in child_spans:
            if dfs(child_span.span_id):
                return True
        stack.remove(span_id)
        return False
    for span in single_trace['span']:
        if span.parent_span_id is None:  # Root span check
            if dfs(span.span_id):
                logging.error(f"Circular reference detected starting from span {span.span_id}")
                return True
    return False

def single_trace_to_endpoint_str_callgraph(single_trace):
    callgraph = {}
    for span in single_trace['span']:
        endpoint_str = f"{span.svc_name}{cfg.ep_del}{span.method}{cfg.ep_del}{span.url}"
        if endpoint_str not in callgraph:
            callgraph[endpoint_str] = []
        for child_span in single_trace['span']:
            if child_span.parent_span_id == span.span_id:
                child_endpoint_str = f"{child_span.svc_name}{cfg.ep_del}{child_span.method}{cfg.ep_del}{child_span.url}"
                callgraph[endpoint_str].append(child_endpoint_str)
        if len(callgraph[endpoint_str]) > 1:
            callgraph[endpoint_str].sort()
    return callgraph


def change_to_relative_time(single_trace, tid):
    sp_cg = single_trace_to_span_callgraph(single_trace)
    root_span = opt_func.find_root_node(sp_cg)
    if not root_span:
        return False

    base_t = root_span.st
    for span in single_trace['span']:
        span.st -= base_t
        span.et -= base_t
        if span.st < 0 or span.et < span.st:
            return False
    return True

def calc_exclusive_time(single_trace):
    for parent_span in single_trace['span']:
        child_spans = [span for span in single_trace['span'] if span.parent_span_id == parent_span.span_id]
        
        if not child_spans:
            exclude_child_rt = 0
        elif len(child_spans) == 1:
            exclude_child_rt = child_spans[0].rt
        else:
            exclude_child_rt = calculate_exclude_child_rt(child_spans)

        parent_span.xt = parent_span.rt - exclude_child_rt
        if parent_span.xt <= 0:
            return False
    return True

def calculate_exclude_child_rt(child_spans):
    exclude_child_rt = 0
    for i in range(len(child_spans)):
        for j in range(i + 1, len(child_spans)):
            if is_parallel_execution(child_spans[i], child_spans[j]):
                exclude_child_rt = max(child_spans[i].rt, child_spans[j].rt)
            else:
                exclude_child_rt = child_spans[i].rt + child_spans[j].rt
    return exclude_child_rt

def single_trace_to_span_callgraph(single_trace):
    callgraph = {}
    for parent_span in single_trace['span']:
        child_spans = [span for span in single_trace['span'] if span.parent_span_id == parent_span.span_id]
        callgraph[parent_span] = sorted(child_spans, key=lambda x: (x.svc_name, x.method, x.url))
    return callgraph


# ###################################################################
# ## Old
# def stitch_time(given_traces):
#     ret_traces = dict()
#     for region in given_traces:
#         for load_bucket in given_traces[region]:
#             for tid in given_traces[region][load_bucket]:
#                 single_trace = given_traces[region][load_bucket][tid]
#                 if stitch_trace(single_trace, tid):
#                     if region not in ret_traces:
#                         ret_traces[region] = dict()
#                     if load_bucket not in ret_traces[region]:
#                         ret_traces[region][load_bucket] = dict()
#                     if tid not in ret_traces[region][load_bucket]:
#                         ret_traces[region][load_bucket][tid] = dict()
#                     ret_traces[region][load_bucket][tid] = single_trace
#                 else:
#                     logger.debug(f"stitch_trace failed for trace {tid}")
#     return ret_traces
#
# def single_trace_to_endpoint_str_callgraph(single_trace):
#     callgraph = dict()
#     for parent_span in single_trace['span']:
#         parent_ep_str = parent_span.endpoint_str
#         if parent_ep_str not in callgraph:
#             callgraph[parent_ep_str] = list()
#         for child_span in single_trace['span']:
#             child_ep_str = child_span.endpoint_str
#             if child_span.parent_span_id == parent_span.span_id:
#                 callgraph[parent_ep_str].append(child_ep_str)
#     for parent_ep_str in callgraph:
#         callgraph[parent_ep_str].sort()
#     return callgraph

# def change_to_relative_time(single_trace, tid):
#     # logger = logging.getLogger(__name__)
#     sp_cg = single_trace_to_span_callgraph(single_trace)
#     root_span = opt_func.find_root_node(sp_cg)
#     if root_span == False:
#         return False
#     base_t = root_span.st
#     for span in single_trace['span']:
#         span.st -= base_t
#         span.et -= base_t
#         if span.st < 0.0 or span.et < 0.0 or span.et < span.st:
#             return False
#     return True


# def calc_exclusive_time(single_trace):
#     for parent_span in single_trace['span']:
#         child_span_list = list()
#         for span in single_trace['span']:
#             if span.parent_span_id == parent_span.span_id:
#                 child_span_list.append(span)
#         if len(child_span_list) == 0:
#             exclude_child_rt = 0
#         elif  len(child_span_list) == 1:
#             exclude_child_rt = child_span_list[0].rt
#         else: # else is redundant but still I leave it there to make the if/else logic easy to follow
#             for i in range(len(child_span_list)):
#                 for j in range(i+1, len(child_span_list)):
#                     is_parallel = is_parallel_execution(child_span_list[i], child_span_list[j])
#                     if is_parallel == 1 or is_parallel == 2: # parallel execution
#                         # TODO: parallel-1 and parallel-2 should be dealt with individually.
#                         exclude_child_rt = max(child_span_list[i].rt, child_span_list[j].rt)
#                     else: 
#                         # sequential execution
#                         exclude_child_rt = child_span_list[i].rt + child_span_list[j].rt
#         parent_span.xt = parent_span.rt - exclude_child_rt
#         # print(f"Service: {parent_span.svc_name}, Response time: {parent_span.rt}, Exclude_child_rt: {exclude_child_rt}, Exclusive time: {parent_span.xt}")
#         if parent_span.xt <= 0.0:
#             # print(f"ERROR: parent_span,{parent_span.svc_name}, span_id,{parent_span.span_id} exclusive time cannot be negative value: {parent_span.xt}")
#             # print(f"ERROR: st,{parent_span.st}, et,{parent_span.et}, rt,{parent_span.rt}, xt,{parent_span.xt}")
#             # print("trace")
#             # for span in single_trace:
#             #     print(span)
#             return False
#         ###########################################
#         # if parent_span.svc_name == FRONTEND_svc:
#         #     parent_span.xt = parent_span.rt
#         # else:
#         #     parent_span.xt = 0
#         ###########################################
#     return True
# #############################################################################