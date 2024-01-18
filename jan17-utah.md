# Jan 17 repro steps

Pre-run steps:
- Label nodes with `topology.kubernetes.io/zone` as `us-west-1` or `us-east-1`.

Verify latency at every step.
- install hotelreservation app from scratch (`kubectl apply -Rf kubernetes/` in `/hotelReservation`).
- switch image from deathstarbench to adiprerepa (`go build .;./dupedeploy -deployments="consul" -exclude -justswitchimage`)
- install istio with `istioctl install`.
  - Get ingressgateway endpoint by getting http2 nodeport of ingressgateway service + node that the ingressagateway is on: `http://<NODE>:NODEPORT`
	- verify traffic with `curl -v http://node1.gangmuk-186812.istio-pg0.utah.cloudlab.us:31852/recommendations\?require\=rate\&lat\=37.804\&lon\=-122.099`
- install istio gateways and frontend vs/dr and jaeger proxyconfig with `kubectl apply -f hotelreservation.yaml`)
- install WASM plugin with `kubectl apply -f wasmplugins.yaml` in `/baremetal-singlecluster`.
- install Slate-controller with `kubectl apply -f slate-controller.yaml`.
- duplicate all deployments with `go build .;./dupedeploy -deployments="consul,slate-controller" -exclude`.
- install virtualservice with `go build .;./vs-headermatch -exclude -services="consul,frontend-us-east-1,frontend-us-west-1,slate-controller"`

