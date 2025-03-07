package main

import (
	"context"
	"flag"
	"fmt"
	// v13 "k8s.io/api/core/v1"
	// "k8s.io/apimachinery/pkg/api/resource"
	"strings"

	v12 "k8s.io/api/apps/v1"
	v1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/util/homedir"
)

func main() {
	regions := flag.String("regions", "us-east-1,us-west-1", "regions to check (comma separated, no spaces, like us-east-1,us-west-1)")
	deployments := flag.String("deployments", "", "deployments to duplicate into regions (comma separated, no spaces, like deployment1,deployment2). use -exclude to do all except these.")
	exclude := flag.Bool("exclude", false, "exclude the deployments specified in -deployments instead of including them")
	ns := flag.String("namespace", "default", "namespace to check")
	justswitchimage := flag.Bool("justswitchimage", false, "just switch the image of all specified deployments, don't create new deployments")
	excludeconsul := flag.Bool("excludeconsul", false, "remove consul clusterIP from allowed outbound traffic proxied")
	sharedspancontext := flag.Bool("sharedspancontext", true, "use shared span context bootstrap")
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
	deploymentsClient := clientset.AppsV1().Deployments(*ns)
	regionsList := strings.Split(*regions, ",")
	var deploymentsList []string
	if *exclude {
		// run all deployments except the ones specified
		deploymentsList = []string{}
		excludedDeployments := strings.Split(*deployments, ",")
		deployments, err := deploymentsClient.List(context.TODO(), v1.ListOptions{})
		if err != nil {
			panic(err.Error())
		}
		// todo refactor this to be a map instead of slice (n vs n^2)
		for _, deployment := range deployments.Items {
			// if deployment is in the list of excluded deployments, skip it
			keep := true
			for _, excluded := range excludedDeployments {
				if excluded == deployment.Name {
					keep = false
					break
				}
			}
			if keep {
				deploymentsList = append(deploymentsList, deployment.Name)
			}
		}
	} else {
		deploymentsList = strings.Split(*deployments, ",")
	}

	consulClusterIP := ""
	if *excludeconsul {
		consul, err := clientset.CoreV1().Services(*ns).Get(context.TODO(), "consul", v1.GetOptions{})
		if err != nil {
			fmt.Printf("couldn't get consul service: %v.\n", err)
		} else {
			consulClusterIP = consul.Spec.ClusterIP
		}
	}
	replMap := map[string]string{
		"gcr.io/google-samples/microservices-demo/frontend:v0.10.1": "docker.io/adiprerepa/boutique-frontend:latest",
		"gcr.io/google-samples/microservices-demo/checkoutservice:v0.10.1": "docker.io/adiprerepa/boutique-checkout:latest",
		"gcr.io/google-samples/microservices-demo/recommendationservice:v0.10.1": "docker.io/adiprerepa/boutique-recommendation:latest",
		"us-central1-docker.pkg.dev/google-samples/microservices-demo/frontend:v0.10.2": "docker.io/adiprerepa/boutique-frontend:latest",
		"us-central1-docker.pkg.dev/google-samples/microservices-demo/checkoutservice:v0.10.2": "docker.io/adiprerepa/boutique-checkout:latest",
		"us-central1-docker.pkg.dev/google-samples/microservices-demo/recommendationservice:v0.10.2": "docker.io/adiprerepa/boutique-recommendation:latest",
	}
	if *justswitchimage {
		fmt.Printf("switching image of deployments %v from deathstarbench to adiprerepa.\n", deploymentsList)
		for _, deployment := range deploymentsList {
			if strings.TrimSpace(deployment) == "" {
				continue
			}
			// get original deployment
			originalDeployment, err := deploymentsClient.Get(context.TODO(), deployment, v1.GetOptions{})
			if err != nil {
				fmt.Printf("Ignoring deployment %s: %v.", deployment, err)
				continue
			}
			if repl, ok := replMap[originalDeployment.Spec.Template.Spec.Containers[0].Image]; ok {
				originalDeployment.Spec.Template.Spec.Containers[0].Image = repl
			}
			// originalDeployment.Spec.Template.Spec.Containers[0].Resources.Limits = map[v13.ResourceName]resource.Quantity{
			// 	v13.ResourceCPU: resource.MustParse("5"),
			// }
			//fmt.Printf("new annotations: %v\n", originalDeployment.Annotations)
			_, err = deploymentsClient.Update(context.TODO(), originalDeployment, v1.UpdateOptions{})
			if err != nil {
				fmt.Printf("couldn't update deployment %s: %v.\n", originalDeployment.Name, err)
				continue
			}
			fmt.Printf("updated deployment %s.\n", originalDeployment.Name)
		}
		fmt.Printf("done.\n")
		return
	}
	

	fmt.Printf("processing deployments %v in regions %v.\n", deploymentsList, regionsList)
	for _, deployment := range deploymentsList {

		if strings.TrimSpace(deployment) == "" {
			continue
		}
		// get original deployment
		originalDeployment, err := deploymentsClient.Get(context.TODO(), deployment, v1.GetOptions{})
		if err != nil {
			fmt.Printf("Ignoring deployment %s: %v.", deployment, err)
			continue
		}

		failsafe := false
		for _, region := range regionsList {
			// create new deployment
			newDeployment := &v12.Deployment{}

			newDeployment.Name = fmt.Sprintf("%s-%s", deployment, region)
			newDeployment.Spec = *originalDeployment.Spec.DeepCopy()
			newDeployment.Spec.Template.Spec.NodeSelector = map[string]string{"topology.kubernetes.io/zone": region}
			if strings.Contains(newDeployment.Spec.Template.Spec.Containers[0].Image, "deathstarbench") {
				newDeployment.Spec.Template.Spec.Containers[0].Image = strings.ReplaceAll(newDeployment.Spec.Template.Spec.Containers[0].Image, "deathstarbench", "adiprerepa")
			}
			if repl, ok := replMap[newDeployment.Spec.Template.Spec.Containers[0].Image]; ok {
				newDeployment.Spec.Template.Spec.Containers[0].Image = repl
			}
			labels := newDeployment.Spec.Template.GetLabels()
			labels["region"] = region
			newDeployment.Spec.Template.SetLabels(labels)
			if *excludeconsul {
				if newDeployment.Spec.Template.Annotations == nil {
					newDeployment.Spec.Template.Annotations = map[string]string{"traffic.sidecar.istio.io/excludeOutboundIPRanges": consulClusterIP + "/32"}
				} else {
					newDeployment.Spec.Template.Annotations["traffic.sidecar.istio.io/excludeOutboundIPRanges"] = consulClusterIP + "/32"
				}
			}

			if *sharedspancontext {
				if newDeployment.Spec.Template.Annotations == nil {
					newDeployment.Spec.Template.Annotations = map[string]string{}
				}
				newDeployment.Spec.Template.Annotations["sidecar.istio.io/bootstrapOverride"] = "shared-span-bootstrap-config"
			}

			_, err = deploymentsClient.Create(context.TODO(), newDeployment, v1.CreateOptions{})
			if err != nil {
				fmt.Printf("couldn't create deployment %s: %v.\n", newDeployment.Name, err)
				failsafe = true
				continue
			}
			fmt.Printf("created deployment %s in region %s.\n", newDeployment.Name, region)
		}
		if failsafe {
			fmt.Printf("skipping deletion of original deployment %s.\n", deployment)
			continue
		}
		// delete original deployment
		err = deploymentsClient.Delete(context.TODO(), deployment, v1.DeleteOptions{})
		if err != nil {
			fmt.Printf("couldn't delete deployment %s: %v.\n", deployment, err)
			continue
		}
		fmt.Printf("processed & deleted original deployment %s.\n", deployment)
	}
	fmt.Printf("done.\n")
}
