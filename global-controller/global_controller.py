from flask import Flask, request
import logging
from threading import Lock
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
import optimizer as opt
import pandas as pd

app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

"""
2
f85116460cc0c607a484d0521e62fb19 7c30eb0e856124df a484d0521e62fb19 1694378625363 1694378625365
4ef8ed533389d8c9ace91fc1931ca0cd 48fb12993023f618 ace91fc1931ca0cd 1694378625363 1694378625365

<Num requests>
<Trace Id> <Span Id> <Parent Span Id> <Start Time> <End Time>

Root svc will have no parent span id
"""

ACTUAL_LOAD=False
log_prefix = "[SLATE]"

complete_traces = {}
all_traces = {}
svc_to_rps = {}
cluster_to_cid = {"us-west": 0, "us-east": 1}
stats_mutex = Lock()
stats_arr = []
# in form of [cluster_id][dest cluster] = pct
# to be applied by cluster controller
cluster_pcts = {}

prof_start = {0: False, 1: False}
counter = {0:0}
PROF_DURATION = 35 # in seconds
prof_done = {0:False}



class Span:
    def __init__(self, svc_name, cluster_id, trace_id, my_span_id, parent_span_id, start, end, load, call_size):
        self.svc_name = svc_name #
        self.my_span_id = my_span_id #
        self.trace_id = trace_id
        self.start = start #
        self.end = end #
        self.parent_span_id = parent_span_id #
        self.load = load #
        self.call_size = call_size ####
        self.cluster_id = cluster_id
        self.xt = 0
        self.rt = self.end - self.start

    def __str__(self):
        return f"{self.svc_name} ({self.my_span_id}) took {self.end - self.start} ms, parent {self.parent_span_id}"

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
        spans.append(Span(service, cluster_to_cid[cluster], trace_id, my_span_id, parent_span_id, start, end, num_req, call_size))
    return spans


def prof_phase():
    if prof_start[0] and prof_start[1]:
        app.logger.info(f"{log_prefix} Both clusters are ready to be profiled")
        prof_percentage = int(counter[0]/PROF_DURATION)
        app.logger.info(f"{log_prefix} Profiling phase: {prof_percentage*100}% (elapsed seconds: {counter[0]} / required seconds: {PROF_DURATION}\n")
        if counter[0] >= PROF_DURATION:
            # prof_counter = 0 # reset the profiling
            prof_done[0] = True
            app.logger.info(f"{log_prefix} Profiling already DONE")
        counter[0] += 1


def garbage_collection():
    app.logger.info(f"{log_prefix} Start Garbage collection")
    app.logger.info(f"{log_prefix} Clearing complete_traces, all_traces, stats_arr...")
    complete_traces.clear()
    all_traces.clear()
    stats_arr.clear()
    app.logger.info(f"{log_prefix} Done with Garbage collection")


