#!/usr/bin/env python
# coding: utf-8

import time
from pprint import pprint
from global_controller import app
# import global_controller as gc

# LOG_PATH = "./call-logs-sept-13.txt"
# LOG_PATH = "./trace_and_load_log.txt"
LOG_PATH = "./modified_trace_and_load_log.txt"
# LOG_PATH = "./call-logs-sept-16.txt"

PRODUCTPAGE_ONLY = False
VERBOSITY=0
intra_cluster_network_rtt = 1
inter_cluster_network_rtt = 2

""" Version 1 Trace example. It doesn't include call size
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


FRONTEND_svc = "productpage-v1"
REVIEW_V1_svc = "reviews-v1"
REVIEW_V2_svc = "reviews-v2"
REVIEW_V3_svc = "reviews-v3"
RATING_svc = "ratings-v1"
DETAIL_svc = "details-v1"
MIN_TRACE_LEN = 3
MAX_TRACE_LEN = 4

def record_reason(reason_, what_, remo_t_, cid_, tid_, single_t_):
    if reason_ not in what_:
        what_[reason_] = 0
    what_[reason_] += 1
    remo_t_[cid_][tid_] = single_t_
    
def remove_incomplete_trace_of_bookinfo(traces_):
    what = dict()
    ret_traces_ = dict()
    removed_traces_ = dict()
    input_trace_len = 0
    # traces:
    # cid -> trace id -> svc -> span
    for cid, trace in traces_.items():
        ret_traces_[cid] = dict()
        removed_traces_[cid] = dict()
        input_trace_len += len(traces_[cid])
        for tid, single_trace in traces_[cid].items():
            # single_trace: {"svc_a": span_obj, "svc_b":span_obj, ...}
            # len(single_trace): #service in the call graph
            if FRONTEND_svc not in single_trace or DETAIL_svc not in single_trace:
                if FRONTEND_svc not in single_trace:
                    record_reason("no_frontend", what, removed_traces_, cid, tid, single_trace)
                if DETAIL_svc not in single_trace:
                    record_reason("no_detail", what, removed_traces_, cid, tid, single_trace)
            elif len(single_trace) < MIN_TRACE_LEN:
                record_reason("shorter_than_min_trace_len", what, removed_traces_, cid, tid, single_trace)
            elif len(single_trace) > MAX_TRACE_LEN:
                record_reason("longer_than_max_trace_len", what, removed_traces_, cid, tid, single_trace)
            elif len(single_trace) == MIN_TRACE_LEN and (REVIEW_V1_svc not in single_trace or REVIEW_V2_svc in single_trace or REVIEW_V3_svc in single_trace):
                record_reason("len_3_but_no_review_v1", what, removed_traces_, cid, tid, single_trace)
            elif len(single_trace) == MAX_TRACE_LEN and REVIEW_V2_svc not in single_trace and REVIEW_V3_svc not in single_trace:
                record_reason("len_4_but_no_review_v2_or_v3", what, removed_traces_, cid, tid, single_trace)
            elif single_trace[FRONTEND_svc].parent_span_id != "":
                record_reason("frontend_has_parent", what, removed_traces_, cid, tid, single_trace)
            else:
                # app.logger.info(f"{gc.log_prefix} complete trace: " + str(single_trace))
                ret_traces_[cid][tid] = single_trace
    app.logger.info(f"[SLATE] Remove incomplete trace remove stats: {what}")
    # assert input_trace_len == ( len(ret_traces_[0]) + len(ret_traces_[1]) + len(removed_traces_[0]) + len(removed_traces_[0]) )
    return ret_traces_

# ratings-v1 and reviews-v1 should not exist in the same trace
FILTER_REVIEW_V1 = True # False
FILTER_REVIEW_V2 = True # False
FILTER_REVIEW_V3 = False # False
def filter_different_version(traces_):
    ret_traces_ = dict()
    filtered_traces_ = dict()
    what = dict()
    for cid, trace in traces_.items():
        ret_traces_[cid] = dict()
        filtered_traces_[cid] = dict()
        for tid, single_trace in traces_[cid].items():
            if FILTER_REVIEW_V1 and REVIEW_V1_svc in single_trace:
                if len(single_trace) != 3:
                    print_single_trace(single_trace)
                assert len(single_trace) == 3
                record_reason("filter_review_v1", what, filtered_traces_, cid, tid, single_trace)
            elif FILTER_REVIEW_V2 and REVIEW_V2_svc in single_trace:
                if len(single_trace) != 4:
                    print_single_trace(single_trace)
                assert len(single_trace) == 4
                record_reason("filter_review_v2", what, filtered_traces_, cid, tid, single_trace)
            elif FILTER_REVIEW_V3 and REVIEW_V3_svc in single_trace:
                if len(single_trace) != 4:
                    print_single_trace(single_trace)
                assert len(single_trace) == 4
                record_reason("filter_review_v3", what, filtered_traces_, cid, tid, single_trace)
            else:
                ret_traces_[cid][tid] = single_trace
    app.logger.info(f"[SLATE] Filter trace filter stats: {what}")
    return ret_traces_                

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
        app.logger.info(f"{gc.log_prefix} Service: {parent_span.svc_name}, Response time: {parent_span.rt}, Exclude_child_rt: {exclude_child_rt}, Exclusive time: {parent_span.xt}")
        ###########################################
        ###########################################
        ## TODO: all non-frontend services' xt will be set to zero for now.
        if parent_span.svc_name == FRONTEND_svc:
            parent_span.xt = parent_span.rt
        else:
            parent_span.xt = 0 ######
        ###########################################
        ###########################################
    return single_trace_


def traces_to_graphs(traces_):
    graph_dict = dict()
    for cid, trace in traces_.items():
        for tid, single_trace in traces_[cid].items():
            callgraph, cg_key = single_trace_to_callgraph(single_trace)
            # app.logger.info(f"tid: {tid}, callgraph: {callgraph}, cg_key: {cg_key}")
            graph_dict[cg_key] = callgraph
    # app.logger.info(f"len: {len(graph_dict)}, graph_dict: {graph_dict}")
    assert len(graph_dict) == 1
    app.logger.info(f"{gc.log_prefix} Graph: {graph_dict}")
    app.logger.info(f"{gc.log_prefix} Graph: {callgraph}")
    return callgraph


def calc_exclusive_time(traces_):
    for cid, trace in traces_.items():
        for tid, single_trace in traces_[cid].items():
            single_trace_ex_time = exclusive_time(single_trace)


# def get_unique_svc_names_from_dag(dag_):
#     unique_svc_names = dict()
#     for parent_span, children in dag_.items():
#         for child_span in children:
#             unique_svc_names[parent_span.svc_name] = "xxxx"
#             unique_svc_names[child_span.svc_name] = "xxxx"
#     return unique_svc_names


def print_all_trace(traces_):
    for cid, trace in traces_.items():
        for tid, single_trace in traces_[cid].items():
            app.logger.info(f"{gc.log_prefix} ======================= ")
            app.logger.info(f"{gc.log_prefix} Trace: " + tid)
            for svc, span in single_trace.items():
                print(span)
            app.logger.info(f"{gc.log_prefix} ======================= ")
    app.logger.info(f"{gc.log_prefix} Num final valid traces: {len(traces_)}")
    

def stitch_time(traces):
    app.logger.info(f"{gc.log_prefix} time stitching starts")
    ts = time.time()
    traces = remove_incomplete_trace_of_bookinfo(traces)
    traces = filter_different_version(traces)
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
        app.logger.info(f"{gc.log_prefix} Time stitching, productpage_only")
        traces = pp_only_traces
    ###################################################
    calc_exclusive_time(traces)
    call_graph = traces_to_graphs(traces)
    app.logger.info(f"{gc.log_prefix} ==============TRACE===============")
    for cid, trace in traces.items():
        for tid, single_trace in traces[cid].items():
            for svc, span in single_trace.items():
                    if svc == FRONTEND_svc:
                        app.logger.info(f"{gc.log_prefix}, SPAN, {span.svc_name}, xt,{span.xt}, rt,{span.rt}, load,{span.load}")
    app.logger.info(f"{gc.log_prefix} =================================")
    print_all_trace(traces)
    app.logger.info(f"{gc.log_prefix} time stitching done: {time.time() - ts}s")
    return traces, call_graph

if __name__ == "__main__":
    traces, call_graph = stitch_time(LOG_PATH)