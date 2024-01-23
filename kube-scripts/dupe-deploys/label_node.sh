
node1=$1
kubectl label node $node1 topology.kubernetes.io/zone=us-west-1
echo "${node1} is labeled as zone=us-west-1"

node2=$2
kubectl label node $node2 topology.kubernetes.io/zone=us-east-1
echo "${node2} is labeled as zone=us-east-1"
