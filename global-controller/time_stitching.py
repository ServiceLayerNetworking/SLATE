#!/usr/bin/env python
# coding: utf-8

import time
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
from concurrent.futures import ThreadPoolExecutor, as_completed

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

def trace_df_to_endpoint_callgraph_table(given_df):
    ep_str_callgraph_table = dict()
    for tid in given_df["trace_id"].unique():
        single_trace = given_df[given_df["trace_id"] == tid]
        ep_str_cg = singlejson_trace_to_endpoint_str_callgraph(single_trace)
        cg_key = get_callgraph_key(ep_str_cg)
        assert cg_key != False
        hash_key = static_hash(cg_key)[:8]
        if hash_key not in ep_str_callgraph_table:
            logger.info(f"new callgraph key: {hash_key}, callgraph str {cg_key} in trace {tid}")
            ep_str_callgraph_table[hash_key] = ep_str_cg
            ## NOTE: It will only get one request type. For multiple request type, uncomment it.
            break
    return ep_str_callgraph_table

def singlejson_trace_to_endpoint_str_callgraph(single_trace):
    callgraph = {}
    for index, row in single_trace.iterrows():
        endpoint_str = f"{row['svc_name']}{cfg.ep_del}{row['method']}{cfg.ep_del}{row['url']}"
        if endpoint_str not in callgraph:
            callgraph[endpoint_str] = []
        for child_index, child_row in single_trace.iterrows():
            if child_row["parent_span_id"] == row["span_id"]:
                child_endpoint_str = f"{child_row['svc_name']}{cfg.ep_del}{child_row['method']}{cfg.ep_del}{child_row['url']}"
                callgraph[endpoint_str].append(child_endpoint_str)
        if len(callgraph[endpoint_str]) > 1:
            callgraph[endpoint_str].sort()
    return callgraph

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
    return ret_traces

##################################################################
##################################################################

def stitch_time_in_df_concurrent(given_df, ep_str_callgraph_table, max_workers=4):
    ret_dfs = []
    overhead = {}
    ts = time.time()
    
    # Group by "trace_id"
    grouped = given_df.groupby("trace_id")
    if "groupby" not in overhead:
        overhead["groupby"] = 0
    overhead["groupby"] += time.time() - ts
    
    # Function to process each single trace
    def process_single_trace(tid, single_trace):
        local_overhead = {}
        single_trace = single_trace.copy()  # Avoid modifying the original grouped DataFrame
        if "single_trace.copy" not in local_overhead:
            local_overhead["single_trace.copy"] = 0
        ts = time.time()
        local_overhead["single_trace.copy"] += time.time() - ts
        
        ret = stitch_trace_in_df(single_trace, local_overhead, ep_str_callgraph_table)
        return tid, single_trace if ret else None, local_overhead

    # Concurrent execution
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_trace = {
            executor.submit(process_single_trace, tid, single_trace): tid
            for tid, single_trace in grouped
        }
        
        for future in as_completed(future_to_trace):
            tid = future_to_trace[future]
            try:
                tid, result, local_overhead = future.result()
                if result is not None:
                    ret_dfs.append(result)
                # Merge local overhead into the global overhead
                for key, value in local_overhead.items():
                    if key not in overhead:
                        overhead[key] = 0
                    overhead[key] += value
            except Exception as e:
                logger.error(f"Error processing trace {tid}: {e}")
    
    # Concatenate the resulting DataFrames
    ts = time.time()
    ret_df = pd.concat(ret_dfs, ignore_index=True) if ret_dfs else pd.DataFrame()
    if "concat" not in overhead:
        overhead["concat"] = 0
    overhead["concat"] += time.time() - ts
    
    # Log overhead information
    for key in overhead:
        logger.info(f"stitch_time_in_df/{key} took {int(overhead[key])}s")
    return ret_df

##################################################################
##################################################################


