from flask import Flask, request
import logging

app = Flask(__name__)
logging.basicConfig(filename='record.log', level=logging.DEBUG)

r = """metrics-fake-ingress-us-west-1@GET@/detectAnomalies, us-west-1, us-west-1, 0.1
metrics-fake-ingress-us-west-1@GET@/detectAnomalies, us-west-1, us-east-1, 0.9
metrics-fake-ingress-us-west-1@POST@/detectAnomalies, us-west-1, us-west-1, 0.5
metrics-fake-ingress-us-west-1@POST@/detectAnomalies, us-west-1, us-east-1, 0.5"""

@app.post('/proxyLoad')
def handleProxyLoad():
    svc = request.headers.get('x-slate-servicename')
    region = request.headers.get('x-slate-region')
    if svc == "metrics-fake-ingress-us-west-1":
        return r
    print("{svc} in {region}".format(svc=svc, region=region), flush=True)
    return ""

if __name__ == '__main__':
	app.run(host='0.0.0.0', port=8080)
