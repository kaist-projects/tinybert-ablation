"""One-time report: how student metrics moved from weightless to weighted KD.

Reads the two metadata trees under ``comparison/`` (all loss weights at 1.0 vs.
the tuned config weights), diffs a curated metric set per (dataset, condition),
and writes ``comparison/COMPARISON.md``.
"""

from __future__ import annotations

import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.analysis.cross_dataset import CONDITION_ORDER, DATASET_ORDER  # noqa: E402
from src.analysis.factorial import effects_table  # noqa: E402
from src.analysis.loaders import load_all_runs  # noqa: E402
from src.analysis.plots import FIGURE_DPI, plot_cross_task_heatmap  # noqa: E402

COMPARISON_ROOT = pathlib.Path("comparison")
WEIGHTLESS_ROOT = COMPARISON_ROOT / "weightless" / "metadata"
WEIGHTED_ROOT = COMPARISON_ROOT / "weighted" / "metadata"
REPORT_PATH = COMPARISON_ROOT / "COMPARISON.md"
FIGURES_DIR = COMPARISON_ROOT / "figures"

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
    weightless_full = load_all_runs(WEIGHTLESS_ROOT)
    weighted_full = load_all_runs(WEIGHTED_ROOT)
    comparison = build_comparison_frame(weightless_full, weighted_full)
    weights = applied_weights(weighted_full)

    best_f1 = write_best_f1_figure(comparison, FIGURES_DIR)
    heatmaps = write_delta_figures(comparison, FIGURES_DIR)
    f1_bars = write_f1_condition_bars(comparison, FIGURES_DIR)
    effect_bars = write_main_effect_change_bars(weightless_full, weighted_full, FIGURES_DIR)

    report = render_comparison(comparison, weights, best_f1, heatmaps, f1_bars, effect_bars)
    REPORT_PATH.write_text(report)
    total = 1 + len(heatmaps) + len(f1_bars) + len(effect_bars)
    print(f"Wrote {REPORT_PATH} ({len(comparison)} rows, {total} figures).")


def build_comparison_frame(weightless_full: pd.DataFrame, weighted_full: pd.DataFrame) -> pd.DataFrame:
    """Merge both sweeps into one row per (dataset, condition) with per-metric deltas."""
    weightless = _trim_side(weightless_full, "wl")
    weighted = _trim_side(weighted_full, "w")
    merged = weightless.merge(weighted, on=["dataset", "condition"], how="outer")
    for column, _, _ in METRICS:
        merged[f"delta_{column}"] = merged[f"{column}_w"] - merged[f"{column}_wl"]
    return merged


def _trim_side(runs: pd.DataFrame, suffix: str) -> pd.DataFrame:
    """Curated metric columns for one sweep, suffixed, with invalid rows nulled."""
    keep = ["dataset", "condition"] + [column for column, _, _ in METRICS]
    frame = runs.loc[:, keep].copy()
    invalid = ~runs["valid"]
    for column, _, _ in METRICS:
        frame.loc[invalid.values, column] = pd.NA
    rename = {column: f"{column}_{suffix}" for column, _, _ in METRICS}
    return frame.rename(columns=rename)


