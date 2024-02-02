from flask import Flask, request
import logging

app = Flask(__name__)
logging.basicConfig(filename='record.log', level=logging.DEBUG)

@app.post('/proxyLoad')
def handleProxyLoad():
    svc = request.headers.get('x-slate-servicename')
    region = request.headers.get('x-slate-region')
    body = request.get_data().decode('utf-8')
    if svc == "metrics-fake-ingress-us-east":
        return """metrics-fake-ingress-us-east-1@GET@/start, us-west-1, us-west-1, 0.6
metrics-fake-ingress-us-east-1@GET@/start, us-west-1, us-east-1, 0.4
metrics-fake-ingress-us-east-1@POST@/start, us-west-1, us-west-1, 0.9
metrics-fake-ingress-us-east-1@POST@/start, us-west-1, us-east-1, 0.1
metrics-fake-ingress-us-west-1@GET@/start, us-west-1, us-west-1, 0.6
metrics-fake-ingress-us-west-1@GET@/start, us-west-1, us-east-1, 0.4
metrics-fake-ingress-us-west-1@POST@/start, us-west-1, us-west-1, 0.9
metrics-fake-ingress-us-west-1@POST@/start, us-west-1, us-east-1, 0.1"""
    app.logger.debug("{svc} in {region}:\n{body}".format(svc=svc, region=region, body=body))
    return ""

if __name__ == '__main__':
	app.run(host='0.0.0.0', port=8080)
