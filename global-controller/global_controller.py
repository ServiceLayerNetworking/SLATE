from flask import Flask, request
import logging
from threading import Lock
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
import optimizer as opt
import pandas as pd
import config as cf
import span as sp

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

"""
2
f85116460cc0c607a484d0521e62fb19 7c30eb0e856124df a484d0521e62fb19 1694378625363 1694378625365
4ef8ed533389d8c9ace91fc1931ca0cd 48fb12993023f618 ace91fc1931ca0cd 1694378625363 1694378625365

<Num requests>
<Trace Id> <Span Id> <Parent Span Id> <Start Time> <End Time>

Root svc will have no parent span id
"""

ACTUAL_LOAD=True
NUM_CLUSTER = 2

complete_traces = {}
all_traces = {}
svc_to_rps = {}
cluster_to_cid = {"us-west": 0, "us-east": 1}
stats_mutex = Lock()
stats_arr = []
# in form of [cluster_id][dest cluster] = pct
# to be applied by cluster controller
cluster_pcts = {} # TODO: It is currently dealing with ingress gateway only.

prof_start = {0: False, 1: False}
counter = {0:0, 1:0} # {cid:counter, ...}
PROF_DURATION = 30 # in seconds
MIN_NUM_TRACE = 30
load_bucket = dict()
num_bucket = 10
bucket_size = 5
min_data_in_bucket = 5
for cid in range(NUM_CLUSTER):
    load_bucket[cid] = dict()
    for i in range(num_bucket):
        load_bucket[cid][i] = 0
prof_done = {0:False, 1:False} # {cid: prof_done_flag, ...}

# TODO: It is currently Hardcoded

'''
Span class in global controlelr is deprecated.
Use Span class in time_stitching.py for compatibility.
'''
# class Span:
#     def __init__(self, svc_name, cluster_id, trace_id, my_span_id, parent_span_id, start, end, load, call_size):
#         self.svc_name = svc_name #
#         self.my_span_id = my_span_id #
#         self.trace_id = trace_id
#         self.start = start #
#         self.end = end #
#         self.parent_span_id = parent_span_id #
#         self.load = load #
#         self.call_size = call_size ####
#         self.cluster_id = cluster_id
#         self.xt = 0
#         self.rt = self.end - self.start

#     def __str__(self):
#         return f"{self.svc_name} ({self.my_span_id}) took {self.end - self.start} ms, parent {self.parent_span_id}"

"""
parse_stats_into_spans will parse the stats string into a list of spans.
stats is in the format of:
<Num requests>
<Trace Id> <Span Id> <Parent Span Id> <Start Time> <End Time> <Call Size>

Root svc will have no parent span id
If the span doesn't make sense, just ignore it.
"""
def parse_stats_into_spans(stats, cluster, service):
    spans = []
    lines = stats.split("\n")
    num_req = int(lines[0])
    for i in range(1, len(lines)):
        line = lines[i]
        ss = line.split(" ")
        if len(ss) < 6:
            continue
        trace_id = ss[0]
        my_span_id = ss[1]
        # can be empty
        parent_span_id = ss[2]
        start = int(ss[3])
        end = int(ss[4])
        call_size = int(ss[5])
        spans.append(sp.Span(service, cluster_to_cid[cluster], trace_id, my_span_id, parent_span_id, start, end, num_req, call_size))
    if len(spans) > 0:
        app.logger.info(f"{cf.log_prefix} ==================================")
        for span in spans:
            app.logger.info(f"{cf.log_prefix} {span}")
        app.logger.info(f"{cf.log_prefix} ==================================")
    return spans


def is_load_bucket_filled(cid):
    for i in range(num_bucket):
        if len(load_bucket[cid][i]) < min_data_in_bucket:
            app.logger.info(f"{cf.log_prefix} Not filled, Cluster {cid}, bucket:{i}, len:{len(load_bucket[cid][i])}, min_len:{min_data_in_bucket}")
            app.logger.info(f"{cf.log_prefix} is_load_bucket_filled, Cluster {cid}, RETURNS FALSE")
            return False
        else:
            app.logger.info(f"{cf.log_prefix} Cluster {cid}, bucket:{i} is filled, bucket_len:{len(load_bucket[cid][i])}, min_len:{min_data_in_bucket}")
    app.logger.info(f"{cf.log_prefix} is_load_bucket_filled, All buckets are filled. Cluster {cid}, RETURN TRUE")
    return True


