#!/usr/bin/env python
# coding: utf-8

import time
import global_controller as global_con
from global_controller import app
# from config import *
from config import *
# import config as cf
import span as sp
import pandas as pd
from IPython.display import display
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
    # cid -> trace id -> svc_name -> span
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
                                    traces_[cid][tid][service_name] = span
                                else:
                                    print(service_name + " already exists in trace["+tid+"]")
                                    assert False
                                # print(str(span.my_span_id) + " is added to " + tid + "len, "+ str(len(traces_[tid])))
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
    span_id = row["my_span_id"][:8] # NOTE
    parent_span_id = row["parent_span_id"][:8] # NOTE
    st = row["st"]
    et = row["et"]
    
    
    load = row["load"]
    last_load = row["last_load"]
    avg_load = row["avg_load"]
    rps = row["rps"]
    
    ########################
    # load = row["avg_load"] 
    ########################
    
    
    callsize = row["call_size"]
    span = sp.Span(svc, cluster_id, trace_id, span_id, parent_span_id, st, et, load, last_load, rps, callsize)
    return span

def trace_trimmer(trace_file):
    df = pd.read_csv(trace_file)
    col_len = df.shape[1]
    if col_len == 14:
        col_name = ['a', 'b', "trace_id","svc_name","cluster_id","my_span_id","parent_span_id","load","last_load","avg_load","st","et","rt","call_size"]
    elif col_len == 14:
        col_name = ['a', 'b', "trace_id","svc_name","cluster_id","my_span_id","parent_span_id","load","last_load","avg_load", "rps", "st","et","rt","call_size"]
    else:
        print("ERROR trace_trimmer, invalid column length, ", col_len)
        assert False
    df.columns = col_name
    # if 'a' in df.columns:
    df = df.drop('a', axis=1)
    # if 'b' in df.columns:
    df = df.drop('b', axis=1)
    df.fillna("", inplace=True)
    df['avg_load'] = df['avg_load'].clip(lower=1)
    df['last_load'] = df['last_load'].clip(lower=1)
    df['load'] = df['load'].clip(lower=1)
    return df

def parse_trace_file_ver2(log_path):
    # colname =  ["trace_id","svc_name","cluster_id","my_span_id","parent_span_id","load","st","et","rt","call_size"]
    # temp_df = pd.read_csv(log_path, names=colname)
    # temp_df.fillna("", inplace=True)
    # temp_df['load'] = temp_df['load'].clip(lower=1)
    df = trace_trimmer(log_path)
    # display(df)
    # temp_df = df[df["load"] != df["last_load"]]
    # display(temp_df)
    traces_ = dict() # cluster_id -> trace id -> svc_name -> span
    for cid in range(NUM_CLUSTER):
        for index, row in df.iterrows():
            span = create_span_ver2(row)
            span.cluster_id = cid
            if span.cluster_id not in traces_:
                traces_[span.cluster_id] = dict()
            if span.trace_id not in traces_[span.cluster_id]:
                traces_[span.cluster_id][span.trace_id] = dict()
            if span.svc_name not in traces_[span.cluster_id][span.trace_id]:
                traces_[span.cluster_id][span.trace_id][span.svc_name] = span
            else:
                print(span.svc_name + " already exists in trace["+span.trace_id+"]")
    # for cid in traces_:
    #     for trace_id, single_trace in traces_[cid].items():
    #         for svc, span in single_trace.items():
    #             print(span)
    return traces_

FRONTEND_svc = "productpage-v1"
span_id_of_FRONTEND_svc = ""
REVIEW_V1_svc = "reviews-v1"
REVIEW_V2_svc = "reviews-v2"
REVIEW_V3_svc = "reviews-v3"
RATING_svc = "ratings-v1"
DETAIL_svc = "details-v1"
###############################
FILTER_REVIEW_V1 = True # False
FILTER_REVIEW_V2 = True # False
FILTER_REVIEW_V3 = False# False
###############################
# ratings-v1 and reviews-v1 should not exist in the same trace
MIN_TRACE_LEN = 3
MAX_TRACE_LEN = 4
def remove_incomplete_trace(traces_):
    ret_traces_ = dict()
    what = [0]*9
    weird_span_id = 0
    for cid in traces_:
        if cid not in ret_traces_:
            ret_traces_[cid] = dict()
        for tid, single_trace in traces_[cid].items():
            if FRONTEND_svc not in single_trace or DETAIL_svc not in single_trace:
                if FRONTEND_svc not in single_trace:
                    print("no frontend")
                if DETAIL_svc not in single_trace:
                    print("no detail")
                print(f"single_trace: {single_trace}")
                for svc, span in single_trace.items():
                    print(svc, " ")
                    print(span)
                print()
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


