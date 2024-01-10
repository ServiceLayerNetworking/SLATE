from flask import Flask, request
import logging

app = Flask(__name__)
logging.basicConfig(filename='record.log', level=logging.DEBUG)

@app.post('/proxyLoad')
def handleProxyLoad():
    svc = request.headers.get('x-slate-servicename')
    region = request.headers.get('x-slate-region')
    body = request.get_data().decode('utf-8')
    app.logger.debug("{svc} in {region}:\n{body}".format(svc=svc, region=region, body=body))
    return ""

if __name__ == '__main__':
	app.run(host='0.0.0.0', port=8080)
