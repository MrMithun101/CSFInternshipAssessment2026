"""Leave-one-shot-out cross-validation for the dog ReID pipeline.

For each fold k, reference image k for every identity rotates into the
query pool as a known positive while the remaining reference images form
the gallery prototype. With 2 reference images per identity this gives
2 folds. Reports mean ± std across folds for all key metrics.

Pre-embeds everything once to avoid redundant forward passes.

Usage:
    python src/cross_validate.py \\
        --reference data/dogfacenet/split/reference \\
        --query     data/dogfacenet/split/query \\
        --labels    data/dogfacenet/split/labels.csv \\
        --model     dinov2 \\
        --output    results/cv_metrics.json
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from sklearn.metrics import average_precision_score
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from embed import Embedder


# ── Data loading ─────────────────────────────────────────────────────────────

def load_labels(path: Path) -> dict[str, str]:
    with open(path) as f:
        return {r["query_image"]: r["identity"] for r in csv.DictReader(f)}


def embed_directory_flat(directory: Path, embedder: Embedder, desc: str = "") -> dict[str, np.ndarray]:
    """Embed all images in a flat directory. Returns {filename: embedding}."""
    paths = sorted(
        p for p in directory.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    result = {}
    batch_size = 16
    for i in tqdm(range(0, len(paths), batch_size), desc=desc):
        batch = paths[i : i + batch_size]
        imgs  = [Image.open(p).convert("RGB") for p in batch]
        embs  = embedder.embed(imgs)
        for p, e in zip(batch, embs):
            result[p.name] = e
    return result


def embed_reference_dir(ref_dir: Path, embedder: Embedder) -> dict[str, dict[str, np.ndarray]]:
    """Returns {identity: {filename: embedding}} for all reference images."""
    result: dict[str, dict[str, np.ndarray]] = {}
    identities = sorted(d for d in ref_dir.iterdir() if d.is_dir())
    all_paths = [
        (id_dir.name, p)
        for id_dir in identities
        for p in sorted(id_dir.iterdir())
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    ]
    batch_size = 16
    for i in tqdm(range(0, len(all_paths), batch_size), desc="Embedding references"):
        batch = all_paths[i : i + batch_size]
        imgs  = [Image.open(p).convert("RGB") for _, p in batch]
        embs  = embedder.embed(imgs)
        for (ident, p), e in zip(batch, embs):
            result.setdefault(ident, {})[p.name] = e
    return result


# ── Per-fold evaluation ───────────────────────────────────────────────────────

def fold_metrics(
    ref_embs: dict[str, dict[str, np.ndarray]],
    held_out_key: str,
    query_embs: dict[str, np.ndarray],
    query_labels: dict[str, str],
    threshold: float,
    possible_threshold: float,
) -> dict:
    """
    Build gallery from all reference images except held_out_key per identity.
    Held-out images become additional known-positive queries.
    Returns metric dict for this fold.
    """
    identity_names: list[str] = []
    gallery_matrix: list[np.ndarray] = []

    for ident, imgs in sorted(ref_embs.items()):
        gallery_imgs = {k: v for k, v in imgs.items() if k != held_out_key}
        if not gallery_imgs:
            continue
        proto = np.mean(list(gallery_imgs.values()), axis=0)
        norm  = np.linalg.norm(proto)
        identity_names.append(ident)
        gallery_matrix.append(proto / norm if norm > 1e-8 else proto)

    G = np.stack(gallery_matrix)  # (N_gallery, D)

    # Build query list: original queries + held-out reference images (known)
    entries = []

    # Held-out reference images → known queries with true label = identity
    for ident, imgs in sorted(ref_embs.items()):
        if held_out_key in imgs:
            emb = imgs[held_out_key]
            sims = emb @ G.T
            order = np.argsort(-sims)
            entries.append({
                "true_id":    ident,
                "top1_id":    identity_names[order[0]],
                "top1_score": float(sims[order[0]]),
                "ranked":     [(identity_names[j], float(sims[j])) for j in order],
            })

    # Original query pool
    for fname, emb in query_embs.items():
        true_id = query_labels.get(fname)
        if true_id is None:
            continue
        sims  = emb @ G.T
        order = np.argsort(-sims)
        entries.append({
            "true_id":    true_id,
            "top1_id":    identity_names[order[0]],
            "top1_score": float(sims[order[0]]),
            "ranked":     [(identity_names[j], float(sims[j])) for j in order],
        })

    closed  = [e for e in entries if e["true_id"] != "unknown"]
    openset = [e for e in entries if e["true_id"] == "unknown"]

    metrics: dict = {}

    if closed:
        n = len(closed)
        rank1 = sum(e["top1_id"] == e["true_id"] for e in closed) / n
        rank5 = sum(
            e["true_id"] in [e["ranked"][k][0] for k in range(min(5, len(e["ranked"])))]
            for e in closed
        ) / n

        aps = []
        for e in closed:
            hits, ap = 0, 0.0
            for pos, (pred, _) in enumerate(e["ranked"], start=1):
                if pred == e["true_id"]:
                    hits += 1
                    ap += hits / pos
            aps.append(ap / hits if hits else 0.0)

        tp = sum(e["top1_id"] == e["true_id"] and e["top1_score"] >= threshold for e in closed)
        fp = sum(e["top1_id"] != e["true_id"] and e["top1_score"] >= threshold for e in closed)
        fn = sum(e["top1_score"] < threshold for e in closed)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec  = tp / (tp + fn) if (tp + fn) else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0

        metrics["closed_set"] = {
            "n_queries": n,
            "rank1":     round(rank1,             4),
            "rank5":     round(rank5,             4),
            "map":       round(float(np.mean(aps)), 4),
            "precision": round(prec, 4),
            "recall":    round(rec,  4),
            "f1":        round(f1,   4),
        }

    if openset and closed:
        known_scores   = [e["top1_score"] for e in closed]
        unknown_scores = [e["top1_score"] for e in openset]

        auroc = float(np.mean([
            sum(u < k for k in known_scores) / len(known_scores)
            for u in unknown_scores
        ]))

        y_true   = [1] * len(openset) + [0] * len(closed)
        y_scores = [-s for s in unknown_scores] + [-s for s in known_scores]
        pr_auc   = float(average_precision_score(y_true, y_scores))

        nmr     = sum(s < threshold         for s in unknown_scores) / len(unknown_scores)
        unk_acc = sum(s < possible_threshold for s in unknown_scores) / len(unknown_scores)

        metrics["open_set"] = {
            "n_unknown_queries":   len(openset),
            "auroc":               round(auroc,   4),
            "pr_auc":              round(pr_auc,  4),
            "unknown_accuracy":    round(unk_acc, 4),
            "non_match_rejection": round(nmr,     4),
        }

    return metrics


# ── Aggregation ───────────────────────────────────────────────────────────────

def aggregate(fold_results: list[dict]) -> dict:
    """Compute mean ± std across folds for every scalar metric."""
    out: dict = {"n_folds": len(fold_results)}
    for section in ("closed_set", "open_set"):
        if section not in fold_results[0]:
            continue
        keys = [k for k, v in fold_results[0][section].items() if isinstance(v, (int, float))]
        agg: dict = {}
        for k in keys:
            vals = [f[section][k] for f in fold_results if section in f]
            agg[k]            = round(float(np.mean(vals)), 4)
            agg[k + "_std"]   = round(float(np.std(vals)),  4)
        out[section] = agg
    return out


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Leave-one-shot-out cross-validation")
    ap.add_argument("--reference",          required=True, type=Path)
    ap.add_argument("--query",              required=True, type=Path)
    ap.add_argument("--labels",             required=True, type=Path)
    ap.add_argument("--model",              default="dinov2",
                    choices=["dinov2", "resnet50", "efficientnet"])
    ap.add_argument("--threshold",          default=0.70, type=float)
    ap.add_argument("--possible-threshold", default=0.55, type=float)
    ap.add_argument("--output",             default="results/cv_metrics.json", type=Path)
    args = ap.parse_args()

    print(f"Loading {args.model} embedder …")
    embedder = Embedder(model_name=args.model)

    print("Embedding reference images …")
    ref_embs = embed_reference_dir(args.reference, embedder)

    print("Embedding query images …")
    query_embs = embed_directory_flat(args.query, embedder, desc="Embedding queries")
    query_labels = load_labels(args.labels)

    # Determine held-out keys (reference filenames, e.g. "0000.jpg", "0001.jpg")
    sample_id    = next(iter(ref_embs))
    held_out_keys = sorted(ref_embs[sample_id].keys())
    n_folds      = len(held_out_keys)
    print(f"\nRunning {n_folds}-fold leave-one-shot-out CV …")

    fold_results = []
    for fold_i, key in enumerate(held_out_keys):
        print(f"\n── Fold {fold_i} (held-out: {key}) ──")
        m = fold_metrics(
            ref_embs, key, query_embs, query_labels,
            args.threshold, args.possible_threshold,
        )
        fold_results.append(m)
        cs = m.get("closed_set", {})
        os = m.get("open_set", {})
        print(f"  Rank-1 {cs.get('rank1','—')}  mAP {cs.get('map','—')}  "
              f"AUROC {os.get('auroc','—')}  PR-AUC {os.get('pr_auc','—')}")

    agg = aggregate(fold_results)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump({"summary": agg, "folds": fold_results}, f, indent=2)

    print(f"\n{'─'*55}")
    print(f"Cross-validation summary ({n_folds} folds):")
    cs = agg.get("closed_set", {})
    os = agg.get("open_set",   {})
    print(f"  Rank-1  {cs.get('rank1','—')} ± {cs.get('rank1_std','—')}")
    print(f"  Rank-5  {cs.get('rank5','—')} ± {cs.get('rank5_std','—')}")
    print(f"  mAP     {cs.get('map','—')} ± {cs.get('map_std','—')}")
    print(f"  F1      {cs.get('f1','—')} ± {cs.get('f1_std','—')}")
    print(f"  AUROC   {os.get('auroc','—')} ± {os.get('auroc_std','—')}")
    print(f"  PR AUC  {os.get('pr_auc','—')} ± {os.get('pr_auc_std','—')}")
    print(f"Saved → {args.output}")


if __name__ == "__main__":
    main()
