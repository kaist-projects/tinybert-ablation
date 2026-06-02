# Factorial Analysis Report

Dataset: `imdb`

## Artifact Summary

- Teacher metadata: `results/metadata/imdb/teacher/run_metadata.json`
- Student metadata: `results/metadata/imdb/student/*/run_metadata.json`
- Report: `results/analysis/imdb/REPORT.md`
- Figures: `figures/`

## Validity Checklist

| Check | Status | Detail |
|---|:---:|---|
| all 8 conditions present and valid | PASS | all 8 condition metadata files are present and valid |
| epochs completed | PASS | all runs completed configured epochs or documented early-stop |
| finite metrics/losses | PASS | all required metrics and active losses are finite |
| teacher forward sane | PASS | top1_agreement is present and above random for every KD condition |
| metric ranges | PASS | F1/accuracy/agreement/ECE values are within [0, 1] |
| artifacts written | PASS | 4 PNG figures and 1 markdown report written |

## Key Results

- Teacher test macro-F1: `0.8885`.
- Best student: `kd_attn` with test macro-F1 `0.8598`.
- CE-only student test macro-F1: `0.8502`.
- Student macro-F1 spread across conditions: `0.0195`.
- Mean final attention-loss magnitude: `0.17099`.

The best student is `kd_attn` (test macro-F1 `0.8598`), but with a single seed the factorial effects
below should be read as pipeline diagnostics and descriptive statistics, not
resolved causal estimates.

## Loss Weights

Global weights multiplying each active loss term:
`L_total = w_ce*L_CE + I_logit*w_logit*L_logit + I_hidden*w_hidden*L_hidden
+ I_attn*w_attn*L_attn`. Per-condition indicators `I` toggle terms on or off;
the weights themselves are identical across all conditions and datasets.

| Term | Weight |
|---|---:|
| CE | `1` |
| Logit | `1.8` |
| Hidden | `0.9` |
| Attention | `240` |

Logit KD temperature `T`: `1`.

## Student Ablation Table

Dataset: `imdb`

Source files:
`results/metadata/imdb/teacher/run_metadata.json` and
`results/metadata/imdb/student/*/run_metadata.json`

Primary metric: test macro-F1. `Delta` is test macro-F1 relative to `ce_only`.
Rows are ordered by test macro-F1 descending.
Bold marks the best value in each metric column: higher is better for F1,
accuracy, and agreement; lower is better for ECE.

| Condition | Logit | Hidden | Attention | Test Macro-F1 | Delta | Test Acc. | Test ECE | Top-1 Agree |
|---|:---:|:---:|:---:|---:|---:|---:|---:|---:|
| `teacher` | N/A | N/A | N/A | **0.8885** | **+0.0383** | **0.8885** | 0.0433 | N/A |
| `kd_attn` |  |  | Y | 0.8598 | +0.0096 | 0.8599 | 0.0426 | 0.9027 |
| `kd_logit_attn` | Y |  | Y | 0.8565 | +0.0063 | 0.8566 | 0.0408 | **0.9030** |
| `kd_full` | Y | Y | Y | 0.8561 | +0.0060 | 0.8562 | 0.0388 | 0.9027 |
| `kd_hidden_attn` |  | Y | Y | 0.8539 | +0.0038 | 0.8540 | 0.0353 | 0.9009 |
| `kd_logit` | Y |  |  | 0.8529 | +0.0027 | 0.8531 | 0.0390 | 0.8996 |
| `kd_logit_hidden` | Y | Y |  | 0.8518 | +0.0016 | 0.8519 | 0.0375 | 0.8978 |
| `ce_only` |  |  |  | 0.8502 | +0.0000 | 0.8505 | 0.0397 | 0.8931 |
| `kd_hidden` |  | Y |  | 0.8403 | -0.0099 | 0.8408 | **0.0299** | 0.8832 |

Best student test macro-F1 is `kd_attn` at 0.8598, +0.0096 over `ce_only`.
The teacher reference is higher at 0.8885.

## Factorial Effects

Metric: `test_macro_f1`

Positive estimates mean the factor or interaction increases the metric under
standard +/-1 factorial coding. Magnitudes are informational for this
single-seed run.

| Effect | Kind | Estimate | Absolute |
|---|---:|---:|---:|
| `logit` | main | +0.00330 | 0.00330 |
| `hidden` | main | -0.00432 | 0.00432 |
| `attention` | main | +0.00782 | 0.00782 |
| `logit x hidden` | 2-way | +0.00358 | 0.00358 |
| `logit x attention` | 2-way | -0.00383 | 0.00383 |
| `hidden x attention` | 2-way | +0.00120 | 0.00120 |
| `logit x hidden x attention` | 3-way | -0.00081 | 0.00081 |

## Attention-Loss Caveat

Attention KD used post-softmax attention probabilities in this run. Its
final loss magnitude is near-inert compared with CE, logit, and hidden
losses, so the attention factor was only weakly applied. Fix this signal or
explicitly document the caveat before scaling the experiment.

## Figures

### Condition Bars

![Condition Bars](figures/condition_bars.png)

### Main Effects

![Main Effects](figures/main_effects.png)

### Loss Magnitudes

![Loss Magnitudes](figures/loss_magnitudes.png)

### Calibration

![Calibration](figures/calibration.png)