def stitch_time_in_df(given_df, ep_str_callgraph_table):
    ret_dfs = []
    overhead = {}
    ts = time.time()
    grouped = given_df.groupby("trace_id")
    if "groupby" not in overhead:
        overhead["groupby"] = 0
    overhead["groupby"] += time.time()-ts
    for tid, single_trace in grouped:
        ts = time.time()
        single_trace = single_trace.copy()  # Avoid modifying the original grouped DataFrame
        if "single_trace.copy" not in overhead:
            overhead["single_trace.copy"] = 0
        overhead["single_trace.copy"] += time.time()-ts
        ret = stitch_trace_in_df(single_trace, overhead, ep_str_callgraph_table)
        if ret:
            ret_dfs.append(single_trace)
        else:
            logger.debug(f"stitch_trace failed for trace {tid}")
    ts = time.time()
    ret_df = pd.concat(ret_dfs, ignore_index=True) if ret_dfs else pd.DataFrame()
    if "concat" not in overhead:
        overhead["concat"] = 0
    overhead["concat"] += time.time()-ts
    for key in overhead:
        logger.info(f"stitch_time_in_df/{key} took {int(overhead[key])}s")
    return ret_df

def stitch_trace_in_df(single_trace, overhead, ep_str_callgraph_table):
    ts = time.time()
    single_trace = single_trace.sort_values(by=["st"])
    single_trace = single_trace.reset_index(drop=True)
    if "sort" not in overhead:
        overhead["sort"] = 0
    overhead["sort"] += time.time()-ts
    
    ts = time.time()
    root_ep_str = None
    for _, row in single_trace.iterrows():
        if row["svc_name"] == "sslateingress":
            root_ep_str = row['endpoint']
            break
    if not root_ep_str:
        logger.error(f"Cannot find root endpoint in callgraph")
        logger.error(f"single_trace: {single_trace}")
        return False
    if "findroot" not in overhead:
        overhead["findroot"] = 0
    overhead["findroot"] += time.time()-ts
    
    ts = time.time()
    relative_time_ret = change_to_relative_time_in_df(single_trace)
    overhead["relativetime"] = overhead.get("relativetime", 0) + time.time()-ts
    
    ts = time.time()
    ## Bottleneck
    xt_ret = calc_exclusive_time_in_df(single_trace, ep_str_callgraph_table, overhead)
    overhead["exclusvietime"] = overhead.get("exclusivetime", 0) + time.time()-ts
    
    ct_ret = True
    if xt_ret == False:
        return False
    if ct_ret == False:
        return False
    if relative_time_ret == False:
        return False
    return True

def change_to_relative_time_in_df(single_trace):
    root_span = single_trace[single_trace["svc_name"] == "sslateingress"]
    if root_span.empty:
        return False
    # base_t = root_span["st"].values[0]
    # single_trace["st"] -= base_t
    # single_trace["et"] -= base_t
    invalid_times = (single_trace["st"] < 0) | (single_trace["et"] < single_trace["st"])
    if invalid_times.any():
        return False
    return True

# def calc_exclusive_time_in_df(single_trace):
#     # Step 1: Precompute child relationships for faster access
#     span_to_children = (
#         single_trace.groupby("parent_span_id")["span_id"]
#         .apply(list)
#         .to_dict()
#     )

#     single_trace["xt"] = single_trace["rt"]  # Initialize exclusive time as runtime

#     for idx, parent_span in single_trace.iterrows():
#         child_span_ids = span_to_children.get(parent_span["span_id"], [])
#         if not child_span_ids:
#             exclude_child_rt = 0
#         else:
#             child_spans = single_trace[single_trace["span_id"].isin(child_span_ids)]
#             exclude_child_rt = calculate_exclude_child_rt_in_df(child_spans)

#         single_trace.at[idx, "xt"] = parent_span["rt"] - exclude_child_rt
#         if single_trace.at[idx, "xt"] < 0:
#             return False

#     return True

def calculate_exclude_child_rt_in_df(child_spans):
    exclude_child_rt = 0
    relationship = 0
    sum_rt = 0
    max_rt = 0
    for i in range(len(child_spans)):
        sum_rt += child_spans.iloc[i]["rt"]
        max_rt = max(max_rt, child_spans.iloc[i]["rt"])
        # for j in range(i + 1, len(child_spans)):
        #     temp = is_parallel_execution_in_df(child_spans.iloc[i], child_spans.iloc[j])
        #     relationship = max(relationship, temp)  
    if relationship == 2:
        exclude_child_rt = max_rt        
    elif relationship == 1:
        exclude_child_rt = max_rt        
        # exclude_child_rt = sum_rt
    else:
        exclude_child_rt = 0
    return exclude_child_rt