# def append_arbitrary_cluster_id_to_spans(traces_):
#     i = 0 # NOTE: idx i will be used to give arbitrary cluster id to each span
#     for cid, trace in traces_.items():
#         for tid, single_trace in traces_[cid].items():
#             cid = i%NUM_CLUSTER
#             i += 1
#             for svc, span in single_trace.items():
#                 span.cluster_id = cid
#     return traces_

def change_to_relative_time(traces_):
    for cid, trace in traces_.items():
        for tid, single_trace in traces_[cid].items():
            try:
                base_t = single_trace[FRONTEND_svc].st
            except Exception as error:
                # print(tid + " does not have " + FRONTEND_svc + ". Skip this trace")
                # for _, span in single_trace.items():
                #     print(span)
                print(error)
                exit()
            for svc, span in single_trace.items():
                span.st -= base_t
                span.et -= base_t
                assert span.st >= 0
                assert span.et >= 0
                assert span.et >= span.st
    return traces_


def print_single_trace(single_t):
    app.logger.debug(f"{log_prefix} print_sinelg_trace")
    for _, span in single_t.items():
        app.logger.debug(f"{log_prefix} {span}")

def print_dag(single_dag_):
    for parent_span, children in single_dag_.items():
        for child_span in children:
            print("{}({})->{}({})".format(parent_span.svc_name, parent_span.my_span_id, child_span.svc_name, child_span.my_span_id))
            
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
callgraph:
    - key: parent service name
    - value: list of child service names
