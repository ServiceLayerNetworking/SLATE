from flask import Flask, request
import logging

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


@app.route("/clusterLoad    ", methods=["POST"])
def proxy_load():
    body = request.get_json(force=True)
    cluster = body["clusterId"]
    pod = body["podName"]
    svc = body["serviceName"]
    stats = body["body"]
    app.logger.info(f"Received proxy load for {cluster} {pod} {svc} {stats}")
    return ""

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
