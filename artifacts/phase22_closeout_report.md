# Phase 22 Closeout

## Best Config
- target_field: `decision_class`
- config_name: `h128_e20_lr0001`
- hidden_dim: `128`
- epochs: `20`
- learning_rate: `0.001`
- manifest_path: `C:\Users\PC\Desktop\dbsAIAgent\artifacts\phase22_generalization_v2\pipeline\phase22_manifest.json`

## Generalized Batch Evaluation
- dataset_count: `4`
- overall_example_count: `636`
- overall_top1_accuracy: `1.000000`
- weakest_dataset: `C:\Users\PC\Desktop\dbsAIAgent\artifacts\phase22_benchmark_batch_v2\mechikabura_vs_krillin.json`
- weakest_dataset_top1: `1.000000`

## Leave-One-Matchup-Out
- dataset_count: `4`
- overall_top1_accuracy_weighted: `1.000000`
- overall_top1_accuracy_macro: `1.000000`
- weakest_fold: `mechikabura_vs_krillin`
- weakest_fold_top1: `1.000000`

## Decision
- Freeze `artifacts/phase22_generalization_v2/production` as the canonical Phase 22 model for the current benchmark scope.
- Do not spend more time tuning Phase 22 on the current four AI-vs-AI matchup groups.

## Recommended Next Benchmarks
1. Add normalized human-vs-AI traces into the benchmark family.
2. Add more deck matchup families beyond the current four.
3. Add identity-enriched gameplay decision datasets when available.
4. Only revisit richer state architectures after those harder benchmarks exist.
