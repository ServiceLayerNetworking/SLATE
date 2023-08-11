# SLATE

This repository houses all the components of the Service Layer Traffic Engineering System.

There are three major components:
- proxy-filters (Envoy C++ Filter)
- cluster-controller (Go gRPC service)
- global-controller (G gRPC service)

`protos/` contains all the protobuf definitions for the gRPC services (proxy <-> cluster-controller, cluster-controller <-> global-controller).

The cluster controller exposes a service that the proxies talk tom and the global controller exposes a service cluster controllers talk to.