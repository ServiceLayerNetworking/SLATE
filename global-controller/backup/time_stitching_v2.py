#!/usr/bin/env python
# coding: utf-8

import time
from pprint import pprint
from global_controller import app

# LOG_PATH = "./call-logs-sept-13.txt"
# LOG_PATH = "./trace_and_load_log.txt"
LOG_PATH = "./modified_trace_and_load_log.txt"
# LOG_PATH = "./call-logs-sept-16.txt"

PRODUCTPAGE_ONLY = True
VERBOSITY=0
intra_cluster_network_rtt = 1
inter_cluster_network_rtt = 1.001

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
        
def print_error(msg):
    exit_time = 1
    print("[ERROR] " + msg)
    print("EXIT PROGRAM in")
    for i in reversed(range(exit_time)) :
        print("{} seconds...".format(i))
        time.sleep(1)
    assert False

def file_read(path_):
    f = open(path_, "r")
    lines = f.readlines()
    return lines


# class Span:
#     def __init__(self, svc, my_span_id, parent_span_id, start, end, load, cluster_id):
#         self.svc_name = svc
#         self.child_spans = list()
#         self.cluster_id = cluster_id
#         self.name_cid = self.svc_name+"#"+str(self.cluster_id)
#         self.root = (parent_span_id=="")
        
#         self.my_span_id = my_span_id
#         self.parent_span_id = parent_span_id
        
#         self.request_size_in_bytes = 10 # parent_span to this span
        
#         self.start = start
#         self.end = end
#         self.rt = end - start
#         self.xt = 0
#         self.load = load
    
#     def print(self):
#         print("SPAN,{},{},{}->{},{},{},{},{},{}".format(self.svc_name, self.cluster_id, self.parent_span_id, self.my_span_id, self.start, self.end, self.rt, self.xt, self.load))

# <Trace Id> <Span Id> <Parent Span Id> <Start Time> <End Time>
# <Parent Span Id> will not exist for the frontend service. e.g., productpage service in bookinfo
# min len of tokens = 4

SPAN_DELIM = " "

if LOG_PATH == "./call-logs-sept-16.txt":
    SPAN_TOKEN_LEN = 6
else:
    SPAN_TOKEN_LEN = 5

# def parse_and_create_span(line, svc, load):
#     tokens = line.split(SPAN_DELIM)
#     if len(tokens) != SPAN_TOKEN_LEN:
#         print_error("Invalid token length in span line. len(tokens):{}, line: {}".format(len(tokens), line))
#     tid = tokens[0]
#     sid = tokens[1]
#     psid = tokens[2]
#     start = int(tokens[3])
#     end = int(tokens[4])
#     span = Span(svc, sid, psid, start, end, load, -1)
#     return tid, span

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
FILTER_REVIEW_V3 = False # False
###############################
# ratings-v1 and reviews-v1 should not exist in the same trace
MIN_TRACE_LEN = 3
MAX_TRACE_LEN = 4
def remove_incomplete_trace(traces_):
    what = [0]*9
    ret_traces_ = dict()
    removed_traces_ = dict()
    input_trace_len = 0
    # cid -> trace id -> svc -> span
    for cid, trace in traces_.items():
        ret_traces_[cid] = dict()
        removed_traces_[cid] = dict()
        input_trace_len += len(traces_[cid])
        for tid, single_trace in traces_[cid].items():
            # app.logger.info(f"trace: {single_trace.keys()}")
            if FRONTEND_svc not in single_trace or DETAIL_svc not in single_trace:
                if FRONTEND_svc not in single_trace:
                    app.logger.info("no frontend")
                if DETAIL_svc not in single_trace:
                    app.logger.info("no detail")
                removed_traces_[cid][tid] = single_trace
                # for svc, sp in single_trace.items():
                #     print(svc, " ")
                #     print(sp)
                # print()
                what[0] += 1
            elif len(single_trace) < MIN_TRACE_LEN:
                removed_traces_[cid][tid] = single_trace
                what[1] += 1
            elif len(single_trace) > MAX_TRACE_LEN:
                removed_traces_[cid][tid] = single_trace
                what[2] += 1
            elif len(single_trace) == MIN_TRACE_LEN and (REVIEW_V1_svc not in single_trace or REVIEW_V2_svc in single_trace or REVIEW_V3_svc in single_trace):
                removed_traces_[cid][tid] = single_trace
                what[3] += 1
            elif len(single_trace) == MAX_TRACE_LEN and REVIEW_V2_svc not in single_trace and REVIEW_V3_svc not in single_trace:
                removed_traces_[cid][tid] = single_trace
                what[4] += 1
            elif single_trace[FRONTEND_svc].parent_span_id != span_id_of_FRONTEND_svc:
                removed_traces_[cid][tid] = single_trace
                what[5] += 1
            elif FILTER_REVIEW_V1 and REVIEW_V1_svc in single_trace:
                if len(single_trace) != 3:
                    print_single_trace(single_trace)
                assert len(single_trace) == 3
                removed_traces_[cid][tid] = single_trace
                what[6] += 1
            elif FILTER_REVIEW_V2 and REVIEW_V2_svc in single_trace:
                if len(single_trace) != 4:
                    print_single_trace(single_trace)
                assert len(single_trace) == 4
                removed_traces_[cid][tid] = single_trace
                what[7] += 1
            elif FILTER_REVIEW_V3 and REVIEW_V3_svc in single_trace:
                if len(single_trace) != 4:
                    print_single_trace(single_trace)
                assert len(single_trace) == 4
                removed_traces_[cid][tid] = single_trace
                what[8] += 1
            else:
                # app.logger.info("complete trace: " + str(single_trace))
                ret_traces_[cid][tid] = single_trace
    app.logger.info(f"[SLATE] Incomplete trace filter stats: {what}")
    # app.logger.info(ret_traces_.keys())
    # assert input_trace_len == ( len(ret_traces_[0]) + len(ret_traces_[1]) + len(removed_traces_[0]) + len(removed_traces_[0]) )
    # app.logger.info("#input trace: " + str(input_trace_len))

    # for cid, trace in ret_traces_.items():
    #     app.logger.info("#returned trace for cid {}: {}".format(cid, len(ret_traces_[cid])))
    # for cid, trace in removed_traces_.items():
    #     app.logger.info("#removed for cid {}: {}".format(cid, len(removed_traces_[cid])))

    return ret_traces_, removed_traces_

