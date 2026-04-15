# Forecast Evaluation Summary

- Primary model: kernel_seasonal
- Gating reason: Kernel seasonal baseline remains primary because the richer scorer did not clear the top-3 and log-loss gate.

## Cluster Backtests

- global_topk: top-1 0.0718, top-3 0.2478, log loss 3.7001, calibration gap 0.041365
- month_frequency: top-1 0.044, top-3 0.1408, log loss 3.9904, calibration gap 0.051631
- kernel_seasonal: top-1 0.0587, top-3 0.1862, log loss 3.8134, calibration gap 0.036846
- current_random_forest: top-1 0.0308, top-3 0.0924, log loss 4.08, calibration gap 0.001141
- hybrid_zone: top-1 0.0557, top-3 0.176, log loss 4.0699, calibration gap 0.036379
