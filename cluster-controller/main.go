package main

import (
	"bytes"
	"fmt"
	"github.com/gin-gonic/gin"
	"strconv"
	"strings"
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

func main() {
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
	load := strings.Split(buf.String(), " ")
	rps, err := strconv.Atoi(load[0])
	if err != nil {
		fmt.Printf("unable to convert %d to int: %v", load[0], err)
		return
	}
	latency, err := strconv.Atoi(load[1])
	if err != nil {
		fmt.Printf("unable to convert %d to int: %v", load[1], err)
		return
	}
	podName := c.Request.Header.Get("x-slate-podname")
	svcName := c.Request.Header.Get("x-slate-servicename")
	fmt.Printf("POD %v SVC %v STATS: RPS %x, LATENCY: %d\n", podName, svcName, rps, latency)
	c.Status(200)
}
