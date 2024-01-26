# Routing Config Generator

This script generates Istio VirtualService and DestinationRule configuration for the specified services to keep traffic in-region when possible and allow header-based traffic redirection.

For each service, a DestinationRule is created, with the name of each subset being the region label it is matching. A corresponding VirtualService is created that first checks (in http) for the `x-slate-routeto` header match, and than tries to keep traffic local based on the traffic source workload labels. If the traffic is TCP, only source labels are matched (no redirection support).

Usage:

```
./vs-headermatch -services="foo,bar" -regions="us-west-1,us-east-1" -exclude
```

Flags:

`-services`: comma separated list of services to apply configuration to. Defaults to nothing.

`-regions`: comma separated list of regions to apply traffic enforcement to. Defaults to "us-west-1,us-east-1".

`-exclude`: if specified, the config will be applied to all services in the default namespace *except* for the services specified in `-services`.

