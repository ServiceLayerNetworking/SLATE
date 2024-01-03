import random
import span as sp
import time_stitching as tst
import optimizer_header as opt_func


'''
Span format
{self.trace_id},{self.svc_name},{self.get_class()},{self.method},{self.url},{self.cluster_id},{self.my_span_id},{self.parent_span_id},{self.load},{self.last_load},{self.avg_load},{self.rps},{self.st},{self.et},{self.rt},{self.call_size}
'''
    
A_GET = sp.Endpoint("A", "GET", "http://localhost:8080/wrk2-api/user-timeline/read")
B_GET = sp.Endpoint("B", "GET", "http://localhost:8080/wrk2-api/user-timeline/read")
A_POST = sp.Endpoint("A", "POST", "http://localhost:8080/wrk2-api/post/compose")
C_POST = sp.Endpoint("C", "POST", "http://localhost:8080/wrk2-api/post/compose")

endpoint_dict = {"A": [A_GET, A_POST], "B": [B_GET], "C": [C_POST]}

callgraph_table = dict()
callgraph_table["GET"] = {A_GET: [B_GET], B_GET: []}
callgraph_table["POST"] = {A_POST: [C_POST], C_POST: []}


def gen_span(endpoint, span_id, num_inflight, cluster_id, trace_id):
    parent_span_id = span_id-1
    num_inflight_dict = {}
    for svc_name in endpoint_dict:
        if svc_name == endpoint.svc_name:
            for ep in endpoint_dict[svc_name]:
                num_inflight_dict[ep.endpoint] = num_inflight
    print(f"endpoint: {endpoint.endpoint}, num_inflight_dict: {num_inflight_dict}")
    if endpoint.svc_name == "A":
        st = 0
        et = 10
    else:
        st = random.randint(3, 6)
        et = random.randint(7, 9)
    span = sp.Span(endpoint.method, endpoint.url, endpoint.svc_name, cluster_id, trace_id, span_id, parent_span_id, st=st, et=et, rps=0, cs=span_id, num_inflight_dict=num_inflight_dict)
    return span


def gen_trace(cg_key, cluster_id, trace_id):
    trace = list()
    next_span_id = 1
    endpoint_topology = callgraph_table[cg_key]
    for endpoint in endpoint_topology:
        span = gen_span(endpoint, next_span_id, random.randint(1,10) ,  cluster_id, trace_id)
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
    