
## Update all deployment in the default namespace.
#kubectl get deployments -n default -o json | jq '.items[].spec.template.spec.containers[].resources = {"requests": {"cpu": "0.5", "memory": "256Mi"}, "limits": {"cpu": "1", "memory": "512Mi"}}' | kubectl apply -f -


## Update deployments except for slate-controller deployment
kubectl get deployments -n default -o json | \
 jq '(.items[] | select(.metadata.name != "slate-controller")) | .spec.template.spec.containers[].resources = {"requests": {"cpu": "0.1"}, "limits": {"cpu": "5"}}' | \
   kubectl apply -f -

remove_cpu_limit() {
  local namespace="$1"
  local exclude_deployments=("${@:2}")

  # Get a list of all deployments in the specified namespace
  local deployment_names=($(kubectl get deployments -n "$namespace" -o jsonpath='{.items[*].metadata.name}'))

  # Loop through the deployments and update CPU requests and limits for all containers
  for deployment in "${deployment_names[@]}"; do
    if [[ " ${exclude_deployments[@]} " =~ " $deployment " ]]; then
      # Skip deployments that are in the exclusion list
      continue
    fi

    kubectl patch deployment "$deployment" -n "$namespace" --type='json' -p='[
      {"op": "remove", "path": "/spec/template/spec/containers/0/resources/limits/cpu"}
    ]'
  done
}

remove_mem() {
  local namespace="$1"
  local exclude_deployments=("${@:2}")

  # Get a list of all deployments in the specified namespace
  local deployment_names=($(kubectl get deployments -n "$namespace" -o jsonpath='{.items[*].metadata.name}'))

  # Loop through the deployments and update CPU requests and limits for all containers
  for deployment in "${deployment_names[@]}"; do
    if [[ " ${exclude_deployments[@]} " =~ " $deployment " ]]; then
      # Skip deployments that are in the exclusion list
      continue
    fi

    kubectl patch deployment "$deployment" -n "$namespace" --type='json' -p='[
      {"op": "remove", "path": "/spec/template/spec/containers/0/resources/requests/mem"},
      {"op": "remove", "path": "/spec/template/spec/containers/0/resources/limits/mem"}
    ]'
  done
}


remove_memory_field() {
  local namespace="$1"
  local exclude_deployments=("${@:2}")

  # Get a list of all deployments in the specified namespace
  local deployment_names=($(kubectl get deployments -n "$namespace" -o jsonpath='{.items[*].metadata.name}'))

  # Loop through the deployments and update CPU requests and limits for all containers
  for deployment in "${deployment_names[@]}"; do
    if [[ " ${exclude_deployments[@]} " =~ " $deployment " ]]; then
      # Skip deployments that are in the exclusion list
      continue
    fi

    kubectl patch deployment "$deployment" -n "$namespace" --type='json' -p='[
      {"op": "remove", "path": "/spec/template/spec/containers/0/resources/requests/memory"},
      {"op": "remove", "path": "/spec/template/spec/containers/0/resources/limits/memory"}
    ]'
  done
}

update_cpu_and_memory() {
  local namespace="$1"
  local exclude_deployments=("${@:2}")
  local cpu_request="1"
  local memory_request=""
  local cpu_limit="1"
  local memory_limit=""

  # Get a list of all deployments in the specified namespace
  local deployment_names=($(kubectl get deployments -n "$namespace" -o jsonpath='{.items[*].metadata.name}'))

  # Loop through the deployments and update resource requests and limits for all containers
  for deployment in "${deployment_names[@]}"; do
    if [[ " ${exclude_deployments[@]} " =~ " $deployment " ]]; then
      # Skip deployments that are in the exclusion list
      continue
    fi

    kubectl patch deployment "$deployment" -n "$namespace" --type='json' -p='[
      {"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/cpu", "value": "'"$cpu_request"'"},
      {"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/memory", "value": "'"$memory_request"'"},
      {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/cpu", "value": "'"$cpu_limit"'"},
      {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": "'"$memory_limit"'"}
    ]'
  done
}

update_cpu() {
  local namespace="$1"
  local exclude_deployments=("${@:2}")
  local cpu_request="0.1"
  local cpu_limit="5"

  # Get a list of all deployments in the specified namespace
  local deployment_names=($(kubectl get deployments -n "$namespace" -o jsonpath='{.items[*].metadata.name}'))

  # Loop through the deployments and update CPU requests and limits for all containers
  for deployment in "${deployment_names[@]}"; do
    if [[ " ${exclude_deployments[@]} " =~ " $deployment " ]]; then
      # Skip deployments that are in the exclusion list
      continue
    fi

    kubectl patch deployment "$deployment" -n "$namespace" --type='json' -p='[
      {"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/cpu", "value": "'"$cpu_request"'"},
      {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/cpu", "value": "'"$cpu_limit"'"}
    ]'
  done
}

update_cpu_request() {
  local namespace="$1"
  local exclude_deployments=("${@:2}")
  local cpu_request="0.5"

  # Get a list of all deployments in the specified namespace
  local deployment_names=($(kubectl get deployments -n "$namespace" -o jsonpath='{.items[*].metadata.name}'))

  # Loop through the deployments and update CPU requests and limits for all containers
  for deployment in "${deployment_names[@]}"; do
    if [[ " ${exclude_deployments[@]} " =~ " $deployment " ]]; then
      # Skip deployments that are in the exclusion list
      continue
    fi

    kubectl patch deployment "$deployment" -n "$namespace" --type='json' -p='[
      {"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/cpu", "value": "'"$cpu_request"'"},
    ]'
  done
}


# Usage:
#update_cpu_and_memory default slate-controller
update_cpu default slate-controller
# remove_cpu_limit default slate-controller
#remove_mem default slate-controller