def change_to_relative_time(traces_):
    for cid, trace in traces_.items():
        for tid, single_trace in traces_[cid].items():
            for svc, span in traces_[cid][tid].items():
                if svc == FRONTEND_svc:
                    base_t = span.start
            for svc, span in traces_[cid][tid].items():
                span.start -= base_t
                span.end -= base_t
    return traces_


def print_single_trace(single_trace):
    for svc, span in single_trace.items():
        print(span)

def print_dag(single_dag_):
    for parent_span, children in single_dag_.items():
        for child_span in children:
            print("{}({})->{}({})".format(parent_span.svc_name, parent_span.my_span_id, child_span.svc_name, child_span.my_span_id))
            
'''
parallel-1
    ----------------------A
        -----------B
           -----C
parallel-2
    ----------------------A
        --------B
             ---------C
'''
def is_parallel_execution(span_a, span_b):
    assert span_a.parent_span_id == span_b.parent_span_id
    if span_a.start < span_b.start:
        earlier_start_span = span_a
        later_start_span = span_b
    else:
        earlier_start_span = span_b
        later_start_span = span_a
    if earlier_start_span.end > later_start_span.start and later_start_span.end > earlier_start_span.start: # parallel execution
        if earlier_start_span.start < later_start_span.start and earlier_start_span.end > later_start_span.end: # parallel-1
            return 1
        else: # parallel-2
            return 2
    else: # sequential execution
        return 0
    

def single_trace_to_callgraph(single_trace_):
    callgraph = dict()
    svc_list = list()
    for _, parent_span in single_trace_.items():
        svc_list.append(parent_span.svc_name)
        callgraph[parent_span.svc_name] = list()
        for _, span in single_trace_.items():
            if span.parent_span_id == parent_span.my_span_id:
                callgraph[parent_span.svc_name].append(span.svc_name)
        # if len(callgraph[parent_span.svc_name]) == 0:
            # del callgraph[parent_span.svc_name]
    svc_list.sort()
    key_ = ""
    for svc in svc_list:
        key_ += svc+","
    return callgraph, key_

                
def calc_exclusive_time(single_trace_):
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
                        # print("parent: {}, child_1: {}, child_2: {}, parallel-{} sibling".format(parent_span.svc_name, child_span_list[i].svc_name, child_span_list[j].svc_name, is_parallel))
                    else: # sequential execution
                        exclude_child_rt = child_span_list[i].rt + child_span_list[j].rt
                        # print("parent: {}, child_1:{}, child_2: {}, sequential sibling".format(parent_span.svc_name, child_span_list[i].svc_name, child_span_list[j].svc_name))
        parent_span.xt = parent_span.rt - exclude_child_rt
        # app.logger.info(f"Service: {parent_span.svc_name}, Exclusive time: {parent_span.xt}")
        if parent_span.xt < 0.0:
            print_error("parent_span exclusive time cannot be negative value: {}".format(parent_span.xt))
        if parent_span.svc_name == FRONTEND_svc:
            assert parent_span.xt > 0.0
            
        ###########################################
        if parent_span.svc_name == FRONTEND_svc:
            parent_span.xt = parent_span.rt
        else:
            parent_span.xt = 0
        ###########################################
        
    return single_trace_