def prof_phase():
    for cid in range(NUM_CLUSTER):
        if prof_start[cid]:
            app.logger.info(f"{cf.log_prefix} Both clusters are ready to be profiled")
            prof_percentage = counter[cid]/PROF_DURATION
            app.logger.info(f"{cf.log_prefix} Cluster {cid}, Profiling phase: {prof_percentage*100}% (elapsed seconds: {counter[cid]} / required seconds: {PROF_DURATION}\n")
            ## TODO:
            # if (counter[cid] >= PROF_DURATION) and (len(complete_traces[cid] > MIN_NUM_TRACE)) and (is_load_bucket_filled(cid)):
            if (counter[cid] >= PROF_DURATION) and (len(complete_traces[cid]) > MIN_NUM_TRACE):
                prof_done[cid] = True
                app.logger.info(f"{cf.log_prefix} Cluster {cid} Profiling already DONE, NUM_TRACE: {len(complete_traces[cid])} ")
            counter[cid] += 1


def garbage_collection():
    app.logger.info(f"{cf.log_prefix} Start Garbage collection")
    app.logger.info(f"{cf.log_prefix} Clearing complete_traces, all_traces, stats_arr...")
    complete_traces.clear()
    all_traces.clear()
    stats_arr.clear()
    app.logger.info(f"{cf.log_prefix} Done with Garbage collection")


# Runs every few seconds
def optimizer_entrypoint():
    # with stats_mutex:
    # for k, v in all_traces.items():
    #     for trace_id, spans in v.items():
    #         app.logger.info(f"{cf.log_prefix} Trace {trace_id} has {len(spans)} spans:")
    #         for svc_name, span in spans.items():
    #             app.logger.info(f"{cf.log_prefix} \t{span}")

        if prof_done[0] and prof_done[1]:
            app.logger.info(f"\n\n{cf.log_prefix} Run Optimizer, number of complete traces (cluster 0: {len(complete_traces[0])}, cluster 1: {len(complete_traces[1])})\n")
            
            # TODO: this should be ingressgateway. hardcoding for now
            
            if ACTUAL_LOAD:
                # Next tick load == Current tick load
                app.logger.info(f"{cf.log_prefix} CONFIG: ACTUAL LOAD")
                cluster_0_num_req = svc_to_rps["us-west"]["productpage-v1"]
                cluster_1_num_req = svc_to_rps["us-east"]["productpage-v1"]
                app.logger.info(f"{cf.log_prefix} LOAD cluster 0: {cluster_0_num_req}, cluster 1: {cluster_1_num_req})\n")
                if cluster_0_num_req == 0 and cluster_1_num_req == 0:
                    app.logger.info(f"{cf.log_prefix} NO LOAD. Skip Optimizer")
                    return
            else:
                # Arbitrary load
                cluster_0_num_req = 10
                cluster_1_num_req = 60
                app.logger.warning(f"{cf.log_prefix} CONFIG: FAKE LOAD: Cluster 0{cluster_0_num_req}, Cluster 1 {cluster_1_num_req}")
            
            num_requests_dict = {0: cluster_0_num_req, 1: cluster_1_num_req}
            num_requests = [cluster_0_num_req, cluster_1_num_req]
            ## NOTE: copy() function could be expensive if complete_trace is large
            percentage_df = opt.run_optimizer(complete_traces.copy(), num_requests)
            app.logger.info(f"{cf.log_prefix} PERCENTAGE RULES: {percentage_df}")
            if percentage_df is None:
                # we don't know what to do to stick to local routing
                if 0 not in cluster_pcts:
                    cluster_pcts[0] = {1: "0.0"}
                if 1 not in cluster_pcts:
                    cluster_pcts[1] = {0: "0.0"}
                app.logger.info(f"{cf.log_prefix} RESET PERCENTAGE RULES: {cluster_pcts}")
                return
            
            else:
                ingress_gw_df = percentage_df[percentage_df['src']=='ingress_gw']
                for src_cid in range(NUM_CLUSTER):
                    for dst_cid in range(NUM_CLUSTER):
                        row = ingress_gw_df[(ingress_gw_df['src_cid']==src_cid) & (ingress_gw_df['dst_cid']==dst_cid)]
                        if len(row) > 1:
                            app.logger.info(f"{cf.log_prefix} length of row can't be greater than 1.")
                            app.logger.info(f"{cf.log_prefix} {row}")
                            assert len(row) <= 1
                        elif len(row) == 1:
                            cluster_pcts[src_cid][dst_cid] = str(row['weight'].tolist()[0])
                        else:
                            cluster_pcts[src_cid][dst_cid] = str(0)
                app.logger.info(f"{cf.log_prefix} CLUSTER PERCENTAGE RULES: {cluster_pcts}")
            # all_traces.clear()
        else:
            app.logger.info(f"{cf.log_prefix} prof is NOT done yet. still needs to collect more traces...")
            return
        
        
# TODO
def retrain_service_models():
    pass


