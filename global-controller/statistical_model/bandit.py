import numpy as np
import random

class RobustEpsilonGreedyBandit:
    def __init__(self, actions, expected_latencies, epsilon=0.1, min_traffic=10):
        self.actions = actions  # List of offloading schedules
        self.epsilon = epsilon  # Exploration probability
        self.expected_latencies = expected_latencies  # Expected latency per cluster
        self.min_traffic = min_traffic  # Minimum traffic to each cluster
        self.action_rewards = np.zeros(len(actions))  # Stores the average reward for each action
        self.action_counts = np.zeros(len(actions))  # Tracks how many times each action is chosen

    def select_action(self, actual_latencies):
        guided_exploration = True
        if guided_exploration:
            if random.random() < self.epsilon:
                print("Exploration")
                # Exploration phase: Guided by actual vs expected latencies
                return self.generate_guided_action(actual_latencies)
            else:
                print("Exploitation")
                # Exploitation: Choose the action with the highest average reward
                return self.actions[np.argmax(self.action_rewards)]
        else:
            if random.random() < self.epsilon:
                # Exploration phase: Randomly choose an action
                return self.generate_random_action()
            else:
                # Exploitation: Choose the action with the highest average reward
                return self.actions[np.argmax(self.action_rewards)]

    def generate_guided_action(self, actual_latencies):
        # Ensure actual latencies are not too small to avoid division by near-zero values
        epsilon_safe_latencies = [max(lat, 1e-6) for lat in actual_latencies]
        # Compute weights based on actual and expected latencies
        weights = [self.expected_latencies[i] / epsilon_safe_latencies[i] for i in range(len(epsilon_safe_latencies))]
        total_weight = sum(weights)
        proportion = [str(int(weight / total_weight * 100))+"%" for weight in weights]
        
        print(f"Expected latencies: {self.expected_latencies}")
        print(f"Actual latencies: {actual_latencies}")
        print(f"Computed weights: {weights}")
        print(f"Proportion: {proportion}")
        
        # Redistribute traffic proportionally based on weights
        adjusted_traffic = [(weight / total_weight) * (100 - self.min_traffic * len(weights)) for weight in weights]

        # Ensure no cluster gets less than the minimum traffic and adjust for rounding errors
        new_action = [max(traffic, self.min_traffic) for traffic in adjusted_traffic]
        total = sum(new_action)
        new_action = [(traffic / total) * 100 for traffic in new_action]  # Ensure sum equals 100%

        return new_action
    
    def generate_random_action(self):
        # Generate random traffic allocations that sum to 100%
        random_action = np.random.dirichlet(np.ones(len(self.expected_latencies))) * 100
        # Ensure each cluster gets at least the minimum traffic
        random_action = np.maximum(random_action, self.min_traffic)
        # Normalize to make sure the total equals 100%
        total = np.sum(random_action)
        return (random_action / total) * 100

    def update_rewards(self, action, reward):
        # Try to find if the action already exists in the actions list
        try:
            action_index = next(i for i, a in enumerate(self.actions) if np.allclose(np.round(a, 2), np.round(action, 2), atol=1e-2))
        except StopIteration:
            # If the action is new, add it to the list of actions
            self.actions.append(action)
            
            action_index = len(self.actions) - 1
            # Expand the rewards and counts arrays to track the new action
            self.action_rewards = np.append(self.action_rewards, 0)
            self.action_counts = np.append(self.action_counts, 0)

        # Increment the count for the chosen action
        self.action_counts[action_index] += 1
        # Update the running average reward for the chosen action
        n = self.action_counts[action_index]
        current_reward = self.action_rewards[action_index]
        new_reward = current_reward + (reward - current_reward) / n
        self.action_rewards[action_index] = new_reward

# Example usage
if __name__ == "__main__":
    # Define possible offloading schedules (actions)
    actions = [
        [30, 20, 50],  # {30% to east, 20% to south, 50% to west}
        [25, 25, 50],  # {25% to east, 25% to south, 50% to west}
        [35, 15, 50],  # {35% to east, 15% to south, 50% to west}
        # Add more actions as needed
    ]
    
    # Expected latency for each cluster (west, east, south)
    expected_latencies = [100, 80, 90]  # in milliseconds

    # Initialize the bandit with actions and expected latencies
    bandit = RobustEpsilonGreedyBandit(actions, expected_latencies, epsilon=0.1)

    # Simulate several rounds of exploration/exploitation
    for round in range(100):  # Example with 100 rounds of decision making
        # Actual latencies observed in this round
        print(f"\nRound {round + 1}")
        actual_latencies = [random.uniform(70, 110), random.uniform(60, 100), random.uniform(70, 110)]

        # Select an action based on actual latencies
        action = bandit.select_action(actual_latencies)

        # Simulate reward (negative of average latency)
        reward = -np.mean(actual_latencies)  # Replace with real reward

        # Update rewards for the selected action
        bandit.update_rewards(action, reward)
        
        print(f"Selected action {action} with reward {reward} (= {actual_latencies})")
    
    # After many rounds, print the best action (offloading schedule) found
    best_action_index = np.argmax(bandit.action_rewards)
    print(f"Best offloading schedule: {bandit.actions[best_action_index]} with reward {bandit.action_rewards[best_action_index]}")
