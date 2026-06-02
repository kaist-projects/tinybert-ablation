"""One-time report: how student metrics moved from weightless to weighted KD.

Reads the two metadata trees under ``comparison/`` (all loss weights at 1.0 vs.
the tuned config weights), diffs a curated metric set per (dataset, condition),
and writes ``comparison/COMPARISON.md``.
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.analysis.cross_dataset import CONDITION_ORDER, DATASET_ORDER  # noqa: E402
from src.analysis.loaders import load_all_runs  # noqa: E402

COMPARISON_ROOT = pathlib.Path("comparison")
WEIGHTLESS_ROOT = COMPARISON_ROOT / "weightless" / "metadata"
WEIGHTED_ROOT = COMPARISON_ROOT / "weighted" / "metadata"
REPORT_PATH = COMPARISON_ROOT / "COMPARISON.md"

#: (column, label, lower_is_better) for the curated metric set.
METRICS = [
    ("test_macro_f1", "F1", False),
    ("test_accuracy", "Acc", False),
    ("test_ece", "ECE", True),
]
WEIGHT_TERMS = [
    ("ce", "weight_ce"),
    ("logit", "weight_logit"),
    ("hidden", "weight_hidden"),
    ("attn", "weight_attn"),
]


def main() -> None:
    comparison = build_comparison_frame(WEIGHTLESS_ROOT, WEIGHTED_ROOT)
    weights = applied_weights(WEIGHTED_ROOT)
    REPORT_PATH.write_text(render_comparison(comparison, weights))
    print(f"Wrote {REPORT_PATH} ({len(comparison)} rows).")


def build_comparison_frame(weightless_root: pathlib.Path, weighted_root: pathlib.Path) -> pd.DataFrame:
    """Merge both sweeps into one row per (dataset, condition) with per-metric deltas."""
    weightless = _side_frame(weightless_root, "wl")
    weighted = _side_frame(weighted_root, "w")
    merged = weightless.merge(weighted, on=["dataset", "condition"], how="outer")
    for column, _, _ in METRICS:
        merged[f"delta_{column}"] = merged[f"{column}_w"] - merged[f"{column}_wl"]
    return merged


def _side_frame(metadata_root: pathlib.Path, suffix: str) -> pd.DataFrame:
    """Tidy frame for one sweep, with metric columns suffixed and invalid rows nulled."""
    runs = load_all_runs(metadata_root)
    keep = ["dataset", "condition"] + [column for column, _, _ in METRICS]
    frame = runs.loc[:, keep].copy()
    invalid = ~runs["valid"]
    for column, _, _ in METRICS:
        frame.loc[invalid.values, column] = pd.NA
    rename = {column: f"{column}_{suffix}" for column, _, _ in METRICS}
    return frame.rename(columns=rename)


def applied_weights(weighted_root: pathlib.Path) -> dict:
    """Pull the loss weights actually used by the weighted sweep from any valid run."""
    frame = load_all_runs(weighted_root)
    valid = frame.loc[frame["valid"]]
    if valid.empty:
        return {}
    row = valid.iloc[0]
    weights = {key: row[column] for key, column in WEIGHT_TERMS}
    weights["temperature"] = row["logit_temperature"]
    return weights


def render_comparison(comparison: pd.DataFrame, weights: dict) -> str:
    """Render the full weighted-vs-weightless markdown report."""
    lines = _header(weights)
    lines += _summary_table(comparison)
    for dataset in _ordered(comparison["dataset"].unique(), DATASET_ORDER):
        lines += _dataset_section(dataset, comparison.loc[comparison["dataset"] == dataset])
    return "\n".join(lines)


def _header(weights: dict) -> list[str]:
    weight_text = ", ".join(f"{key}=`{_weight(weights.get(key))}`" for key, _ in WEIGHT_TERMS)
    temperature = _weight(weights.get("temperature"))
    return [
        "# Loss-Weighting Comparison",
        "",
        "Student metrics before and after applying tuned KD loss weights. The",
        "**weightless** sweep ran every loss term at weight 1.0; the **weighted** sweep",
        f"applied {weight_text}, logit KD temperature `T`=`{temperature}`.",
        "Deltas are `weighted - weightless`. Higher is better for F1 and accuracy;",
        "**lower** is better for ECE. Single seed (42): read deltas as descriptive, not",
        "causal.",
        "",
    ]


def _summary_table(comparison: pd.DataFrame) -> list[str]:
    lines = [
        "## Best-Student Macro-F1 by Dataset",
        "",
        "Best test macro-F1 over the 8 conditions on each side (each side's own argmax).",
        "",
        "| Dataset | Weightless | Weighted | Delta |",
        "|---|---:|---:|---:|",
    ]
    for dataset in _ordered(comparison["dataset"].unique(), DATASET_ORDER):
        rows = comparison.loc[comparison["dataset"] == dataset]
        wl = rows["test_macro_f1_wl"].max(skipna=True)
        w = rows["test_macro_f1_w"].max(skipna=True)
        delta = w - wl if pd.notna(wl) and pd.notna(w) else pd.NA
        lines.append(f"| `{dataset}` | {_num(wl)} | {_num(w)} | {_num(delta, signed=True)} |")
    lines.append("")
    return lines


def _dataset_section(dataset: str, rows: pd.DataFrame) -> list[str]:
    indexed = rows.set_index("condition")
    headers = " | ".join(f"{label} wl | {label} w | Δ{label}" for _, label, _ in METRICS)
    aligns = " | ".join(["---:"] * (len(METRICS) * 3))
    lines = [
        f"## `{dataset}`",
        "",
        f"| Condition | {headers} |",
        f"|---|{aligns}|",
    ]
    for condition in _ordered(rows["condition"].unique(), CONDITION_ORDER):
        lines.append(_dataset_row(condition, indexed.loc[condition]))
    lines.append("")
    return lines


def _dataset_row(condition: str, row: pd.Series) -> str:
    cells = []
    for column, _, _ in METRICS:
        cells.append(_num(row[f"{column}_wl"]))
        cells.append(_num(row[f"{column}_w"]))
        cells.append(_num(row[f"delta_{column}"], signed=True))
    return f"| `{condition}` | " + " | ".join(cells) + " |"


def _ordered(values, order: list[str]) -> list[str]:
    present = set(values)
    ranked = [name for name in order if name in present]
    extra = sorted(name for name in present if name not in order)
    return ranked + extra


def _num(value: object, *, signed: bool = False) -> str:
    if pd.isna(value):
        return "N/A"
    number = float(value)
    return f"{number:+.4f}" if signed else f"{number:.4f}"


def _weight(value: object) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{float(value):g}"


if __name__ == "__main__":
    main()
