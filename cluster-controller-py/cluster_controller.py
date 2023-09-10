from flask import Flask, request
import logging

app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)


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
