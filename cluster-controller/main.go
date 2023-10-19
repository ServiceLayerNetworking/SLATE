package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"

	"github.com/gin-gonic/gin"
	versionedclient "istio.io/client-go/pkg/clientset/versioned"
	v1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/rest"
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
var global_ic *versionedclient.Clientset

func init() {
	clusterId = os.Getenv("CLUSTER_ID")
	if clusterId == "" {
		clusterId = "unknown-cluster"
	}

}

type ClusterControllerRequest struct {
	ClusterId   string `json:"clusterId"`
	PodName     string `json:"podName"`
	ServiceName string `json:"serviceName"`
	Body        string `json:"body"`
}

func UpdatePolicy(routingPcts map[int]string) error {

	// somehow map subset->cluster
	// vs, err := global_ic.NetworkingV1alpha3().VirtualServices("default").Get(context.Background(), "bookinfo", v1.GetOptions{})
	// if err != nil {
	// 	fmt.Printf("error getting virtual service %v", err)
	// 	return err
	// }
	// fmt.Printf("GOT virtual service: %s\n", vs.Name)
	// // us-west is 0
	// // us-east is 1
	// // update routing percentages
	// west_weight := int32(0)
	// east_weight := int32(0)
	// // if clusterId == "us-west" {
	// // 	val, exists := routingPcts[1]
	// // 	if !exists {
	// // 		// nothing to update
	// // 		return nil
	// // 	}
	// // 	raw, err := strconv.ParseFloat(val, 64)
	// // 	if err != nil {
	// // 		fmt.Printf("error parsing float %v", err)
	// // 		return err
	// // 	}
	// // 	for _, httpRoute := range vs.Spec.Http {
	// // 		for _, route := range httpRoute.Route {
	// // 			if route.Destination.Subset == "east" {
	// // 				east_weight = int32(raw * 100)
	// // 				if east_weight > 0 {
	// // 					east_weight = 50
	// // 				}
	// // 				route.Weight = east_weight
	// // 			} else if route.Destination.Subset == "west" {
	// // 				west_weight = int32(100 - raw*100)
	// // 				if west_weight < 100 {
	// // 					west_weight = 50
	// // 				}
	// // 				route.Weight = west_weight
	// // 			}
	// // 		}
	// // 	}
	// // } else {
	// // 	val, exists := routingPcts[0]
	// // 	if !exists {
	// // 		return nil
	// // 	}
	// // 	raw, err := strconv.ParseFloat(val, 64)
	// // 	if err != nil {
	// // 		fmt.Printf("error parsing float %v", err)
	// // 		return err
	// // 	}
	// // 	for _, httpRoute := range vs.Spec.Http {
	// // 		for _, route := range httpRoute.Route {
	// // 			if route.Destination.Subset == "west" {
	// // 				route.Weight = int32(raw * 100)
	// // 				west_weight = int32(raw * 100)
	// // 			} else if route.Destination.Subset == "east" {
	// // 				route.Weight = int32(100 - raw*100)
	// // 				east_weight = int32(100 - raw*100)
	// // 			}
	// // 		}
	// // 	}
	// // }
	// fmt.Printf("UpdatePolicy, I am %s, west,%d, east,%d\n", clusterId, west_weight, east_weight)

	// _, err = global_ic.NetworkingV1alpha3().VirtualServices("default").Update(context.Background(), vs, v1.UpdateOptions{})
	// if err != nil {
	// 	fmt.Printf("error updating virtual service %v", err)
	// 	return err
	// }
	return nil
}

func main() {

	// get all deployments in default namespace
	//deployments, err := cs.NetworkingV1alpha3().VirtualServices("default").List(context.Background(), v1.ListOptions{})
	//if err != nil {
	//	fmt.Printf("error getting deployments %v", err)
	//	return
	//}
	//fmt.Printf("LEN DEPLOY: %v", len(deployments.Items))
	cc, err := rest.InClusterConfig()
	if err != nil {
		fmt.Printf("error getting in cluster config %v", err)
		return
	}
	ic, err := versionedclient.NewForConfig(cc)
	if err != nil {
		fmt.Printf("error getting istio client %v", err)
		return
	}
	_, err = ic.NetworkingV1alpha3().VirtualServices("default").Get(context.Background(), "bookinfo", v1.GetOptions{})
	if err != nil {
		fmt.Printf("error getting virtual service %v", err)
		return
	}
	global_ic = ic

	if err := UpdatePolicy(map[int]string{0: "0.0", 1: "0.0"}); err != nil {
		fmt.Printf("error updating policy %v", err)
	}

	r := gin.New()
	r.POST("/proxyLoad", HandleProxyLoad)
	r.Run()
}

func HandleProxyLoad(c *gin.Context) {
	buf := new(bytes.Buffer)
	if _, err := buf.ReadFrom(c.Request.Body); err != nil {
		fmt.Printf("error reading from request body %v", err)
		return
	}

	// buf_for_header := new(bytes.Buffer)
	// if _, err := buf_for_header.ReadFrom(c.Request.Header); err != nil {
	// 	fmt.Printf("error reading from request header %v", err)
	// 	return
	// }
	// reqHeader := buf_for_header.String()
	reqBody := buf.String()
	// fmt.Printf("#################### reqBody: %s", reqBody)

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
	if respBody == "" {
		return
	}
	if resp.StatusCode != 200 {
		fmt.Printf("error response from global controller %v", respBody)
		return
	}
	fmt.Printf("global controller response body: %s", respBody)
	var recommendations map[int]string
	if err = json.Unmarshal([]byte(respBody), &recommendations); err != nil {
		fmt.Printf("error unmarshalling global controller response %v", err)
		return
	}
	if err := UpdatePolicy(recommendations); err != nil {
		fmt.Printf("error updating policy %v", err)
		return
	}

	c.Status(200)
}
