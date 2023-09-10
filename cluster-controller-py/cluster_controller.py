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

@app.route("/proxyLoad", methods=["POST"])
def proxy_load():
    stats = request.data.decode(encoding="utf-8")
    if len(stats) == 0:
        return ""
    pod = request.headers.get("x-slate-podname")
    svc = request.headers.get("x-slate-servicename")
    app.logger.info("recieved stats from service %s: %s", svc, stats)
    return ""

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
