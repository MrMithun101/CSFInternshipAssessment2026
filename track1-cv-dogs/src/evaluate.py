"""Evaluation metrics for the dog ReID pipeline.

Computes:
  Closed-set: Rank-1, Rank-5, mAP, precision, recall, F1 at a threshold
  Open-set:   AUROC, unknown accuracy, non-match rejection rate

Usage:
    python src/evaluate.py \\
        --results  results/ranked_results.csv \\
        --labels   data/sample/labels.csv \\
        --threshold 0.70 \\
        --possible-threshold 0.55 \\
        --output   results/metrics.json

labels.csv columns: query_image, identity  ('unknown' marks open-set queries)
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

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

        # AUROC: P(unknown_score < known_score) over all pairs
        # Unknown dogs should score LOWER than known gallery members.
        pairs = len(known_scores) * len(unknown_scores)
        correct = sum(u < k for u in unknown_scores for k in known_scores)
        auroc = correct / pairs if pairs else 0.0

        # unknown_accuracy: fraction of unknowns the system hard-rejects
        # (score < possible_threshold → labelled "unknown")
        unk_acc = sum(s < possible_threshold for s in unknown_scores) / len(unknown_scores)

        # non_match_rejection: fraction of unknowns not confidently matched
        # (score < threshold → "unknown" or "possible_match")
        nmr = sum(s < threshold for s in unknown_scores) / len(unknown_scores)

        metrics["open_set"] = {
            "n_unknown_queries":  len(openset),
            "auroc":              round(auroc,   4),
            "unknown_accuracy":   round(unk_acc, 4),
            "non_match_rejection": round(nmr,    4),
        }

    return metrics


def main():
    ap = argparse.ArgumentParser(description="Evaluate ReID pipeline results")
    ap.add_argument("--results",             required=True, type=Path)
    ap.add_argument("--labels",              required=True, type=Path)
    ap.add_argument("--threshold",           default=0.70,  type=float)
    ap.add_argument("--possible-threshold",  default=0.55,  type=float)
    ap.add_argument("--output",              default="results/metrics.json", type=Path)
    args = ap.parse_args()

    results = load_csv(args.results)
    labels  = label_map(args.labels)
    metrics = compute_metrics(results, labels, args.threshold, args.possible_threshold)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(metrics, f, indent=2)

    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
