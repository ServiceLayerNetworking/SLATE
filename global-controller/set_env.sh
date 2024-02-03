#!/bin/bash

mode=$1
if [ -z "$mode" ]; then
    echo "Error: No argument provided."
    echo "Usage: set_env.sh [profile|runtime]"
    exit
fi

if [ $mode != "profile" ] && [ $mode != "runtime" ]; then
    echo "Error: Invalid argument provided. ${mode}"
    echo "Usage: set_env.sh [profile|runtime]"
    exit
fi

file="env.txt"
sed -i "/^mode,/s/,.*$/,${mode}/" "$file"

slate_controller_pod=$(kubectl get pods -l app=slate-controller -o custom-columns=:metadata.name)
kubectl cp env.txt ${slate_controller_pod}:/app/env.txt
echo "kubectl cp env.txt ${slate_controller_pod}:/app/env.txt"
cat env.txt
