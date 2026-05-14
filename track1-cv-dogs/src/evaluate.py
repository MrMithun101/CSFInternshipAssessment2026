"""Evaluation metrics for the dog ReID pipeline.

Computes:
  Closed-set: Rank-1, Rank-5, mAP, precision, recall, F1 at a threshold
  Open-set:   AUROC, unknown accuracy, non-match rejection rate

Add --sweep to run a threshold sweep from 0.40 to 0.95 and write
results/metrics_sweep.csv alongside the main metrics.json.

Usage:
    python src/evaluate.py \\
        --results  results/ranked_results.csv \\
        --labels   data/sample/labels.csv \\
        --threshold 0.70 \\
        --possible-threshold 0.55 \\
        --output   results/metrics.json \\
        --sweep

labels.csv columns: query_image, identity  ('unknown' marks open-set queries)
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score

sys.path.insert(0, str(Path(__file__).parent))


def load_csv(path: Path) -> list[dict]:
    with open(path) as f:
        return list(csv.DictReader(f))


def label_map(labels_path: Path) -> dict[str, str]:
    return {r["query_image"]: r["identity"] for r in load_csv(labels_path)}


def compute_metrics(
    results: list[dict],
    labels: dict[str, str],
    threshold: float,
    possible_threshold: float,
) -> dict:
    n_ranks = sum(1 for k in results[0] if k.startswith("identity_"))

    closed, openset = [], []
    for row in results:
        q = row["query_image"]
        true_id = labels.get(q)
        if true_id is None:
            continue
        ranked = [
            (row[f"identity_{k}"], float(row[f"score_{k}"]))
            for k in range(1, n_ranks + 1)
            if row.get(f"identity_{k}") and row.get(f"score_{k}")
        ]
        entry = {"query": q, "true_id": true_id, "ranked": ranked,
                 "top1_id": ranked[0][0], "top1_score": ranked[0][1]}
        if true_id == "unknown":
            openset.append(entry)
        else:
            closed.append(entry)

    metrics: dict = {}

    # ── Closed-set ──────────────────────────────────────────────────────────
    if closed:
        n = len(closed)

        rank1 = sum(r["top1_id"] == r["true_id"] for r in closed) / n

        rank5 = sum(
            r["true_id"] in [r["ranked"][k][0] for k in range(min(5, len(r["ranked"])))]
            for r in closed
        ) / n

        # mAP: for each query compute AP over the ranked list then average
        aps = []
        for r in closed:
            hits, ap = 0, 0.0
            for pos, (pred, _) in enumerate(r["ranked"], start=1):
                if pred == r["true_id"]:
                    hits += 1
                    ap += hits / pos
            aps.append(ap / hits if hits else 0.0)
        map_val = float(np.mean(aps))

        # Threshold-based precision / recall / F1
        tp = sum(r["top1_id"] == r["true_id"] and r["top1_score"] >= threshold for r in closed)
        fp = sum(r["top1_id"] != r["true_id"] and r["top1_score"] >= threshold for r in closed)
        fn = sum(r["top1_score"] < threshold for r in closed)

        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec  = tp / (tp + fn) if (tp + fn) else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0

        metrics["closed_set"] = {
            "n_queries":  n,
            "rank1":      round(rank1,   4),
            "rank5":      round(rank5,   4),
            "map":        round(map_val, 4),
            "threshold":  threshold,
            "precision":  round(prec, 4),
            "recall":     round(rec,  4),
            "f1":         round(f1,   4),
        }

    # ── Open-set ────────────────────────────────────────────────────────────
    if openset and closed:
        known_scores   = [r["top1_score"] for r in closed]
        unknown_scores = [r["top1_score"] for r in openset]

        # AUROC and PR AUC: unknown = positive class, low similarity = high score
        # We use sklearn for both so the implementation is auditable.
        y_true   = [1] * len(openset) + [0] * len(closed)
        y_scores = [-s for s in unknown_scores] + [-s for s in known_scores]
        auroc  = float(np.mean([
            sum(u < k for k in known_scores) / len(known_scores)
            for u in unknown_scores
        ]))  # P(unknown_score < known_score), equivalent to ROC AUC
        pr_auc = float(average_precision_score(y_true, y_scores))

        # unknown_accuracy: fraction of unknowns hard-rejected (< possible_threshold)
        unk_acc = sum(s < possible_threshold for s in unknown_scores) / len(unknown_scores)

        # non_match_rejection: fraction not confidently matched (< threshold)
        nmr = sum(s < threshold for s in unknown_scores) / len(unknown_scores)

        metrics["open_set"] = {
            "n_unknown_queries":   len(openset),
            "auroc":               round(auroc,   4),
            "pr_auc":              round(pr_auc,  4),
            "unknown_accuracy":    round(unk_acc, 4),
            "non_match_rejection": round(nmr,     4),
        }

    return metrics


def _build_sweep_rows(
    results: list[dict],
    labels: dict[str, str],
    lo: float = 0.40,
    hi: float = 0.95,
    step: float = 0.05,
) -> list[dict]:
    """Return per-threshold sweep rows (shared by threshold_sweep and find_optimal_threshold)."""
    n_ranks = sum(1 for k in results[0] if k.startswith("identity_"))

    closed, openset = [], []
    for row in results:
        q = row["query_image"]
        true_id = labels.get(q)
        if true_id is None:
            continue
        ranked = [
            (row[f"identity_{k}"], float(row[f"score_{k}"]))
            for k in range(1, n_ranks + 1)
            if row.get(f"identity_{k}") and row.get(f"score_{k}")
        ]
        entry = {"true_id": true_id, "top1_id": ranked[0][0], "top1_score": ranked[0][1]}
        (openset if true_id == "unknown" else closed).append(entry)

    unknown_scores = [r["top1_score"] for r in openset]

    thresholds, t = [], lo
    while t <= hi + 1e-9:
        thresholds.append(round(t, 2))
        t += step

    rows = []
    for tau in thresholds:
        poss_tau = max(0.0, round(tau - 0.15, 2))
        tp = sum(r["top1_id"] == r["true_id"] and r["top1_score"] >= tau for r in closed)
        fp = sum(r["top1_id"] != r["true_id"] and r["top1_score"] >= tau for r in closed)
        fn = sum(r["top1_score"] < tau for r in closed)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec  = tp / (tp + fn) if (tp + fn) else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        unk_acc = sum(s < poss_tau for s in unknown_scores) / len(unknown_scores) if unknown_scores else 0.0
        nmr     = sum(s < tau     for s in unknown_scores) / len(unknown_scores) if unknown_scores else 0.0
        rows.append({
            "tau_match":           tau,
            "tau_possible":        poss_tau,
            "precision":           round(prec,    4),
            "recall":              round(rec,     4),
            "f1":                  round(f1,      4),
            "unknown_accuracy":    round(unk_acc, 4),
            "non_match_rejection": round(nmr,     4),
        })
    return rows


def find_optimal_threshold(results: list[dict], labels: dict[str, str]) -> dict:
    """Return the τ_match that maximises F1, plus its precision/recall/F1."""
    rows = _build_sweep_rows(results, labels)
    best = max(rows, key=lambda r: r["f1"])
    return {
        "tau_match":    best["tau_match"],
        "tau_possible": best["tau_possible"],
        "precision":    best["precision"],
        "recall":       best["recall"],
        "f1":           best["f1"],
    }


def threshold_sweep(
    results: list[dict],
    labels: dict[str, str],
    sweep_output: Path,
    lo: float = 0.40,
    hi: float = 0.95,
    step: float = 0.05,
) -> None:
    """Sweep τ_match from lo to hi; τ_possible = τ_match - 0.15 (floored at 0).
    Writes a CSV with one row per threshold level.
    """
    rows = _build_sweep_rows(results, labels, lo, hi, step)
    best = max(rows, key=lambda r: r["f1"])

    sweep_output.parent.mkdir(parents=True, exist_ok=True)
    with open(sweep_output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"\nThreshold sweep → {sweep_output}")
    print(f"  {'tau':>6}  {'prec':>6}  {'rec':>6}  {'f1':>6}  {'unk_acc':>8}  {'nmr':>6}")
    for r in rows:
        marker = " ← best F1" if r["tau_match"] == best["tau_match"] else ""
        print(f"  {r['tau_match']:>6.2f}  {r['precision']:>6.4f}  {r['recall']:>6.4f}  "
              f"{r['f1']:>6.4f}  {r['unknown_accuracy']:>8.4f}  {r['non_match_rejection']:>6.4f}{marker}")


def main():
    ap = argparse.ArgumentParser(description="Evaluate ReID pipeline results")
    ap.add_argument("--results",             required=True, type=Path)
    ap.add_argument("--labels",              required=True, type=Path)
    ap.add_argument("--threshold",           default=0.70,  type=float)
    ap.add_argument("--possible-threshold",  default=0.55,  type=float)
    ap.add_argument("--output",              default="results/metrics.json", type=Path)
    ap.add_argument("--sweep",               action="store_true",
                    help="Also run a threshold sweep and write metrics_sweep.csv")
    args = ap.parse_args()

    results = load_csv(args.results)
    labels  = label_map(args.labels)
    metrics = compute_metrics(results, labels, args.threshold, args.possible_threshold)

    # Always find and report the F1-optimal threshold alongside the fixed one
    optimal = find_optimal_threshold(results, labels)
    metrics["optimal_threshold"] = optimal

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(metrics, f, indent=2)

    print(json.dumps(metrics, indent=2))

    opt = optimal
    print(f"\nF1-optimal threshold: τ={opt['tau_match']} "
          f"(precision={opt['precision']}, recall={opt['recall']}, F1={opt['f1']})")

    if args.sweep:
        sweep_path = args.output.parent / (args.output.stem + "_sweep.csv")
        threshold_sweep(results, labels, sweep_path)


if __name__ == "__main__":
    main()