@app.route("/clusterLoad", methods=["POST"])
def proxy_load():
    body = request.get_json(force=True)
    cluster = body["clusterId"]
    pod = body["podName"]
    svc_name = body["serviceName"]
    stats = body["body"]
    # app.logger.info(f"{cf.log_prefix} Received stats from {cluster} {pod} {svc_name}")
    if cluster not in svc_to_rps:
        svc_to_rps[cluster] = {}
    svc_to_rps[cluster][svc_name] = int(stats.split("\n")[0])
    
    ## Keep collecting traces
    ################################################
    # if prof_done[cluster_to_cid[cluster]] == False:
    if True:
    ################################################
        spans = parse_stats_into_spans(stats, cluster, svc_name)
        # if len(spans) > 0 and spans[0].load > 0:
        if prof_start[cluster_to_cid[cluster]] == True or (len(spans) > 0 and spans[0].load):
            if prof_start[cluster_to_cid[cluster]] == False:
                prof_start[cluster_to_cid[cluster]] = True
                app.logger.info(f"{cf.log_prefix} The FIRST proxy load for cluster {cluster}, {spans[0].cluster_id}.")
                app.logger.info(f"{cf.log_prefix} Start profiling for cluster {cluster}, {spans[0].cluster_id}.")
            else:
                app.logger.info(f"{cf.log_prefix} Profiling for Cluster {cluster} already started.")
        else:
            app.logger.info(f"{cf.log_prefix} cluster {cluster}, {cluster_to_cid[cluster]} still have NOT received any proxy load. Hold off starting profiling.")
        with stats_mutex:
            for span in spans:
                if span.cluster_id not in all_traces:
                    all_traces[span.cluster_id] = {}
                if span.trace_id not in all_traces[span.cluster_id]:
                    all_traces[span.cluster_id][span.trace_id] = {}
                all_traces[span.cluster_id][span.trace_id][span.svc_name] = span
                if len(all_traces[span.cluster_id][span.trace_id]) == 4: # NOTE: hardcoded.
                    span_exists = []
                    ignore_cur = False
                    for svc_name, span in all_traces[span.cluster_id][span.trace_id].items():
                        if span.my_span_id in span_exists:
                            ignore_cur = True
                            break
                        span_exists.append(span.my_span_id)
                    if ignore_cur:
                        continue
                    if span.cluster_id not in complete_traces:
                        complete_traces[span.cluster_id] = {}
                    if span.trace_id not in complete_traces[span.cluster_id]:
                        complete_traces[span.cluster_id][span.trace_id] = {}
                    complete_traces[span.cluster_id][span.trace_id] = all_traces[span.cluster_id][span.trace_id].copy()
                    try:
                        bucket_key = int(span.load/bucket_size)
                        if bucket_key not in load_bucket[span.cluster_id]:
                            app.logger.info(f"{cf.log_prefix} New load bucket key:{bucket_key}, load:{span.load}")
                            load_bucket[span.cluster_id][bucket_key] = 0
                        load_bucket[span.cluster_id][bucket_key] += 1
                    except Exception as e:
                        app.logger.error(f"{cf.log_prefix} {e}")
                    
        # cid -> trace id -> svc_name -> span
        stats_arr.append(f"{cluster} {pod} {svc_name} {stats}\n")
        # app.logger.info(f"{cf.log_prefix} Profiling was done. No more trace will be collected anymore.")
        for cid in range(2):
            if cid not in cluster_pcts:
                cluster_pcts[cid] = {}
        # Since this is still profiling phase, it does not have enough traces.
        # Set local routing rule
        
    if prof_done[cluster_to_cid[cluster]] == False:
        # Need more traces. Do local routing for now.
        app.logger.info(f"{cf.log_prefix} Cluster Percentage for {cluster} is NOT computed yet...")
        cluster_pcts[0][0] = "1.0"
        cluster_pcts[0][1] = "0.0"
        cluster_pcts[1][1] = "1.0"
        cluster_pcts[1][0] = "0.0"
    else:
        # Profiling is DONE.
        app.logger.info(f"{cf.log_prefix} Profiling was already done.")
        
    # if cluster_to_cid[cluster] in cluster_pcts:
    assert cluster_to_cid[cluster] in cluster_pcts
    return cluster_pcts[cluster_to_cid[cluster]]
    

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=optimizer_entrypoint, trigger="interval", seconds=5)
    scheduler.add_job(func=prof_phase, trigger="interval", seconds=1)
    scheduler.add_job(func=garbage_collection, trigger="interval", seconds=600)
    # scheduler.add_job(func=retrain_service_models, trigger="interval", seconds=10)
    scheduler.start()

    atexit.register(lambda: scheduler.shutdown())

    app.run(host='0.0.0.0', port=8080)
