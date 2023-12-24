package main

import (
	"flag"
	"fmt"
	versionedistioclient "istio.io/client-go/pkg/clientset/versioned"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/util/homedir"
	"log"
)

func main() {
	/*
		For every service,
		1. Get the deployments for each service, and the regions they are in
		2. Create destinationrules for every service, subsetted by region
		3. Create virtualservices for every service, performing header match based on x-slate-routeto header, keyed by region
	*/
	regions := flag.String("regions", "us-east-1,us-west-1", "regions to check (comma separated, no spaces, like us-east-1,us-west-1)")
	deployments := flag.String("deployments", "", "deployments to duplicate into regions (comma separated, no spaces, like deployment1,deployment2). use -exclude to do all except these.")
	exclude := flag.Bool("exclude", false, "exclude the deployments specified in -deployments instead of including them")
	ns := flag.String("namespace", "default", "namespace to check")
	flag.Parse()

	home := homedir.HomeDir()
	kubeconfig := fmt.Sprintf("%s/.kube/config", home)
	config, err := clientcmd.BuildConfigFromFlags("", kubeconfig)
	if err != nil {
		panic(err.Error())
	}

	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		panic(err.Error())
	}
	svcClient := clientset.CoreV1().Services(*ns)

	restConfig, err := clientcmd.BuildConfigFromFlags("", kubeconfig)
	if err != nil {
		log.Fatalf("Failed to create k8s rest client: %s", err)
	}

	istioclient, err := versionedistioclient.NewForConfig(restConfig)
	if err != nil {
		log.Fatalf("Failed to create istio client: %s", err)
	}
	drClient := istioclient.NetworkingV1alpha3().DestinationRules(*ns)
	vsClient := istioclient.NetworkingV1alpha3().VirtualServices(*ns)

}
