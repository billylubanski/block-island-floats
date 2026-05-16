# Forecast Evaluation Summary

- Primary model: kernel_seasonal
- Gating reason: Kernel seasonal baseline remains primary because the richer scorer did not clear the top-3 and log-loss gate.

## Cluster Backtests

- global_topk: top-1 0.0726, top-3 0.2467, log loss 3.6945, calibration gap 0.039786
- month_frequency: top-1 0.0435, top-3 0.1393, log loss 3.992, calibration gap 0.052278
- kernel_seasonal: top-1 0.0566, top-3 0.1843, log loss 3.816, calibration gap 0.039161
- current_random_forest: top-1 0.0319, top-3 0.0842, log loss 4.0813, calibration gap 5e-05
- hybrid_zone: top-1 0.0552, top-3 0.1771, log loss 4.07, calibration gap 0.035802