############################################################
# def calc_exclusive_time_in_df(single_trace):
#     # Step 1: Precompute child relationships for faster access
#     span_to_children = (
#         single_trace.groupby("parent_span_id")["span_id"]
#         .apply(list)
#         .to_dict()
#     )
#     single_trace["xt"] = single_trace["rt"]  # Initialize exclusive time as runtime
#     for parent_span_id, child_span_ids in span_to_children.items():
#         if not child_span_ids:
#             continue

#         parent_span = single_trace[single_trace["span_id"] == parent_span_id]
#         if parent_span.empty:
#             continue
#         child_spans = single_trace[single_trace["span_id"].isin(child_span_ids)]
#         if child_spans.empty:
#             continue
#         exclude_child_rt = calculate_exclude_child_rt_in_df_optimized(child_spans)
#         parent_rt = parent_span["rt"].values[0]
#         exclusive_time = parent_rt - exclude_child_rt
#         if exclusive_time < 0:
#             return False
#         single_trace.loc[single_trace["span_id"] == parent_span_id, "xt"] = exclusive_time
#     return True

# def calculate_exclude_child_rt_in_df_optimized(child_spans):
#     if child_spans.empty:
#         return 0
#     child_spans = child_spans.sort_values("st")
#     merged_intervals = []
#     current_start = child_spans.iloc[0]["st"]
#     current_end = child_spans.iloc[0]["et"]
#     for idx in range(1, len(child_spans)):
#         span = child_spans.iloc[idx]
#         if span["st"] <= current_end:
#             # Overlapping interval, extend the current interval
#             current_end = max(current_end, span["et"])
#         else:
#             # No overlap, add the current interval to the list
#             merged_intervals.append((current_start, current_end))
#             current_start = span["st"]
#             current_end = span["et"]
#     merged_intervals.append((current_start, current_end))
#     exclude_child_rt = sum(end - start for start, end in merged_intervals)
#     return exclude_child_rt
############################################################

def get_child_spans(single_trace, parent_span, ep_str_callgraph_table):
    child_spans = []
    for _, row in single_trace.iterrows():
        if row["parent_span_id"] == parent_span["span_id"]:
            child_spans.append(row)
    return pd.DataFrame(child_spans)

def calc_exclusive_time_in_df(single_trace, ep_str_callgraph_table, overhead):
    for _, parent_span in single_trace.iterrows():
        ts = time.time()
        child_spans = single_trace[single_trace["parent_span_id"] == parent_span["span_id"]]
        # child_spans = get_child_spans(single_trace, parent_span, ep_str_callgraph_table)
        overhead["child_spans"] = overhead.get("child_spans", 0) + (time.time() - ts)
        if child_spans.empty:
            exclude_child_rt = 0
        else:
            ts = time.time()
            # exclude_child_rt = calculate_exclude_child_rt_in_df(child_spans)
            row_with_max_rt = child_spans.loc[child_spans["rt"].idxmax()]
            exclude_child_rt = row_with_max_rt["rt"]
            overhead["child_rt"] = overhead.get("child_rt", 0) + (time.time() - ts)
        #######################################################
        # parent_span["xt"] = parent_span["rt"] - exclude_child_rt
        parent_span["xt"] = parent_span["rt"]
        #######################################################
        # logger.info(f"parent,{parent_span['svc_name']}, parent_rt: {parent_span['rt']}, exclude_child_rt: {exclude_child_rt}, parent_xt: {parent_span['xt']}")
        if parent_span["xt"] < 0:
            return False
    return True