'''
def single_trace_to_callgraph(single_trace_):
    callgraph = dict()
    svc_list = list()
    for _, parent_span in single_trace_.items():
        svc_list.append(parent_span.svc_name)
        callgraph[parent_span.svc_name] = list()
        for _, span in single_trace_.items():
            if span.parent_span_id == parent_span.my_span_id:
                callgraph[parent_span.svc_name].append(span.svc_name)
                parent_span.child_spans.append(span)
        # if len(callgraph[parent_span.svc_name]) == 0:
            # del callgraph[parent_span.svc_name]
    svc_list.sort()
    key_ = ""
    for svc in svc_list:
        key_ += svc+","
    # for svc, span in single_trace_.items():
    #     print(f"{span}")
    # print(f"single_trace_to_callgraph, callgraph, {callgraph}")
    return callgraph, key_


def traces_to_graphs(traces_):
    graph_dict = dict()
    for cid, trace in traces_.items():
        if cid not in graph_dict:
            graph_dict[cid] = dict()
        for tid, single_trace in traces_[cid].items():
            callgraph, cg_key = single_trace_to_callgraph(single_trace)
            graph_dict[cid][cg_key] = callgraph
            # break
            # print(f"tid: {tid}, callgraph: {callgraph}, cg_key: {cg_key}")
        app.logger.debug(f"{log_prefix} Cluster {cid} Graph dict: {graph_dict[cid]}")
        app.logger.debug(f"{log_prefix} Call graph: {callgraph}")
        assert len(graph_dict[cid]) == 1
    return callgraph, graph_dict
    

def exclusive_time(single_trace_):
    for svc, parent_span in single_trace_.items():
        child_span_list = list()
        for svc, span in single_trace_.items():
            if span.parent_span_id == parent_span.my_span_id:
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
        app.logger.debug(f"{log_prefix} Service: {parent_span.svc_name}, Response time: {parent_span.rt}, Exclude_child_rt: {exclude_child_rt}, Exclusive time: {parent_span.xt}")
        if parent_span.xt < 0.0:
            print(f"parent_span,{parent_span.svc_name} exclusive time cannot be negative value: {parent_span.xt}")
            print(f"st,{parent_span.st}, et,{parent_span.et}, rt,{parent_span.rt}, xt,{parent_span.xt}")
            assert False
        # if parent_span.svc_name == FRONTEND_svc:
        assert parent_span.xt >= 0.0
        ###########################################
        # if parent_span.svc_name == FRONTEND_svc:
        #     parent_span.xt = parent_span.rt
        # else:
        #     parent_span.xt = 0
        ###########################################
    return single_trace_


def calc_exclusive_time(traces_):
    for cid, trace in traces_.items():
        for tid, single_trace in traces_[cid].items():
            single_trace_ex_time = exclusive_time(single_trace)


def print_all_trace(traces_):
    for cid in traces_:
        for tid, single_trace in traces_[cid].items():
            app.logger.debug(f"{log_prefix} ======================= ")
            app.logger.debug(f"{log_prefix} Trace: " + tid)
            for svc, span in single_trace.items():
                app.logger.debug(f"{log_prefix} {span}")
            app.logger.debug(f"{log_prefix} ======================= ")


def inject_arbitrary_callsize(traces_, depth_dict):
    for cid in traces_:
        for tid, single_trace in traces_[cid].items():
            for svc, span in single_trace.items():
                span.depth = depth_dict[svc]
                span.call_size = depth_dict[svc]*10


def product_page_only(traces_):
    pp_only_traces = dict()
    for cid, trace in traces_.items():
        if cid not in pp_only_traces:
            pp_only_traces[cid] = dict()
        for tid, single_trace in traces_[cid].items():
            for svc, span in single_trace.items():
                temp_trace = dict()
                if svc == FRONTEND_svc:
                    temp_trace[svc] = span
                if len(temp_trace) > 0:
                    pp_only_traces[cid][tid] = temp_trace
    return pp_only_traces


def print_graph_dict(gd):
    for cid in gd:
        for k, cg in gd[cid].items():
            print(f"{log_prefix} graph key: {k}")
            for parent_svc, children in cg.items():
                for child_svc in children:
                    print(f"{log_prefix} {parent_svc} -> {child_svc}")


def set_depth_of_span(cg, parent_svc, children, depth_d, prev_dep):
    if len(children) == 0:
        # print(f"{log_prefix} Leaf service {parent_svc}, Escape recursive function")
        return
    for child_svc in children:
        if child_svc not in depth_d:
            depth_d[child_svc] = prev_dep + 1
            # print(f"{log_prefix} Service {child_svc}, depth, {depth_d[child_svc]}")
        set_depth_of_span(cg, child_svc, cg[child_svc], depth_d, prev_dep+1)


def critical_path_analysis(parent_span):
    sorted_children = sorted(parent_span.child_spans, key=lambda x: x.et, reverse=True)
    if len(parent_span.critical_child_spans) != 0:
        app.logger.debug(f"{log_prefix} critical_path_analysis, {parent_span}")
        app.logger.debug(f"{log_prefix} critical_path_analysis, critical_child_spans:", end="")
        for ch_sp in parent_span.critical_child_spans:
            app.logger.debug(f"{log_prefix} {ch_sp}")
    cur_end_time = parent_span.et
    total_critical_children_time = 0
    for child_span in sorted_children:
        if child_span.et < cur_end_time:
            parent_span.critical_child_spans.append(child_span)
            total_critical_children_time += child_span.rt
            cur_end_time = child_span.st
    parent_span.ct = parent_span.rt - total_critical_children_time
    assert parent_span.ct >= 0.0
    # print(" ==== " + str(parent_span) + " ==== ")
    # for child_span in sorted_children:
    #     print(child_span)


def analyze_critical_path_time(traces_):
    print(f"{log_prefix} Critical Path Analysis")
    for cid in traces_:
        for tid, single_trace in traces_[cid].items():
            for svc, span in single_trace.items():
                critical_path_analysis(span)


def traces_to_df(traces_):
    list_of_unfold_span = list()
    colname = list()
    for cid in traces_:
        for tid, single_trace in traces_[cid].items():
            for svc, span in single_trace.items():
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


def stitch_time(traces):
    app.logger.info(f"{log_prefix} time stitching starts")
    ts = time.time()
    ###################################################
    input_trace_len = dict()
    for cid in traces:
        input_trace_len[cid] = len(traces[cid])
    traces = remove_incomplete_trace(traces)
    # traces = append_arbitrary_cluster_id_to_spans(traces)
    traces = change_to_relative_time(traces)
    if global_con.PRODUCTPAGE_ONLY:
        traces = product_page_only(traces)
    calc_exclusive_time(traces)
    call_graph, graph_dict = traces_to_graphs(traces)
    depth_dict = dict()
    for parent_svc, children in call_graph.items():
        if parent_svc == FRONTEND_svc:
            frontend_depth = 1
            depth_dict[parent_svc] = 1
            set_depth_of_span(call_graph, parent_svc, children, depth_dict, frontend_depth)
    print(f"call_graph: {call_graph}")
    print(f"depth_dict: {depth_dict}")
    inject_arbitrary_callsize(traces, depth_dict)
    analyze_critical_path_time(traces)
    

    df = traces_to_df(traces)    
    # print("dfdf")
    # display(df)
    
    # print("temp_df")
    # temp_df = df[df["xt"] <= 0.0]
    # zero_xt_svc = temp_df["svc_name"].unique()
    # print("zero_xt_svc, ", zero_xt_svc)
    # temp_df.reset_index(drop=True)
    # display(temp_df)
    
    print_all_trace(traces)
    for cid in traces:
        app.logger.info(f"{log_prefix} Cluster {cid} Num Input traces: {input_trace_len[cid]}")
        app.logger.info(f"{log_prefix} Cluster {cid} Num Final valid traces: {len(traces[cid])}")
    app.logger.info(f"{log_prefix} time stitching done: {time.time() - ts}s")
    return traces, call_graph, depth_dict, df
    ###################################################

# if __name__ == "__main__":
#     traces = parse_trace_file
#     traces, call_graph, depth_dict = stitch_time(traces)
