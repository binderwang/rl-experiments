

import math
import numpy as np
from scipy.optimize import linprog


def lp_irl(S, A, T, gamma, pi, l1=10, Rmax=10):
    """
    Given a set of states S, A set of actions A, a transition matrix T, a
    discount factor gamma and a stationary, deterministic policy pi, finds a
    reward function R(S) for which the policy is optimal.

    \ref{Ng and Abbeel, 2000}
    The original paper: http://ai.stanford.edu/~ang/papers/icml00-irl.pdf
    A good reference: https://www.inf.ed.ac.uk/teaching/courses/rl/slides17/8_IRL.pdf
    A not as good reference: http://www.eecs.wsu.edu/~taylorm/14_580/yusen.pdf
    """

    # Measure size of state and action sets
    n = len(S)
    k = len(A)

    # Helper function to get index of state
    si = lambda s: S.tolist().index(s)

    # Helper function to get index of action
    ai = lambda a: A.tolist().index(a)

    # Helper function to get a transition probability
    trans = lambda s1, a, s2: T[si(s1) * k + ai(a), si(s2)]

    # Helper function to build a transition matrix, given a policy lambda
    def trans_mat(pi):
        T = np.zeros(shape=[n, n])
        for from_state in S:
            for to_state in S:
                t = trans(from_state, pi(from_state), to_state)
                T[si(from_state), si(to_state)] = t
        return T

    # Build Transition matrix under policy pi
    Tpi = trans_mat(lambda s: pi[s])

    # Construct transition matrices when we take the ith non-policy action at
    # each state
    Tnotpi = {}
    for i in range(k - 1):
        Tnotpi[i] = np.zeros(shape=[n, n])

        for from_state in S:
            Atmp = A.tolist()
            Atmp.remove(pi[from_state])
            non_policy_action = Atmp[i]

            for to_state in S:
                t = trans(from_state, non_policy_action, to_state)
                Tnotpi[i][si(from_state), si(to_state)] = t

    # Find the stationary distribution under the policy pi
    #Tpi_stat = np.linalg.matrix_power(Tpi, 1000)[0, :]

    # Compute the discounted transition matrix term
    T_disc_inv = np.linalg.inv(np.identity(n) - gamma * Tpi)

    # Formulate the linear programming problem constraints
    # NB: The general form for adding a constraint looks like this
    # c, A_ub, b_ub = f(c, A_ub, b_ub)

    # Prepare LP constraint matrices
    c = np.empty(shape=[1, n], dtype=float)
    A_ub = np.empty(shape=[0, n], dtype=float)
    b_ub = np.empty(shape=[0, 1])


    def add_optimal_policy_constraints(c, A_ub, b_ub):
        """
        Add constraints to ensure the expert policy is optimal
        This will add (k-1) * n extra constraints
        """
        for i in range(k - 1):
            constraint_rows = -1 * (Tpi - Tnotpi[i]) @ T_disc_inv
            A_ub = np.vstack((A_ub, constraint_rows))
            b_ub = np.vstack((b_ub, np.zeros(shape=[constraint_rows.shape[0], 1])))
        return c, A_ub, b_ub


    def add_costly_single_step_constraints(c, A_ub, b_ub):
        """
        Augment the optimisation objective to add the costly-single-step
        degeneracy heuristic
        This will add n extra optimisation variables and (k-1) * n extra
        constraints
        NB: Assumes the true optimisation variables are first in the objective
        function
        """

        # Expand the c vector add new terms for the min{} operator
        c = np.hstack((c, -1 * np.ones(shape=[1, n])))
        css_offset = c.shape[1] - n

        # Don't forget to resize the A_ub matrix to match
        A_ub = np.hstack((A_ub, np.zeros(shape=[A_ub.shape[0], n])))

        # Add min{} operator constrints
        for i in range(k - 1):
            # Generate the costly single step constraint terms
            constraint_rows = -1 * (Tpi - Tnotpi[i]) @ T_disc_inv

            # constraint_rows is nxn - we need to add the min{} terms though
            min_operator_entries = np.identity(n)
            
            # And we have to make sure we put the min{} operator entries in
            # the correct place in the A_ub matrix
            num_padding_cols = css_offset - n
            padding_entries = np.zeros(shape=[constraint_rows.shape[0], num_padding_cols])
            constraint_rows = np.hstack((constraint_rows, padding_entries, min_operator_entries))

            # Finally, add the new constraints
            A_ub = np.vstack((A_ub, constraint_rows))
            b_ub = np.vstack((b_ub, np.zeros(shape=[constraint_rows.shape[0], 1])))
        
        return c, A_ub, b_ub


    def add_l1norm_constraints(c, A_ub, b_ub, l1):
        """
        Augment the optimisation objective to add an l1 norm regularisation
        term z += l1 * ||R||_1
        This will add n extra optimisation variables and 2n extra constraints
        NB: Assumes the true optimisation variables are first in the objective
        function
        """

        # We add an extra variable for each each true optimisation variable
        c = np.hstack((c, l1 * np.ones(shape=[1, n])))
        l1_offset = c.shape[1] - n

        # Don't forget to resize the A_ub matrix to match
        A_ub = np.hstack((A_ub, np.zeros(shape=[A_ub.shape[0], n])))

        # Now we add 2 new constraints for each true optimisation variable to
        # enforce the absolute value terms in the l1 norm
        for i in range(n):

            # An absolute value |x1| can be enforced via constraints
            # -x1 <= 0             (i.e., x1 must be positive or 0)
            #  x1 + -xe1 <= 0
            # Where xe1 is the replacement for |x1| in the objective
            #
            # TODO ajs 04/Apr/2018 This enforces that R must be positive or 0,
            # but I was under the impression that it was also possible to
            # enforce an abs operator without this requirement - e.g. see
            # http://lpsolve.sourceforge.net/5.1/absolute.htm
            constraint_row_1 = [0] * A_ub.shape[1]
            constraint_row_1[i] = -1
            A_ub = np.vstack((A_ub, constraint_row_1))
            b_ub = np.vstack((b_ub, [[0]]))

            constraint_row_2 = [0] * A_ub.shape[1]
            constraint_row_2[i] = 1
            constraint_row_2[l1_offset + i] = -1
            A_ub = np.vstack((A_ub, constraint_row_2))
            b_ub = np.vstack((b_ub, [[0]]))

        return c, A_ub, b_ub


    def add_rmax_constraints(c, A_ub, b_ub, Rmax):
        """
        Add constraints for a maximum R value Rmax
        This will add n extra constraints
        """
        for i in range(n):
            constraint_row = [0] * A_ub.shape[1]
            constraint_row[i] = 1
            A_ub = np.vstack((A_ub, constraint_row))
            b_ub = np.vstack((b_ub, Rmax))
        return c, A_ub, b_ub

    
    # Compose LP optimisation problem
    c, A_ub, b_ub = add_optimal_policy_constraints(c, A_ub, b_ub)
    c, A_ub, b_ub = add_costly_single_step_constraints(c, A_ub, b_ub)
    c, A_ub, b_ub = add_rmax_constraints(c, A_ub, b_ub, Rmax)
    c, A_ub, b_ub = add_l1norm_constraints(c, A_ub, b_ub, l1)

    # Show the LP system prior to solving
    #print(c[0, :])
    #print(A_ub)
    #print(b_ub[:, 0])

    # Solve for a solution
    # NB: scipy.optimize.linprog expects a 1d c vector

    # NB: for my test problems, the simplex method return nan for the true
    # optimisation variables!
    #res = linprog(c[0, :], A_ub=A_ub, b_ub=b_ub[:, 0], method="simplex")
    # The interior point method seems to work though
    res = linprog(c[0, :], A_ub=A_ub, b_ub=b_ub[:, 0],  method="interior-point")

    # cvxopt also works (python 3.5 only)
    #from cvxopt import matrix, solvers
    #res = solvers.lp(matrix(c[0, :]), matrix(A_ub), matrix(b_ub))


    def normalize(vals):
        """
        normalize to (0, max_val)
        input:
        vals: 1d array
        """
        min_val = np.min(vals)
        max_val = np.max(vals)
        return (vals - min_val) / (max_val - min_val)

    
    # Extract the true optimisation variables and re-scale
    rewards = Rmax * normalize(res['x'][0:n])

    return rewards, res




if __name__ == "__main__":

    S = np.array(["s0", "s1", "s2"])
    A = np.array(["b", "o"])
    T = np.array([[0,    0.4, 0.6 ],
                  [0,    0,   1   ],
                  [0,    0,   1   ],
                  [0,    0,   1   ],
                  [1,    0,   0   ],
                  [1,    0,   0   ]])
    gamma = 0.9
    pi = {
        "s0": "b",
        "s1": "o",
        "s2": "o"
    }

    ## Try a smaller (n=2) problem
    S = np.array(["s0", "s1"])
    T = np.array([[0.4, 0.6],
                [0.9, 0.1],
                [1,   0],
                [1,   0]])
    pi = {
      "s0": "b",
      "s1": "o"
    }

    # L1 norm weight
    l1=10

    # Maximum reward
    Rmax=2

    print(S)
    print(T)
    print(pi)
    rewards, _ = lp_irl(S, A, T, gamma, pi, l1, Rmax)
    print(rewards)