# def calculate_exclude_child_rt_in_df(child_spans):
#     exclude_child_rt = 0
#     for i in range(len(child_spans)):
#         for j in range(i + 1, len(child_spans)):
#             if is_parallel_execution_in_df(child_spans.iloc[i], child_spans.iloc[j]):
#                 exclude_child_rt = max(child_spans.iloc[i]["rt"], child_spans.iloc[j]["rt"])
#                 # exclude_child_rt = max(child_spans.iloc[i]["et"], child_spans.iloc[j]["et"]) - min(child_spans.iloc[i]["st"], child_spans.iloc[j]["st"])
#             else:
#                 # exclude_child_rt = child_spans.iloc[i]["rt"] + child_spans.iloc[j]["rt"]
#                 exclude_child_rt = child_spans.iloc[i]["rt"] + child_spans.iloc[j]["rt"]
#     return exclude_child_rt


## 2
def is_parallel_execution_in_df(span_a, span_b):
    if span_a["et"] > span_b["st"] and span_b["et"] > span_a["st"] or span_b["et"] > span_a["st"] and span_a["et"] > span_b["st"]:
        if (span_a["st"] < span_b["st"] and span_a["et"] > span_b["et"]) or (span_b["st"] < span_a["st"] and span_b["et"] > span_a["et"]):
            return 1  # Fully nested
        else:
            return 2  # Partially overlapping
    return 0  # No overlap

## 1
# def is_parallel_execution_in_df(span_a, span_b):
#     if span_a["st"] < span_b["st"]:
#         earlier_start_span = span_a
#         later_start_span = span_b
#     else:
#         earlier_start_span = span_b
#         later_start_span = span_a
#     if earlier_start_span["et"] > later_start_span["st"] and later_start_span["et"] > earlier_start_span["st"]:
#         if earlier_start_span["st"] < later_start_span["st"] and earlier_start_span["et"] > later_start_span["et"]:
#             return 1
#         else:
#             return 2
#     else:
#         return 0


def stitch_time(given_traces):
    ret_traces = {}
    num_fail = {}
    overhead = {"callgraph": 0, "findroot": 0, "relativetime": 0, "exclusivetime": 0, "child_spans": 0}
    for region, loads in given_traces.items():
        region_traces = ret_traces.setdefault(region, {})
        for load_bucket, tids in loads.items():
            load_traces = region_traces.setdefault(load_bucket, {})
            for tid, single_trace in tids.items():
                ret = stitch_trace(single_trace, tid, overhead)
                if ret == True:
                    load_traces[tid] = single_trace
                else:
                    logging.debug(f"stitch_trace failed for trace {tid}")
                    if ret not in num_fail:
                        num_fail[ret] = 0
                    num_fail[ret] += 1
    logger.info(f"stitch_time, overhead: {overhead}")
    return ret_traces, num_fail


def stitch_trace(single_trace, tid, overhead):
    # ts = time.time()
    # ep_str_cg = single_trace_to_endpoint_str_callgraph(single_trace)
    # temp["callgraph"] = time.time()-ts
    # ts = time.time()
    # root_ep_str = opt_func.find_root_node(ep_str_cg)
    ts = time.time()
    root_ep_str = None
    for span in single_trace['span']:
        if span.svc_name == "sslateingress":
            root_ep_str = span.endpoint_str
            break
    if not root_ep_str:
        logger.error(f"Cannot find root endpoint in callgraph")
        return "too many root", [] # too many root nodes or no root node
    overhead["findroot"] = time.time()-ts
    ts = time.time()
    relative_time_ret = change_to_relative_time(single_trace, tid)
    overhead["relativetime"] = time.time()-ts
    ts = time.time()
    xt_ret = calc_exclusive_time(single_trace)
    overhead["exclusivetime"] = time.time()-ts
    ct_ret = True
    if xt_ret == False:
        return "negative_exclusive_time"
    if ct_ret == False:
        return "negative_critical_tim"
    if relative_time_ret == False:
        return "negative_relative_time"
    return True

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


def change_to_relative_time(single_trace, tid):
    # sp_cg = single_trace_to_span_callgraph(single_trace)
    # root_span = opt_func.find_root_node(sp_cg)
    root_span = None
    for span in single_trace['span']:
        if span.svc_name == "sslateingress":
            root_span = span
            break
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
        if parent_span.xt < 0:
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