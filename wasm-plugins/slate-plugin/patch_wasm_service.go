package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"github.com/tidwall/gjson"
	"github.com/tidwall/sjson"
	"io/ioutil"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/util/homedir"
)

func main() {
	// Load the kubeconfig file (for local or remote Kubernetes cluster)
	home := homedir.HomeDir()
	kubeconfig := fmt.Sprintf("%s/.kube/config", home)
	config, err := clientcmd.BuildConfigFromFlags("", kubeconfig)
	if err != nil {
		fmt.Printf("Failed to load kubeconfig: %v\n", err)
		return
	}

	// Create the Kubernetes client
	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		fmt.Printf("Failed to create Kubernetes client: %v\n", err)
		return
	}

	// Define variables
	configMapName := "shared-span-bootstrap-config"
	namespace := "default"
	wasmFilePath := "wasm-out/slate_service.wasm" // Path to your Wasm file

	// Step 1: Read the Wasm file
	wasmData, err := ioutil.ReadFile(wasmFilePath)
	if err != nil {
		fmt.Printf("Failed to read Wasm file: %v\n", err)
		return
	}

	// Step 2: Calculate SHA256 hash of the Wasm file
	hash := sha256.New()
	_, err = hash.Write(wasmData)
	if err != nil {
		fmt.Printf("Failed to hash Wasm file: %v\n", err)
		return
	}
	sha256Hash := hex.EncodeToString(hash.Sum(nil))

	// Step 3: Get the existing ConfigMap
	configMap, err := clientset.CoreV1().ConfigMaps(namespace).Get(context.TODO(), configMapName, metav1.GetOptions{})
	if err != nil {
		fmt.Printf("Failed to get ConfigMap: %v\n", err)
		return
	}

	// Step 4: Retrieve the current custom_bootstrap.json content
	bootstrapConfig, ok := configMap.Data["custom_bootstrap.json"]
	if !ok {
		fmt.Println("custom_bootstrap.json not found in ConfigMap")
		return
	}

	// Step 5: Use gjson to verify that the sha256 field exists
	jsonPath := "bootstrap_extensions.0.typed_config.config.vm_config.code.remote.sha256"
	currentSha256 := gjson.Get(bootstrapConfig, jsonPath)
	if !currentSha256.Exists() {
		fmt.Println("sha256 field not found in the JSON")
		return
	}

	// Step 6: Use sjson to set the new sha256 value in the JSON
	updatedBootstrapConfig, err := sjson.Set(bootstrapConfig, jsonPath, sha256Hash)
	if err != nil {
		fmt.Printf("Failed to set new sha256 value in JSON: %v\n", err)
		return
	}

	// Step 7: Update the ConfigMap with the new JSON configuration
	configMap.Data["custom_bootstrap.json"] = updatedBootstrapConfig

	// Step 8: Update the ConfigMap in Kubernetes
	_, err = clientset.CoreV1().ConfigMaps(namespace).Update(context.TODO(), configMap, metav1.UpdateOptions{})
	if err != nil {
		fmt.Printf("Failed to update ConfigMap: %v\n", err)
		return
	}

	fmt.Println("ConfigMap updated successfully with new Wasm SHA256 hash:", sha256Hash)
}
