# Phase 14 Embedding Sweep Report

## Summary
- Profile: `standard`
- Gallery split: `train`
- Query split: `validation`
- Config count: `3`
- Best config: `h256_e20_lr5e4`
- Best MRR: `0.996337890625`
- Best recall@1: `0.9931640625`
- Best recall@5: `1.0`
- Best recall@10: `1.0`

## Ranking
| Config | Hidden | Epochs | LR | MRR | R@1 | R@5 | R@10 | Duration(s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| h256_e20_lr5e4 | 256 | 20 | 0.0005 | 0.996338 | 0.993164 | 1.000000 | 1.000000 | 10.52 |
| h128_e20_lr1e3 | 128 | 20 | 0.001 | 0.988421 | 0.978516 | 0.999023 | 1.000000 | 10.00 |
| h64_e20_lr1e3 | 64 | 20 | 0.001 | 0.868852 | 0.783203 | 0.979492 | 0.998047 | 9.87 |
