# Forecast Evaluation Summary

- Primary model: kernel_seasonal
- Gating reason: Kernel seasonal baseline remains primary because the richer scorer did not clear the top-3 and log-loss gate.

## Cluster Backtests

- global_topk: top-1 0.0731, top-3 0.245, log loss 3.6892, calibration gap 0.038134
- month_frequency: top-1 0.043, top-3 0.1361, log loss 3.9883, calibration gap 0.052143
- kernel_seasonal: top-1 0.0602, top-3 0.1805, log loss 3.8093, calibration gap 0.035506
- current_random_forest: top-1 0.0272, top-3 0.0845, log loss 4.0824, calibration gap 0.004753
- hybrid_zone: top-1 0.0501, top-3 0.1748, log loss 4.0702, calibration gap 0.030797
