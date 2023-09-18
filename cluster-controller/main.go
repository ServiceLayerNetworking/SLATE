package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"github.com/gin-gonic/gin"
	"k8s.io/client-go/rest"
	"net/http"
	"os"
)

/*
/proxyLoad is expected to return http text/plain in the following format:

<requests per second> <header>
<requests per second_2> <header_2>
...
<requests per second_n> <header_n>

where <header> is a string that can be used to identify the remote cluster to route to.
where <requests per second_n-1> > <requests per second_n>
(requests_per_second entries are sorted in descending order)
*/

var clusterId string
var ic *IstioController

func init() {
	clusterId = os.Getenv("CLUSTER_ID")
	if clusterId == "" {
		clusterId = "unknown-cluster"
	}
	//cli, err := rest.InClusterConfig()
	
}

type ClusterControllerRequest struct {
	ClusterId   string `json:"clusterId"`
	PodName     string `json:"podName"`
	ServiceName string `json:"serviceName"`
	Body        string `json:"body"`
}

type IstioController struct {
	client *rest.RESTClient
}

func (ic *IstioController) UpdatePolicy(routingPcts map[string]string) map[string]string {
	// somehow map subset->cluster

	return nil
}

func main() {
	r := gin.New()
	r.POST("/proxyLoad", HandleProxyLoad)

	r.Run()
}

func HandleProxyLoad(c *gin.Context) {
	fmt.Printf("HJERE\n")
	buf := new(bytes.Buffer)
	if _, err := buf.ReadFrom(c.Request.Body); err != nil {
		fmt.Printf("error reading from request body %v", err)
		return
	}
	reqBody := buf.String()

	podName := c.Request.Header.Get("x-slate-podname")
	svcName := c.Request.Header.Get("x-slate-servicename")

	clusterControllerRequest := ClusterControllerRequest{
		ClusterId:   clusterId,
		PodName:     podName,
		ServiceName: svcName,
		Body:        reqBody,
	}
	globalControllerReqBody, err := json.Marshal(clusterControllerRequest)
	if err != nil {
		fmt.Printf("error marshalling cluster controller request %v", err)
		return
	}
	fmt.Printf("cluster controller request body: %s", string(globalControllerReqBody))
	resp, err := http.Post("http://slate-global-controller:8080/clusterLoad", "application/json", bytes.NewBuffer(globalControllerReqBody))
	if err != nil {
		fmt.Printf("error posting to global controller %v", err)
		return
	}
	// print response body
	buf = new(bytes.Buffer)
	if _, err := buf.ReadFrom(resp.Body); err != nil {
		fmt.Printf("error reading from response body %v", err)
		return
	}
	respBody := buf.String()
	fmt.Printf("global controller response body: %s", respBody)
	var recommendations map[string]string
	if err = json.Unmarshal([]byte(respBody), &recommendations); err != nil {
		fmt.Printf("error unmarshalling global controller response %v", err)
		return
	}
	config, err := rest.InClusterConfig()
	if err != nil {
		fmt.Printf("error getting in cluster config %v", err)
		return
	}
	c.Status(200)
}
