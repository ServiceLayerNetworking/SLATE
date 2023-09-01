package main

import (
	"bytes"
	"fmt"
	"github.com/gin-gonic/gin"
	"strconv"
	"strings"
)

var ()

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
	fmt.Printf("POD %v SVC %v STATS: RPS %d, LATENCY: %d\n", podName, svcName, rps, latency)
	c.Status(200)
}
