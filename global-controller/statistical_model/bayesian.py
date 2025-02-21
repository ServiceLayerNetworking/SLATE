import numpy as np
import emcee
import matplotlib.pyplot as plt
from scipy.stats import lognorm
import time

# Initialize latency data arrays for each replica
latency_data_west = []
latency_data_east = []
latency_data_south = []

# Step 1: Define the log-likelihood function
def log_likelihood(params, data):
    mu, sigma = params
    if sigma <= 0:
        return -np.inf
    return np.sum(lognorm.logpdf(data, s=sigma, scale=np.exp(mu)))

# Step 2: Define the log-prior function
def log_prior(params):
    mu, sigma = params
    if 0 < sigma < 10:  # A weak prior on sigma
        return 0.0  # Flat prior
    return -np.inf  # Invalid prior values

# Step 3: Define the posterior function (log-posterior)
def log_posterior(params, data):
    lp = log_prior(params)
    if not np.isfinite(lp):
        return -np.inf
    return lp + log_likelihood(params, data)

# Step 4: Set up MCMC for real-time updates
def run_mcmc(latency_data, n_steps=100, initial_pos=None):
    n_walkers = 32  # Number of MCMC walkers
    n_dim = 2  # Two parameters: mu and sigma
    if len(latency_data) == 0:  # No data, return empty
        return None
    initial_guess = [np.log(np.mean(latency_data)), np.std(latency_data)]
    initial_pos = initial_pos or initial_guess + 0.1 * np.random.randn(n_walkers, n_dim)

    sampler = emcee.EnsembleSampler(n_walkers, n_dim, log_posterior, args=[latency_data])
    sampler.run_mcmc(initial_pos, n_steps)
    return sampler

# Step 5: Function to update posterior distributions based on new observations
def update_posterior(new_data, replica_data, n_steps=100):
    # Add new data to the existing latency data
    replica_data.extend(new_data)
    # Run MCMC with updated data
    return run_mcmc(replica_data, n_steps)

# Example functions to collect real latency data from logs or metrics
# These should be replaced by actual data collection methods
def collect_latency_from_metrics(replica_name):
    # Here you would fetch actual observed latency data from a log or metrics system
    if replica_name == 'west':
        return np.random.lognormal(mean=2, sigma=0.5, size=50)  # Simulate real data
    elif replica_name == 'east':
        return np.random.lognormal(mean=2.2, sigma=0.4, size=50)  # Simulate real data
    elif replica_name == 'south':
        return np.random.lognormal(mean=1.8, sigma=0.6, size=50)  # Simulate real data

# Step 6: Periodically update with real latency data for each replica
def update_all_replicas():
    # Fetch real latency data
    new_data_west = collect_latency_from_metrics('west')
    new_data_east = collect_latency_from_metrics('east')
    new_data_south = collect_latency_from_metrics('south')

    # Update posterior distributions for each replica
    sampler_west = update_posterior(new_data_west, latency_data_west)
    sampler_east = update_posterior(new_data_east, latency_data_east)
    sampler_south = update_posterior(new_data_south, latency_data_south)
    
    return sampler_west, sampler_east, sampler_south

# Step 7: Calculate 95% credible interval
def calculate_credible_interval(samples, credibility=0.95):
    lower = np.percentile(samples, (1 - credibility) / 2 * 100)
    upper = np.percentile(samples, (1 + credibility) / 2 * 100)
    return lower, upper

# Step 8: Compare the posterior distributions of the replicas with 95% confidence
def compare_replicas(sampler_west, sampler_east, sampler_south):
    if sampler_west is None or sampler_east is None or sampler_south is None:
        print("Insufficient data for comparison.")
        return

    # Extract samples from the posterior
    samples_west = sampler_west.get_chain(flat=True)
    samples_east = sampler_east.get_chain(flat=True)
    samples_south = sampler_south.get_chain(flat=True)

    # Calculate 95% credible intervals for the posterior means (mu) of each replica
    ci_west = calculate_credible_interval(samples_west[:, 0])
    ci_east = calculate_credible_interval(samples_east[:, 0])
    ci_south = calculate_credible_interval(samples_south[:, 0])

    # Print the credible intervals for each replica
    print(f"- West replica 95% credible interval for mean latency (mu): ({round(ci_west[0], 2)}, {round(ci_west[1], 2)})")
    print(f"- East replica 95% credible interval for mean latency (mu): ({round(ci_east[0], 2)}, {round(ci_east[1], 2)})")
    print(f"- South replica 95% credible interval for mean latency (mu): ({round(ci_south[0], 2)}, {round(ci_south[1], 2)})")

    # Step 9: Compare credible intervals to decide if one replica has significantly higher latency
    # Check if one replica has a credible interval that is entirely higher than the others
    if ci_east[0] > ci_west[1] and ci_east[0] > ci_south[1]:
        print("Decision: East replica has significantly higher latency than both West and South replicas with 95% confidence.")
    elif ci_west[0] > ci_east[1] and ci_west[0] > ci_south[1]:
        print("Decision: West replica has significantly higher latency than both East and South replicas with 95% confidence.")
    elif ci_south[0] > ci_east[1] and ci_south[0] > ci_west[1]:
        print("Decision: South replica has significantly higher latency than both East and West replicas with 95% confidence.")
    else:
        print("Decision: No replica has a significantly higher latency with 95% confidence. Credible intervals overlap.")

# Step 10: Run the process for real-time inference
def run_real_time_inference():
    counter = 0
    while True:
        # Update the posterior based on new data from real observations
        print("-"*20, f"Round: {counter}", "-"*20)
        sampler_west, sampler_east, sampler_south = update_all_replicas()
        # Compare the replicas with 95% credible intervals and make a decision
        compare_replicas(sampler_west, sampler_east, sampler_south)
        # Sleep or wait for the next batch of latency data (e.g., every few seconds or minutes)
        time.sleep(1)  # Adjust the delay as needed for your use case
        counter += 1
        
# Start the real-time inference process
run_real_time_inference()
