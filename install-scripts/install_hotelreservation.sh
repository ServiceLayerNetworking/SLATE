#!/bin/bash

set -e


# label nodes with regions.
nodeNames=$(kubectl get nodes --show-labels | grep -v 'node-role.kubernetes.io/master' | grep -v 'node-role.kubernetes.io/control-plane' | awk 'NR>1 {printf "%s ", $1}')
echo "Node names: $nodeNames"
# separate the node names into bash array
IFS=' ' read -r -a nodeArray <<< "$nodeNames"
# label the node nodeArray[0] with topology.kubernetes.io/zone=us-west-1
kubectl label node ${nodeArray[0]} topology.kubernetes.io/zone=us-west-1 --overwrite
# label the node nodeArray[1] with topology.kubernetes.io/zone=us-east-1
kubectl label node ${nodeArray[1]} topology.kubernetes.io/zone=us-east-1 --overwrite

# if $HOTELRESERVATION_DIR is not set, clone the DeathStarBench repository and change directory to hotelReservation/, otherwise change directory to $HOTELRESERVATION_DIR.
if [ -z "$HOTELRESERVATION_DIR" ]; then
	git clone https://github.com/delimitrou/DeathStarBench.git
	cd DeathStarBench/hotelReservation/
else
	cd $HOTELRESERVATION_DIR
fi

# install hotelreservation manifests
kubectl apply -Rf kubernetes/

# change directory to the original directory
cd -

# duplicate all deployments 
echo "[SCRIPT] duplicating deployments..."
cd ../kube-scripts/dupe-deploys
go build .;./dupedeploy -deployments="consul" -exclude;

# install istio
echo "[SCRIPT] installing istio..."
istioctl install -y
kubectl label namespace default istio-injection=enabled
kubectl rollout restart deploy
cd ../../ # should now be in base slate directory
kubectl apply -f config/baremetal-singlecluster/hotelreservation.yaml

# verify traffic can be sent through ingressgateway
echo "[SCRIPT] waiting for pods to be ready after restart..."
sleep 15
# get the http2 nodePort of the istio-ingressgateway service
http2NodePort=$(kubectl get svc istio-ingressgateway -n istio-system -o=jsonpath='{.spec.ports[?(@.name=="http2")].nodePort}')
# check which node the istio-ingressgateway pod is running on
ingressNode=$(kubectl get pod -l app=istio-ingressgateway -n istio-system -o=jsonpath='{.items[0].spec.nodeName}')
# send a request to the istio-ingressgateway pod at port $http2NodePort
echo "[SCRIPT] trying to reach cluster through ingressgateway nodePort... $ingressNode:$http2NodePort}"
curl -v http://$ingressNode:$http2NodePort/recommendations\?require\=rate\&lat\=37.804\&lon\=-122.099

# install WASM Plugins
kubectl apply -f config/baremetal-singlecluster/wasmplugins.yaml
# install slate-controller
kubectl apply -f config/baremetal-singlecluster/slate-controller.yaml

echo "[SCRIPT] applying local routing rules to the cluster..."
# apply local routing rules
cd kube-scripts/virtualservice-headermatch
go build .;./vs-headermatch -exclude -services="consul,frontend"
kubectl rollout restart deploy
echo "[SCRIPT] waiting for pods to be ready after restart..."
sleep 10

# verify traffic again
echo "trying to reach cluster through ingressgateway nodePort... $ingressNode:$http2NodePort}"
curl -v http://$ingressNode:$http2NodePort/recommendations\?require\=rate\&lat\=37.804\&lon\=-122.099

