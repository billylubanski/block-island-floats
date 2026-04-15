# Forecast Evaluation Summary

- Primary model: kernel_seasonal
- Gating reason: Kernel seasonal baseline remains primary because the richer scorer did not clear the top-3 and log-loss gate.

## Cluster Backtests

- global_topk: top-1 0.0717, top-3 0.2474, log loss 3.6988, calibration gap 0.041144
- month_frequency: top-1 0.0439, top-3 0.1406, log loss 3.9916, calibration gap 0.051668
- kernel_seasonal: top-1 0.0586, top-3 0.1859, log loss 3.8153, calibration gap 0.036868
- current_random_forest: top-1 0.0293, top-3 0.0864, log loss 4.0806, calibration gap 0.002672
- hybrid_zone: top-1 0.0556, top-3 0.1757, log loss 4.07, calibration gap 0.0363
