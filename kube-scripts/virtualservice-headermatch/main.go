package main

func main() {
	/*
		For every service,
		1. Get the deployments for each service, and the regions they are in
		2. Create destinationrules for every service, subsetted by region
		3. Create virtualservices for every service, performing header match based on x-slate-routeto header, keyed by region
	
	*/
}
