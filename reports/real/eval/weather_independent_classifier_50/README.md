# Preserved 50-feature comparisons before classifier-chain integration

These reports use the independent-label classifier before upstream commit 083c9d0.
Both controls have 50 features and valid input hashes, but cheap probabilities and
calibration were fitted independently and could violate p_cheap <= p_near_zero.

The parent directory now contains reruns with the nested two-step classifier.
Price model inputs remain unchanged. Preserve these reports as development history,
not as current nested-classifier or chronological-validation scores.