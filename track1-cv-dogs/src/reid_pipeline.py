"""Dog re-identification pipeline.

Builds a gallery of per-identity prototype embeddings from reference images,
then ranks gallery identities for each query image by cosine similarity.

Usage:
    python src/reid_pipeline.py \\
        --reference data/sample/reference \\
        --query     data/sample/query \\
        --output    results/ranked_results.csv \\
        --top-k     10 \\
        --model     dinov2

Reference directory layout:  reference/{identity_id}/{image.jpg|png}
Query directory layout:       query/{image.jpg|png}  (flat)

Output CSV columns:
    query_image, identity_1, score_1, identity_2, score_2, ..., decision
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from embed import Embedder


def build_gallery(ref_dir: Path, embedder: Embedder) -> tuple[list[str], np.ndarray]:
    """Return (identity_names, prototype_matrix) where matrix is (N, D), L2-normalised."""
    names, protos = [], []
    for id_dir in sorted(d for d in ref_dir.iterdir() if d.is_dir()):
        paths = sorted(
            p for p in id_dir.iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )
        if not paths:
            continue
        imgs = [Image.open(p).convert("RGB") for p in paths]
        embs = embedder.embed(imgs)          # (k, D), already L2-normed
        proto = embs.mean(axis=0)
        norm = np.linalg.norm(proto)
        proto = proto / norm if norm > 1e-8 else proto
        names.append(id_dir.name)
        protos.append(proto)
    return names, np.stack(protos)           # (N, D)


def rank_queries(
    query_dir: Path,
    names: list[str],
    gallery: np.ndarray,
    embedder: Embedder,
    top_k: int,
    threshold: float,
    possible_threshold: float,
) -> list[dict]:
    paths = sorted(
        p for p in query_dir.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    rows = []
    batch_size = 16

    for i in tqdm(range(0, len(paths), batch_size), desc="Querying"):
        batch = paths[i : i + batch_size]
        imgs = [Image.open(p).convert("RGB") for p in batch]
        embs = embedder.embed(imgs)          # (B, D)
        sims = embs @ gallery.T              # (B, N)

        for path, sim in zip(batch, sims):
            order = np.argsort(-sim)[:top_k]
            top_score = float(sim[order[0]])

            if top_score >= threshold:
                decision = "match"
            elif top_score >= possible_threshold:
                decision = "possible_match"
            else:
                decision = "unknown"

            row = {"query_image": path.name, "decision": decision}
            for rank, idx in enumerate(order, start=1):
                row[f"identity_{rank}"] = names[idx]
                row[f"score_{rank}"] = round(float(sim[idx]), 6)
            rows.append(row)

    return rows


def save_results(rows: list[dict], output: Path, top_k: int):
    output.parent.mkdir(parents=True, exist_ok=True)
    cols = ["query_image", "decision"] + [
        col for k in range(1, top_k + 1)
        for col in (f"identity_{k}", f"score_{k}")
    ]
    with open(output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description="Dog ReID pipeline")
    ap.add_argument("--reference", required=True, type=Path)
    ap.add_argument("--query",     required=True, type=Path)
    ap.add_argument("--output",    default="results/ranked_results.csv", type=Path)
    ap.add_argument("--top-k",     default=10, type=int)
    ap.add_argument("--model",     default="dinov2",
                    choices=["dinov2", "resnet50", "efficientnet"])
    ap.add_argument("--threshold",          default=0.70, type=float,
                    help="Cosine similarity above which a query is a confident match")
    ap.add_argument("--possible-threshold", default=0.55, type=float,
                    help="Below this the query is flagged unknown; between the two = possible_match")
    args = ap.parse_args()

    print(f"Loading {args.model} embedder …")
    embedder = Embedder(model_name=args.model)

    print("Building gallery …")
    names, gallery = build_gallery(args.reference, embedder)
    print(f"  {len(names)} identities in gallery")

    rows = rank_queries(
        args.query, names, gallery, embedder,
        top_k=args.top_k,
        threshold=args.threshold,
        possible_threshold=args.possible_threshold,
    )

    save_results(rows, args.output, top_k=args.top_k)
    print(f"Saved {len(rows)} rows → {args.output}")


if __name__ == "__main__":
    main()
