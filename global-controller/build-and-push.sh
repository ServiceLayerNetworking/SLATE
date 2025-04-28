#!/bin/bash

# dockerfile=$1
# if [ -z "$dockerfile" ]; then
#   echo "Usage: $0 <dockerfile>"
#   echo "options1: ./build-and-push.sh Dockerfile-original for global controller 'without' continous profilig"
#   echo "options2: ./build-and-push.sh Dockerfile-continuous for global controller 'with' continous profilig"
#   exit 1
# fi
# docker build -f ${dockerfile} -t ghcr.io/adiprerepa/slate-controller:latest . &&
# docker push ghcr.io/adiprerepa/slate-controller:latest &&

# docker build -t ghcr.io/adiprerepa/slate-controller:latest .
# docker push ghcr.io/adiprerepa/slate-controller:latest

# docker_file="Dockerfile-continuous"
docker_file="Dockerfile"

ghcr_account="gangmuk"
tag=apr27th-test-merged-version

## Read the current image name and tag from the current slate-controller deployment
current_image=$(kubectl get deploy slate-controller -o jsonpath='{.spec.template.spec.containers[0].image}')

echo "*************************"
echo "** Current slate-controller deployment: $current_image"
echo "*************************"

# ghcr_account="adiprerepa"
# tag=latest

echo "========================="
echo "== ghcr_account: ${ghcr_account}"
echo "== tag: ${tag}"
echo "========================="
echo "starting in 3 seconds..."
sleep 1
echo "starting in 2 seconds..."
sleep 1
echo "starting in 1 seconds..."
sleep 1
echo "It is pushing to the '${ghcr_account}' repository..."
docker build -f ${docker_file} -t ghcr.io/${ghcr_account}/slate-controller:${tag} .
docker push ghcr.io/${ghcr_account}/slate-controller:${tag}
kubectl rollout restart deploy slate-controller
echo tag: ${tag}