def write_best_f1_figure(comparison: pd.DataFrame, out_dir: pathlib.Path) -> pathlib.Path:
    """Grouped bars of best-student test macro-F1, weightless vs weighted, per dataset."""
    out_dir.mkdir(parents=True, exist_ok=True)
    datasets = [name for name in DATASET_ORDER if name in set(comparison["dataset"])]
    weightless = [_best_student_f1(comparison, name, "test_macro_f1_wl") for name in datasets]
    weighted = [_best_student_f1(comparison, name, "test_macro_f1_w") for name in datasets]

    positions = range(len(datasets))
    width = 0.4
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar([p - width / 2 for p in positions], weightless, width, label="weightless", color="#9aa7b5")
    ax.bar([p + width / 2 for p in positions], weighted, width, label="weighted", color="#3274a1")
    ax.set_title("Best-student test macro-F1: weightless vs weighted")
    ax.set_ylabel("Test macro-F1")
    ax.set_ylim(0.0, 1.0)
    ax.set_xticks(list(positions))
    ax.set_xticklabels(datasets, rotation=35, ha="right")
    ax.legend()
    fig.tight_layout()

    path = out_dir / "best_student_f1.png"
    fig.savefig(path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    return path


def _best_student_f1(comparison: pd.DataFrame, dataset: str, column: str) -> float:
    rows = comparison.loc[comparison["dataset"] == dataset, column]
    return float(rows.max(skipna=True))


def write_delta_figures(comparison: pd.DataFrame, out_dir: pathlib.Path) -> list[pathlib.Path]:
    """Write one datasets x conditions delta heatmap per curated metric."""
    written = []
    for column, label, _ in METRICS:
        matrix = _delta_matrix(comparison, f"delta_{column}")
        title = f"Weighted - weightless {label} (datasets x conditions)"
        written.extend(
            plot_cross_task_heatmap(matrix, out_dir, f"delta_{column}", title, fmt=".3f", center=0.0, cmap="coolwarm")
        )
    return written


def _delta_matrix(comparison: pd.DataFrame, value_column: str) -> pd.DataFrame:
    """Pivot a delta column into a dataset-row / condition-column matrix in canonical order."""
    matrix = comparison.pivot(index="dataset", columns="condition", values=value_column)
    rows = [name for name in DATASET_ORDER if name in matrix.index]
    cols = [name for name in CONDITION_ORDER if name in matrix.columns]
    return matrix.reindex(index=rows, columns=cols)


def write_f1_condition_bars(comparison: pd.DataFrame, out_dir: pathlib.Path) -> dict[str, pathlib.Path]:
    """Per dataset, signed bars of ΔF1 (weighted - weightless) across the 8 conditions."""
    figures = {}
    for dataset in _ordered(comparison["dataset"].unique(), DATASET_ORDER):
        rows = comparison.loc[comparison["dataset"] == dataset].set_index("condition")
        conditions = _ordered(rows.index, CONDITION_ORDER)
        values = [_float(rows.loc[condition, "delta_test_macro_f1"]) for condition in conditions]
        path = out_dir / f"delta_f1_conditions_{dataset}.png"
        _save_signed_bars(conditions, values, f"{dataset}: ΔF1 by condition", "Δ test macro-F1", path)
        figures[dataset] = path
    return figures


def write_main_effect_change_bars(
    weightless_full: pd.DataFrame, weighted_full: pd.DataFrame, out_dir: pathlib.Path
) -> dict[str, pathlib.Path]:
    """Per dataset, signed bars of the change in each factorial effect (weighted - weightless)."""
    figures = {}
    datasets = _ordered(weighted_full["dataset"].unique(), DATASET_ORDER)
    for dataset in datasets:
        delta = _effect_change(weightless_full, weighted_full, dataset)
        if delta is None:
            continue
        path = out_dir / f"delta_effects_{dataset}.png"
        _save_signed_bars(
            list(delta["effect"]), list(delta["estimate"]), f"{dataset}: Δ main effects", "Δ effect on F1", path
        )
        figures[dataset] = path
    return figures


def _effect_change(weightless_full: pd.DataFrame, weighted_full: pd.DataFrame, dataset: str) -> pd.DataFrame | None:
    """Weighted-minus-weightless factorial effect estimates for one dataset, or None if incomplete."""
    weightless = _valid_dataset_runs(weightless_full, dataset)
    weighted = _valid_dataset_runs(weighted_full, dataset)
    if weightless is None or weighted is None:
        return None
    wl_effects = effects_table(weightless, "test_macro_f1")
    w_effects = effects_table(weighted, "test_macro_f1")
    merged = wl_effects.merge(w_effects, on=["effect", "kind"], suffixes=("_wl", "_w"))
    merged["estimate"] = merged["estimate_w"] - merged["estimate_wl"]
    return merged[["effect", "estimate"]]


def _valid_dataset_runs(full: pd.DataFrame, dataset: str) -> pd.DataFrame | None:
    """All-8 valid condition rows for a dataset, or None if any condition is missing/invalid."""
    rows = full.loc[(full["dataset"] == dataset) & full["valid"]]
    if len(rows) < len(CONDITION_ORDER):
        return None
    return rows


def applied_weights(weighted_full: pd.DataFrame) -> dict:
    """Pull the loss weights actually used by the weighted sweep from any valid run."""
    valid = weighted_full.loc[weighted_full["valid"]]
    if valid.empty:
        return {}
    row = valid.iloc[0]
    weights = {key: row[column] for key, column in WEIGHT_TERMS}
    weights["temperature"] = row["logit_temperature"]
    return weights


def _save_signed_bars(
    labels: list[str], values: list[float], title: str, ylabel: str, path: pathlib.Path
) -> pathlib.Path:
    """Save a signed bar chart centered at zero: positive teal, negative red."""
    path.parent.mkdir(parents=True, exist_ok=True)
    colors = ["#3274a1" if value >= 0 else "#c0504d" for value in values]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar(range(len(labels)), values, color=colors, width=0.8)
    ax.axhline(0.0, color="#4c566a", linewidth=1.0)
    span = max((abs(value) for value in values), default=0.0)
    offset = max(span * 0.04, 1e-4)
    for index, value in enumerate(values):
        ax.text(index, value + (offset if value >= 0 else -offset), f"{value:+.3f}",
                ha="center", va="bottom" if value >= 0 else "top", fontsize=8)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=35, ha="right")
    fig.tight_layout()
    fig.savefig(path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    return path


def _float(value: object) -> float:
    return 0.0 if pd.isna(value) else float(value)


def render_comparison(
    comparison: pd.DataFrame,
    weights: dict,
    best_f1: pathlib.Path,
    heatmaps: list[pathlib.Path],
    f1_bars: dict[str, pathlib.Path],
    effect_bars: dict[str, pathlib.Path],
) -> str:
    """Render the full weighted-vs-weightless markdown report."""
    lines = _header(weights)
    lines += _summary_table(comparison)
    lines += _best_f1_section(best_f1)
    lines += _figures_section(heatmaps)
    for dataset in _ordered(comparison["dataset"].unique(), DATASET_ORDER):
        rows = comparison.loc[comparison["dataset"] == dataset]
        lines += _dataset_section(dataset, rows, f1_bars.get(dataset), effect_bars.get(dataset))
    return "\n".join(lines)


def _best_f1_section(figure: pathlib.Path) -> list[str]:
    relative = figure.relative_to(COMPARISON_ROOT).as_posix()
    return [
        "## Best-Student F1 Chart",
        "",
        "Best test macro-F1 over the 8 conditions per dataset, weightless vs weighted.",
        "",
        f"![Best-student F1: weightless vs weighted]({relative})",
        "",
    ]


def _figures_section(figures: list[pathlib.Path]) -> list[str]:
    if not figures:
        return []
    lines = [
        "## Delta Heatmaps",
        "",
        "Per metric, weighted minus weightless across datasets (rows) and conditions",
        "(columns). Warm = weighted is higher. For F1 and accuracy warm is better; for",
        "ECE warm is **worse** (more miscalibrated).",
        "",
    ]
    for figure in figures:
        title = figure.stem.replace("delta_", "Δ ").replace("test_", "").replace("_", " ")
        relative = figure.relative_to(COMPARISON_ROOT).as_posix()
        lines.extend([f"### {title}", "", f"![{title}]({relative})", ""])
    return lines


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


def _dataset_section(
    dataset: str, rows: pd.DataFrame, f1_bar: pathlib.Path | None, effect_bar: pathlib.Path | None
) -> list[str]:
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
    lines += _dataset_figure(f1_bar, "ΔF1 by condition")
    lines += _dataset_figure(effect_bar, "Δ main effects")
    return lines


def _dataset_figure(figure: pathlib.Path | None, alt: str) -> list[str]:
    if figure is None:
        return []
    relative = figure.relative_to(COMPARISON_ROOT).as_posix()
    return [f"![{alt}]({relative})", ""]


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
