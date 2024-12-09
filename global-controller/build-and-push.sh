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
#ghcr_account="adiprerepa"
ghcr_account="gangmuk"

echo "It is pushing to the '${ghcr_account}' repository..."
docker build -f ${docker_file} -t ghcr.io/${ghcr_account}/slate-controller:latest .
docker push ghcr.io/${ghcr_account}/slate-controller:latest
kubectl rollout restart deploy slate-controller
