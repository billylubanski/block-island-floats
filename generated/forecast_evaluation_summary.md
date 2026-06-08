# Forecast Evaluation Summary

- Primary model: kernel_seasonal
- Gating reason: Kernel seasonal baseline remains primary because the richer scorer did not clear the top-3 and log-loss gate.

## Cluster Backtests

- global_topk: top-1 0.0719, top-3 0.2454, log loss 3.6889, calibration gap 0.035829
- month_frequency: top-1 0.0423, top-3 0.1312, log loss 3.951, calibration gap 0.052884
- kernel_seasonal: top-1 0.0592, top-3 0.1777, log loss 3.8035, calibration gap 0.035452
- current_random_forest: top-1 0.0296, top-3 0.0804, log loss 4.0842, calibration gap 0.002393
- hybrid_zone: top-1 0.0536, top-3 0.1777, log loss 4.0698, calibration gap 0.034247
