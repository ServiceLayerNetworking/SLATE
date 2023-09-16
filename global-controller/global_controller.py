from flask import Flask, request
import logging
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

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

traces = {}
svc_to_rps = {}

stats_arr = []

def flush_stats_to_file():
    for s in stats_arr:
        app.logger.info(s)
    stats_arr.clear()


@app.route("/clusterLoad", methods=["POST"])
def proxy_load():
    body = request.get_json(force=True)
    cluster = body["clusterId"]
    pod = body["podName"]
    svc = body["serviceName"]
    stats = body["body"]
    # if svc == "productpage-v1":
    #     num_req = stats.split("\n")[0]
    #     sum = 0
    #     num_p = 0
    #     for s in stats.split("\n")[1:]:
    #
    #         ss = s.split(" ")
    #         if len(ss) >= 3:
    #             start = int(ss[-3])
    #             end = int(ss[-2])
    #             sum += (end - start)
    #             num_p += 1
    #
    #     if num_p > 0:
    #         app.logger.info(f"{num_req} requests, avg latency {sum/num_p} ms")

    stats_arr.append(f"{cluster} {pod} {svc} {stats}\n")

        # print(f"Received proxy load for {cluster} {pod} {svc}\n{stats}")
    return ""

if __name__ == "__main__":

    scheduler = BackgroundScheduler()
    scheduler.add_job(func=flush_stats_to_file, trigger="interval", seconds=3)
    scheduler.start()

    atexit.register(lambda: scheduler.shutdown())

    app.run(host='0.0.0.0', port=8080)
