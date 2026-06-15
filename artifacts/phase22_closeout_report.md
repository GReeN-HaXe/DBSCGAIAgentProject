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

## Mixed-Source Batch Evaluation
- dataset_count: `5`
- overall_example_count: `649`
- overall_top1_accuracy: `1.000000`
- added_dataset: `C:\Users\PC\Desktop\dbsAIAgent\artifacts\phase22_benchmark_batch_v2\human_vs_ai.json`
- added_dataset_example_count: `13`
- report_path: `C:\Users\PC\Desktop\dbsAIAgent\artifacts\phase22_generalization_v2\phase22_batch_eval_with_human_report.md`
- comparison_artifact: `C:\Users\PC\Desktop\dbsAIAgent\artifacts\phase22_generalization_v2\phase22_mixed_source_comparison.json`
- comparison_result:
  - no regression versus the AI-vs-AI-only batch eval
  - the current human slice is still too small to pressure the model meaningfully

## Leave-One-Matchup-Out
- dataset_count: `4`
- overall_top1_accuracy_weighted: `1.000000`
- overall_top1_accuracy_macro: `1.000000`
- weakest_fold: `mechikabura_vs_krillin`
- weakest_fold_top1: `1.000000`

## Decision
- Freeze `artifacts/phase22_generalization_v2/production` as the canonical Phase 22 model for the current benchmark scope.
- Do not spend more time tuning Phase 22 on the current four AI-vs-AI matchup groups.
- The first mixed-source check with the current `human_vs_ai` slice also remains solved, so the next useful pressure comes from more human traces and broader matchup coverage rather than local retuning.

## Recommended Next Benchmarks
1. Grow the `human_vs_ai` benchmark slice with more traces and more consistent matchup batches.
2. Add more deck matchup families beyond the current four.
3. Compare AI-vs-AI-only and mixed-source behavior again after the human slice is materially larger.
4. Add identity-enriched gameplay decision datasets when available.
5. Only revisit richer state architectures after those harder benchmarks exist.
