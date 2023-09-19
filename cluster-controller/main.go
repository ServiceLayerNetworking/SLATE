package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"github.com/gin-gonic/gin"
	versionedclient "istio.io/client-go/pkg/clientset/versioned"
	v1 "k8s.io/apimachinery/pkg/apis/meta/v1"
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
	config, err := rest.InClusterConfig()
	if err != nil {
		fmt.Printf("error getting in cluster config %v", err)
		return
	}
	cs, err := versionedclient.NewForConfig(config)
	if err != nil {
		fmt.Printf("error getting istio client %v", err)
		return
	}
	ic = &IstioController{}
	ic.istioClient = cs
}

type ClusterControllerRequest struct {
	ClusterId   string `json:"clusterId"`
	PodName     string `json:"podName"`
	ServiceName string `json:"serviceName"`
	Body        string `json:"body"`
}

type IstioController struct {
	istioClient *versionedclient.Clientset
}

func (ic *IstioController) UpdatePolicy(routingPcts map[string]string) map[string]string {
	// somehow map subset->cluster
	ic.istioClient.NetworkingV1alpha3().VirtualServices("sample").G(context.TODO(), v1.ListOptions{})
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

	c.Status(200)
}
