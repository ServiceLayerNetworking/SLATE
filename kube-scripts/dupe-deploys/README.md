# Automatically Duplicate Deployments

Usage:

```
go build -o .
./dupedeploy -deployments="foo,bar" -regions="us-west-1,us-east-1"
```

This command will take the deployments you provide and create `n` new deployments with the region appended to the name, along with setting the nodeSelector to that region label. It will then delete the original deployment.

## Flags

`-deployments`: takes list of deployments separated by commas. Default is empty.

`-regions`: takes a list of regions to duplicate to. Default is "us-west-1, us-east-1"

`-justswitchimage`: does not duplicate deployments, and just performs the operations of switching the image, adjusting resource limits, etc on the specified deployments. (default false).

`-exclude`: when specified, the script will take every deployment in the default namespace, remove the deployments specified in `-deployments`, and perform the operations on that set of deployments. (default false)
