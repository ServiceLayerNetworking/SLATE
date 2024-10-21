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

echo "It is pushing to the 'gangmuk' repository..."
docker build -f Dockerfile-continuous -t ghcr.io/gangmuk/slate-controller:latest .
docker push ghcr.io/gangmuk/slate-controller:latest
kubectl rollout restart deploy slate-controller