# Runs every few seconds
def optimizer_entrypoint():
    # with stats_mutex:
    # for k, v in all_traces.items():
    #     for trace_id, spans in v.items():
    #         app.logger.info(f"{log_prefix} Trace {trace_id} has {len(spans)} spans:")
    #         for svc_name, span in spans.items():
    #             app.logger.info(f"{log_prefix} \t{span}")

        if prof_done[0]:
            app.logger.info(f"\n\n{log_prefix} Run Optimizer, number of complete traces (cluster 0: {len(complete_traces[0])}, cluster 1: {len(complete_traces[1])})\n")
            
            # TODO: this should be ingressgateway. hardcoding for now
            
            if ACTUAL_LOAD:
                # Next tick load == Current tick load
                cluster_1_num_req = svc_to_rps["us-west"]["productpage-v1"]
                cluster_2_num_req = svc_to_rps["us-east"]["productpage-v1"]
                app.logger.info(f"{log_prefix} LOAD cluster 0: {cluster_1_num_req}, cluster 1: {cluster_2_num_req})\n")
                if cluster_1_num_req == 0 and cluster_2_num_req == 0:
                    app.logger.info(f"{log_prefix} NO LOAD. Skip Optimizer")
                    return
            else:
                # Arbitrary load
                cluster_1_num_req = 10
                cluster_2_num_req = 60
            
            num_requests = {0: cluster_1_num_req, 1: cluster_2_num_req}
            percentage_df = opt.run_optimizer(complete_traces.copy(), num_requests)
            if percentage_df is None:
                # we don't know what to do to stick to local routing
                if 0 not in cluster_pcts:
                    cluster_pcts[0] = {1: "0.0"}
                if 1 not in cluster_pcts:
                    cluster_pcts[1] = {0: "0.0"}
                app.logger.info(f"{log_prefix}RESET PERCENTAGE RULES: {cluster_pcts}")
                return
            
            #########################################################
            #          src	    dst	    src_cid	dst_cid	flow
            # 0	ingress_gw	productpage-v1	0	0	    10.00
            # 1	ingress_gw	productpage-v1	1	0	    10.25
            # 2	ingress_gw	productpage-v1	1	1	    39.75
            #
            # src_list = ["ingress_gw"]*4
            # dst_list = ["productpage-v1"]*4
            # src_cid_list = [0,0,1,1]
            # dst_cid_list = [0,1,0,1]
            # flow_list = [10.0, 0.0, 10.25, 39.75]
            # percentage_df = pd.DataFrame(
            #     data={
            #         "src": src_list,
            #         "dst": dst_list, 
            #         "src_cid": src_cid_list,
            #         "dst_cid": dst_cid_list,
            #         "flow": flow_list
            #     },
            # )
            #########################################################
            
            app.logger.info(f"{log_prefix}PERCENTAGE RULES: {percentage_df}")
            igw_rows = percentage_df[percentage_df['src'] == "ingress_gw"]
            total_reqs = 0
            for idx, row in igw_rows.iterrows():
                total_reqs += int(row['flow'])
                src_cluster = int(row['src_cid'])
                dst_cluster = int(row['dst_cid'])
                if src_cluster not in cluster_pcts:
                    cluster_pcts[src_cluster] = {}
                if src_cluster != dst_cluster:
                    # flow to another cluster
                    pct = int(row['flow']) / reqs[src_cluster]
                    cluster_pcts[src_cluster][dst_cluster] = str(pct)
            app.logger.info(f"{log_prefix} CLUSTER PERCENTAGE RULES: {cluster_pcts}")
            # all_traces.clear()
        else:
            app.logger.info(f"{log_prefix} prof is NOT done yet. still needs to collect more traces...")
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
    # app.logger.info(f"{log_prefix} Received stats from {cluster} {pod} {svc_name}")
    if cluster not in svc_to_rps:
        svc_to_rps[cluster] = {}
    svc_to_rps[cluster][svc_name] = int(stats.split("\n")[0])
    
    if prof_done[0]:
        app.logger.info(f"{log_prefix} Profiling was done. No more trace will be collected anymore.")
    else:
        spans = parse_stats_into_spans(stats, cluster, svc_name)
        # if len(spans) > 0 and spans[0].load > 0:
        if prof_start[cluster_to_cid[cluster]] == True or (len(spans) > 0 and spans[0].load):
            if prof_start[cluster_to_cid[cluster]] == False:
                prof_start[cluster_to_cid[cluster]] = True
                app.logger.info(f"{log_prefix} The FIRST proxy load for cluster {cluster}, {spans[0].cluster_id}.")
                app.logger.info(f"{log_prefix} Start profiling for cluster {cluster}, {spans[0].cluster_id}.")
            else:
                app.logger.info(f"{log_prefix} Profiling for cluster {cluster} already started.")
        else:
            app.logger.info(f"{log_prefix} cluster {cluster}, {cluster_to_cid[cluster]} still have NOT received any proxy load. Hold off starting profiling.")
        with stats_mutex:
            for span in spans:
                if span.cluster_id not in all_traces:
                    all_traces[span.cluster_id] = {}
                if span.trace_id not in all_traces[span.cluster_id]:
                    all_traces[span.cluster_id][span.trace_id] = {}
                all_traces[span.cluster_id][span.trace_id][span.svc_name] = span
                if len(all_traces[span.cluster_id][span.trace_id]) == 4:
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
        # cid -> trace id -> svc_name -> span
        stats_arr.append(f"{cluster} {pod} {svc_name} {stats}\n")
        # app.logger.info(f"{log_prefix} Profiling was done. No more trace will be collected anymore.")
        
        app.logger.info(f"{log_prefix} Cluster Percentage for {cluster} is NOT computed yet...")
        for cid in range(2):
            if cid not in cluster_pcts:
                cluster_pcts[cid] = {}
        cluster_pcts[0][0] = "1.0"
        cluster_pcts[0][1] = "0.0"
        
        cluster_pcts[1][1] = "1.0"
        cluster_pcts[1][0] = "0.0"
        
    if cluster_to_cid[cluster] in cluster_pcts:
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
