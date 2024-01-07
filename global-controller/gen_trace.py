import random
import span as sp
import time_stitching as tst
import optimizer_header as opt_func

A_GET = sp.Endpoint("A", "GET", "read")
B_GET = sp.Endpoint("B", "GET", "read")
A_POST = sp.Endpoint("A", "POST", "post")
C_POST = sp.Endpoint("C", "POST", "post")


'''
NOTE:
A_GET, A_POST is ordered when inserted to load_dict, eventually leading to the order of the coefficnets in trained linear regression model.

IMPORTANT:
For example, A, GET
latency_function['A, 'GET']['linearregression'].coef_[0] -> load in A,GET
latency_function['A, 'GET']['linearregression'].coef_[1] -> load in A,POST

latency of A,GET  = 
    load of A,GET * latency_func['A, GET']['linearregression'].coef_[0]
    
    + load of A,POST * latency_func['A, POST']['linearregression'].coef_[1]
    
    + latency_func['A, GET']['linearregression'].intercept_
'''
endpoint_dict = {"A": [A_GET, A_POST], "B": [B_GET], "C": [C_POST]}
callgraph_table = dict()
callgraph_table["GET"] = {A_GET: [B_GET], B_GET: []}
callgraph_table["POST"] = {A_POST: [C_POST], C_POST: []}


def gen_span(endpoint, span_id, cluster_id, trace_id, start_end_time):
    parent_span_id = span_id-1
    num_inflight_dict = {}
    for svc_name in endpoint_dict:
        if svc_name == endpoint.svc_name:
            et = start_end_time[svc_name][1]
            st = start_end_time[svc_name][0]
            for ep in endpoint_dict[svc_name]:
                num_inflight_dict[ep.endpoint] = et - st # it should have been xt
                print(f"num_inflight_dict[{ep.endpoint}]: {num_inflight_dict[ep.endpoint]}")
    print(f"endpoint: {endpoint.endpoint}, num_inflight_dict: {num_inflight_dict}")
    span = sp.Span(endpoint.method, endpoint.url, endpoint.svc_name, cluster_id, trace_id, span_id, parent_span_id, st=st, et=et, rps=0, cs=span_id, num_inflight_dict=num_inflight_dict)
    return span


def gen_trace(cg_key, cluster_id, trace_id):
    trace = list()
    next_span_id = 1
    endpoint_topology = callgraph_table[cg_key]
    # endpoint_topology: {A_GET: [B_GET], B_GET: []}
    # endpoint: A_GET, B_GET, ...
    if random.random() < 0.5:
        # A's xt: 6
        # B's xt: 4
        # C's xt: 4
        start_end_time = {"A":[0, 10],"B": [4, 8], "C": [4, 8]}
    else:
        # A's xt: 12
        # B's xt: 8
        # C's xt: 8
        start_end_time = {"A":[0, 20],"B": [4, 12], "C": [4, 12]}
    for endpoint in endpoint_topology:
        # span = gen_span(endpoint, next_span_id, random.randint(1,10),  cluster_id, trace_id)
        span = gen_span(endpoint, next_span_id, cluster_id, trace_id, start_end_time)
        trace.append(span)
        next_span_id += 1
    return trace


def run(num_cluster, num_traces):
    traces = dict()
    tid = 0
    for cid in range(num_cluster): # 0
        for cg_key in callgraph_table: # GET, POST
            for _ in range(num_traces): # 0
                if cid not in traces:
                    traces[cid] = dict()
                traces[cid][tid] = gen_trace(cg_key, cid, tid)
                tid += 1
    return traces

def print_trace(target_traces):
    for cid in target_traces:
        for tid, single_trace in target_traces[cid].items():
            for span in single_trace:
                print(f"{span}")
        print()
    
    
if __name__ == "__main__":
    traces = run(num_cluster=2, num_traces=10)
    root = dict()
    for cid in traces:
        for tid in traces[cid]:
            tst.stitch_trace(traces[cid][tid])
    print()
    temp = sp.Span()
    print(temp.get_colunm_name())
    print_trace(traces)
    