"""
Defines an interface for a Markov Reward Process
"""

import numpy as np

from .markov_process import MarkovProcess


class MarkovRewardProcess(MarkovProcess):
    """
    A Markov Reward Process is a tuple <S, P, R, gamma>
    S: Finite set of states
    P: State transition matrix
    R: State reward function
    gamma: Discount factor
    """

    def __init__(self):
        """
        Constructor
        """

        # A list of parameters that should be set by any sub-class
        self.state_set
        self.terminal_state_set
        self.transition_matrix
        self.reward_mapping
        self.discount_factor

        raise NotImplementedError


    def __str__(self):
        """
        Get string representation
        """
        return "<MarkovRewardProcess(\n  S: {}\n  P: {}\n  R: {}\n  gamma: {}\n)>".format(
            str(self.state_set).replace("\n", "\n     "),
            str(self.transition_matrix).replace("\n", "\n     "),
            str(self.reward_mapping).replace("\n", "\n     "),
            self.discount_factor
        )


    def get_reward_mapping(self):
        """
        Returns the reward mapping {s_i: r_i}
        """
        return self.reward_mapping


    def get_reward_vector(self):
        """
        Returns the reward vector [r_i, ...] for every state s_i
        in the ordered list state_set
        """
        reward_vector = np.array([])
        for state in self.state_set:
            reward_vector = np.append(reward_vector, self.reward_mapping[state])
        return reward_vector


    def solve_bellman_equation(self):
        """
        Solves the Bellman equation for the MRP giving
        v = ((I - discount*P)^-1) * R
        This is only feasible for small processes
        """

        assert self.discount_factor != 1, \
            "Cannot solve bellman equation for infinitely far-sighted process (results in a singular matrix inversion)"

        value_vector = np.matmul(
            np.linalg.inv(
                np.identity(
                    len(self.state_set)
                ) - self.discount_factor * self.transition_matrix
            ),
            self.get_reward_vector()
        )

        self.value_map = {}
        for i in range(len(self.state_set)):
            self.value_map[self.state_set[i]] = value_vector[i]

        return self.value_map



    def get_discount_factor(self):
        """
        Returns the discount factor
        """
        return self.discount_factor


    def get_expected_reward(self, current_state):
        """
        Returns the expected reward at time t+1 given we are currently in the given state s_t
        """

        assert current_state in self.state_set, \
            "Given state ({}) is not in state set".format(current_state)

        assert current_state in self.reward_mapping, \
            "Given state ({}) is not in reward mapping".format(current_state)

        return self.reward_mapping[current_state]


    def get_value(self, current_state, *, num_rollouts=1000, max_length=None):
        """
        Computes an expectation of return up to horizon max_length from the current state
        """

        assert current_state in self.state_set, \
            "Given state ({}) is not in state set".format(current_state)

        value = 0
        for i in range(num_rollouts):
            value += self.get_return(current_state, max_length=max_length)
        value /= num_rollouts

        return value


    def get_return(self, current_state, *, max_length=None):
        """
        Rolls out the MRP once from the given state and calculates the return
        """

        assert current_state in self.state_set, \
            "Given state ({}) is not in state set".format(current_state)

        # Perform rollout
        history = self.rollout(current_state, max_length=max_length)
        
        # Slice record array to get rewards
        rewards = history['reward']

        # Remove None types (e.g. initial state has reward of None)
        rewards = rewards[rewards != None]

        # Apply discount factor
        discounted_rewards = np.empty_like(rewards)
        for i in range(len(rewards)):
            reward = rewards[i]
            discounted_rewards[i] = reward * self.discount_factor ** i

        return np.sum(discounted_rewards)


    def get_value_map(self, *, num_rollouts=10000, max_length=None):
        """
        Performs many rollouts to compute an estimate of the value function
        """

        print(
            "Computing value function with {} rollouts, discount {} and max length {}".format(
                num_rollouts,
                self.discount_factor,
                max_length
            )
        )
        print("(this may take a while...)")

        self.value_map = {}
        for state in self.state_set:
            self.value_map[state] = self.get_value(
                state,
                num_rollouts=num_rollouts,
                max_length=max_length
            )

        return self.value_map


    def rollout(self, current_state, *, max_length=None):
        """
        Returns a single rollout of the process [(R, S), (R', S'), ..., (R_terminal, S_terminal)]
        """

        assert current_state in self.state_set, \
            "Given state ({}) is not in state set".format(current_state)

        curr = (None, current_state)

        history = np.array(
            [curr],
            dtype=[
                ('reward', np.array(self.reward_mapping.values()).dtype),
                ('state', np.array(self.state_set).dtype)
            ]
        )

        while curr[1] not in self.terminal_state_set:

            if max_length is not None:
                if len(history) >= max_length: break

            curr = self.transition(curr[1])
            history = np.append(
                history,
                np.array([curr], dtype=history.dtype)
            )

        return history


    def transition(self, current_state):
        """
        Returns the reward for being in the current state, and a subsequent state
        """

        assert current_state in self.state_set, \
            "Given state ({}) is not in state set".format(current_state)

        reward = self.get_expected_reward(current_state)
        new_state = super().transition(current_state)
        return (reward, new_state)


    def compute_stationary_distribution(self, *, num_rollouts=10000, max_length=None):
        """
        Estimates the stationary distribution of a process
        """

        print("Estimating the stationary distribution with {} rollouts".format(num_rollouts))
        print("(this may take a while)")
        
        state_counts = {}
        for state in self.state_set:
            state_counts[state] = 0

        total_visited_states = 0
        for n in range(num_rollouts):
            # Pick a starting state
            start_state = np.random.choice(self.state_set)

            # Do a full rollout
            rollout = self.rollout(start_state, max_length=max_length)
            total_visited_states += len(rollout)

            # Add up the states we visited
            for got_reward, visited_sate in rollout:
                state_counts[visited_sate] += 1

        # Convert to a probability
        stationary_distribution = []
        for state in state_counts:
            stationary_distribution.append(state_counts[state] / total_visited_states)

        return np.array(stationary_distribution)


    def decompose(self):
        """
        Decomposes this MRP to a Markov Process by discarding the reward terms
        """

        def mp_init(self, parent_mrp):
            """
            Decomposes a given MRP a simple MP
            """
            print("Initializing derived MP from MRP")

            # Set MDP parameters
            self.state_set = parent_mrp.state_set
            self.terminal_state_set = parent_mrp.terminal_state_set
            self.transition_matrix = parent_mrp.transition_matrix

        dynamic_class_type = type("DerivedMarkovProcess", (MarkovProcess, ), {'__init__': mp_init})
        return dynamic_class_type(self)
