# Forecast Evaluation Summary

- Primary model: kernel_seasonal
- Gating reason: Kernel seasonal baseline remains primary because the richer scorer did not clear the top-3 and log-loss gate.

## Cluster Backtests

- global_topk: top-1 0.0767, top-3 0.2476, log loss 3.6723, calibration gap 0.038237
- month_frequency: top-1 0.0511, top-3 0.1575, log loss 3.908, calibration gap 0.044622
- kernel_seasonal: top-1 0.0794, top-3 0.1925, log loss 3.7669, calibration gap 0.021671
- current_random_forest: top-1 0.031, top-3 0.0915, log loss 4.0824, calibration gap 0.000816
- hybrid_zone: top-1 0.0592, top-3 0.1898, log loss 4.0664, calibration gap 0.039772
