# Phase 14 Embedding Sweep Report

## Summary
- Profile: `quick`
- Gallery split: `train`
- Query split: `validation`
- Config count: `2`
- Best config: `h128_e10_lr1e3`
- Best MRR: `0.9771918402777778`
- Best recall@1: `0.95703125`
- Best recall@5: `0.9990234375`
- Best recall@10: `1.0`

## Ranking
| Config | Hidden | Epochs | LR | MRR | R@1 | R@5 | R@10 | Duration(s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| h128_e10_lr1e3 | 128 | 10 | 0.001 | 0.977192 | 0.957031 | 0.999023 | 1.000000 | 8.81 |
| h64_e10_lr1e3 | 64 | 10 | 0.001 | 0.434405 | 0.314453 | 0.579102 | 0.676758 | 8.65 |