def traces_to_graphs_and_calc_exclusive_time(traces_):
    graph_dict = dict()
    for cid, trace in traces_.items():
        # app.logger.info(f"cid: {cid}, trace: {trace}")
        for tid, single_trace in traces_[cid].items():
            # single_trace = traces_[cid][tid]
            callgraph, cg_key = single_trace_to_callgraph(single_trace)
            # app.logger.info(f"tid: {tid}, callgraph: {callgraph}, cg_key: {cg_key}")
            single_trace_ex_time = calc_exclusive_time(single_trace)
            graph_dict[cg_key] = callgraph
    # app.logger.info(f"len: {len(graph_dict)}, graph_dict: {graph_dict}")
    assert len(graph_dict) == 1
    return callgraph


# def add_child_services(graph_dict_):
#     for tid in graph_dict_:
#         dag = graph_dict_[tid]
#         for parent_span, children in dag.items():
#             for child_span in children:
#                 parent_span.child_spans.append(child_span)

# def get_unique_dag_list(graph_dict_):
#     unique_dags = dict()
#     for _, dag in graph_dict_.items():
#         temp_list = list()
#         for parent_span, children in dag.items():
#             for child_span in children:
#                 temp_list.append((parent_span.svc_name + "," + child_span.svc_name))
#         temp_list.sort()
#         temp_str = ""
#         for elem in temp_list:
#             temp_str += elem + ","
#         if temp_str not in uni/que_dags:
#             unique_dags[temp_str] = dag
#     print(" --- unique dag list --- ")
#     i = 0
#     for _, dag in unique_dags.items():
#         print("unique dag #"+str(i))
#         print_dag(dag)
#         i += 1
#     return unique_dags

def get_unique_svc_names_from_dag(dag_):
    unique_svc_names = dict()
    for parent_span, children in dag_.items():
        for child_span in children:
            unique_svc_names[parent_span.svc_name] = "xxxx"
            unique_svc_names[child_span.svc_name] = "xxxx"
    return unique_svc_names

def stitch_time(traces):
    # print_log("time stitching starts")
    ts = time.time()
    traces, removed_traces = remove_incomplete_trace(traces)
    traces = change_to_relative_time(traces)
    
    ###################################################
    # cid -> trace id -> svc_name -> span
    pp_only_traces = dict()
    if PRODUCTPAGE_ONLY:
        for cid, trace in traces.items():
            if cid not in pp_only_traces:
                pp_only_traces[cid] = dict()
            for tid, single_trace in traces[cid].items():
                pp_single_trace = dict()
                for svc, span in single_trace.items():
                    if svc == FRONTEND_svc:
                        pp_single_trace[svc] = span
                assert FRONTEND_svc in pp_single_trace
                
                assert len(pp_single_trace) == 1
                if len(pp_single_trace) == 1:
                    if tid not in pp_only_traces[cid]:
                        pp_only_traces[cid][tid] = dict()
                    pp_only_traces[cid][tid] = pp_single_trace
                    
        assert len(pp_only_traces) > 0
        assert len(pp_only_traces[0]) > 0
        assert len(pp_only_traces[1]) > 0
        app.logger.info(f"productpage")
        traces = pp_only_traces
    ###################################################


    call_graph = traces_to_graphs_and_calc_exclusive_time(traces)
    # add_child_services(graph_dict)
    
    app.logger.info("==============TRACE===============")
    for cid, trace in traces.items():
        for tid, single_trace in traces[cid].items():
            for svc, span in single_trace.items():
                    if svc == FRONTEND_svc:
                        app.logger.info(f"[SLATE], SPAN, {span.svc_name}, xt,{span.xt}, rt,{span.rt}, load,{span.load}")
    app.logger.info("=================================")
    
    
    # print("*"*50)
    # for cid, trace in traces.items():
        # for tid, single_trace in traces[cid].items():
            # print("="*30)
            # print("Trace: " + tid)
            # for svc, span in single_trace.items():
            #     print(span)
            # print("="*30)
    # print()
    # print("num final valid traces: " + str(len(traces)))
    #
    print_log("time stitching done: {}s".format(time.time() - ts))
    return traces, call_graph

if __name__ == "__main__":
    traces, call_graph = stitch_time(LOG_PATH)