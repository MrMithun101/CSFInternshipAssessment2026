"""Visualise ReID results: success and failure case grids.

Each row shows a query image followed by its top-k ranked gallery matches.
Green borders = correct identity, red = wrong.

Usage:
    python src/visualise.py \\
        --results   results/ranked_results.csv \\
        --labels    data/sample/labels.csv \\
        --reference data/sample/reference \\
        --query     data/sample/query \\
        --output-dir results \\
        --top-k 5 \\
        --n-cases 5
"""

import argparse
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))


def load_csv(path: Path) -> list[dict]:
    with open(path) as f:
        return list(csv.DictReader(f))


def label_map(path: Path) -> dict[str, str]:
    return {r["query_image"]: r["identity"] for r in load_csv(path)}


def first_ref_image(identity: str, ref_dir: Path) -> Image.Image | None:
    id_dir = ref_dir / identity
    if not id_dir.exists():
        return None
    for p in sorted(id_dir.iterdir()):
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            return Image.open(p).convert("RGB")
    return None


def plot_grid(cases: list[dict], ref_dir: Path, query_dir: Path,
              title: str, output_path: Path, top_k: int, n_cases: int):
    if not cases:
        print(f"No cases for '{title}' — skipping.")
        return

    cases = cases[:n_cases]
    n_cols = top_k + 1   # query column + top-k gallery columns
    fig, axes = plt.subplots(len(cases), n_cols,
                             figsize=(2.8 * n_cols, 2.8 * len(cases)))
    fig.suptitle(title, fontsize=13, fontweight="bold", y=1.01)

    if len(cases) == 1:
        axes = [axes]

    for row_i, case in enumerate(cases):
        query_path = query_dir / case["query"]
        q_img = Image.open(query_path).convert("RGB") if query_path.exists() else _placeholder()

        ax0 = axes[row_i][0]
        ax0.imshow(q_img)
        ax0.set_title(f"Query\ntrue: {case['true_id']}", fontsize=7)
        ax0.axis("off")
        _border(ax0, color="black", lw=2)

        for rank_i in range(top_k):
            ax = axes[row_i][rank_i + 1]
            pred_id, score = case["ranked"][rank_i]
            ref_img = first_ref_image(pred_id, ref_dir) or _placeholder()
            ax.imshow(ref_img)

            correct = pred_id == case["true_id"]
            color = "#2ca02c" if correct else "#d62728"
            ax.set_title(f"#{rank_i+1} {pred_id}\n{score:.3f}", fontsize=7, color=color)
            ax.axis("off")
            _border(ax, color=color, lw=3)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=100, bbox_inches="tight")
    plt.close()
    print(f"Saved {output_path}")


def _placeholder(size: int = 64) -> Image.Image:
    img = Image.new("RGB", (size, size), color=(200, 200, 200))
    return img


def _border(ax, color: str, lw: float):
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_edgecolor(color)
        spine.set_linewidth(lw)


def main():
    ap = argparse.ArgumentParser(description="Visualise ReID results")
    ap.add_argument("--results",    required=True, type=Path)
    ap.add_argument("--labels",     required=True, type=Path)
    ap.add_argument("--reference",  required=True, type=Path)
    ap.add_argument("--query",      required=True, type=Path)
    ap.add_argument("--output-dir", default="results", type=Path)
    ap.add_argument("--top-k",      default=5, type=int)
    ap.add_argument("--n-cases",    default=5, type=int,
                    help="Max rows to show per panel")
    args = ap.parse_args()

    results = load_csv(args.results)
    labels  = label_map(args.labels)

    n_ranks = sum(1 for k in results[0] if k.startswith("identity_"))
    top_k = min(args.top_k, n_ranks)

    successes, failures = [], []
    for row in results:
        q = row["query_image"]
        true_id = labels.get(q)
        if true_id is None or true_id == "unknown":
            continue
        ranked = [
            (row[f"identity_{k}"], float(row[f"score_{k}"]))
            for k in range(1, n_ranks + 1)
            if f"identity_{k}" in row
        ]
        case = {"query": q, "true_id": true_id, "ranked": ranked}
        (successes if ranked[0][0] == true_id else failures).append(case)

    print(f"Successes: {len(successes)}  |  Failures: {len(failures)}")

    plot_grid(successes, args.reference, args.query,
              "Success Cases (Rank-1 correct)",
              args.output_dir / "success_cases.png", top_k, args.n_cases)

    plot_grid(failures, args.reference, args.query,
              "Failure Cases (Rank-1 wrong)",
              args.output_dir / "failure_cases.png", top_k, args.n_cases)


if __name__ == "__main__":
    main()
