# Forecast Evaluation Summary

- Primary model: kernel_seasonal
- Gating reason: Kernel seasonal baseline remains primary because the richer scorer did not clear the top-3 and log-loss gate.

## Cluster Backtests

- global_topk: top-1 0.0696, top-3 0.2133, log loss 3.633, calibration gap 0.045114
- month_frequency: top-1 0.0459, top-3 0.1274, log loss 3.948, calibration gap 0.052225
- kernel_seasonal: top-1 0.0578, top-3 0.1689, log loss 3.7482, calibration gap 0.039529
- current_random_forest: top-1 0.0296, top-3 0.0919, log loss 4.0482, calibration gap 0.003333
- hybrid_zone: top-1 0.0489, top-3 0.1689, log loss 4.0343, calibration gap 0.028828
