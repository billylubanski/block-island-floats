# Forecast Evaluation Summary

- Primary model: kernel_seasonal
- Gating reason: Kernel seasonal baseline remains primary because the richer scorer did not clear the top-3 and log-loss gate.

## Cluster Backtests

- global_topk: top-1 0.0734, top-3 0.2438, log loss 3.6871, calibration gap 0.033341
- month_frequency: top-1 0.0443, top-3 0.1302, log loss 3.9388, calibration gap 0.050425
- kernel_seasonal: top-1 0.0651, top-3 0.1773, log loss 3.7939, calibration gap 0.029986
- current_random_forest: top-1 0.0332, top-3 0.0914, log loss 4.081, calibration gap 0.001344
- hybrid_zone: top-1 0.0554, top-3 0.1676, log loss 4.0698, calibration gap 0.03606
