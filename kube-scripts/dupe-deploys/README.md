# Automatically Duplicate Deployments

Usage:

```
go build -o .
./dupedeploy -deployments="foo,bar" -regions="us-west-1,us-east-1"
```

This command will take the deployments you provide and create `n` new deployments with the region appended to the name, along with setting the nodeSelector to that region label. It will then delete the original deployment.
