"""Ad-hoc dog ReID inference — no pre-built gallery or dataset required.

Given one or more reference images of a dog and one or more query images,
ranks each query by cosine similarity to the reference prototype and prints
a match decision.

Usage:
    # single reference, single query
    python src/inference.py -r data/sample/reference/dog_a/0000.jpg \
                            -q data/sample/query/q_a_0.jpg

    # multiple references (averaged into one prototype), multiple queries
    python src/inference.py \
        -r ref1.jpg ref2.jpg ref3.jpg \
        -q query1.jpg query2.jpg query3.jpg \
        --threshold 0.70 --possible-threshold 0.55 --model dinov2
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from embed import Embedder

_DECISION_WIDTH = 14


def _decision_label(score: float, tau_match: float, tau_possible: float) -> str:
    if score >= tau_match:
        return "MATCH"
    if score >= tau_possible:
        return "POSSIBLE MATCH"
    return "UNKNOWN"


def run_inference(
    reference_paths: list[Path],
    query_paths: list[Path],
    model: str = "dinov2",
    tau_match: float = 0.70,
    tau_possible: float = 0.55,
) -> list[dict]:
    """
    Embed references into a single prototype, score each query against it.
    Returns a list of result dicts sorted by descending similarity score.
    """
    embedder = Embedder(model_name=model)

    # Build reference prototype
    ref_imgs = [Image.open(p).convert("RGB") for p in reference_paths]
    ref_embs = embedder.embed(ref_imgs)           # (N_ref, D), already L2-normed
    prototype = ref_embs.mean(axis=0)
    norm = np.linalg.norm(prototype)
    prototype = prototype / norm if norm > 1e-8 else prototype   # re-normalise

    # Embed queries
    query_imgs = [Image.open(p).convert("RGB") for p in query_paths]
    query_embs = embedder.embed(query_imgs)       # (N_query, D)

    # Score and rank
    scores = (query_embs @ prototype).tolist()    # cosine similarity (dot of unit vecs)
    results = [
        {
            "query":    query_paths[i].name,
            "score":    round(scores[i], 4),
            "decision": _decision_label(scores[i], tau_match, tau_possible),
        }
        for i in range(len(query_paths))
    ]
    results.sort(key=lambda r: -r["score"])
    return results


def main():
    ap = argparse.ArgumentParser(
        description="Ad-hoc ReID: rank query images against reference images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("-r", "--reference", nargs="+", required=True, type=Path,
                    metavar="IMG", help="Reference image(s) of the known dog")
    ap.add_argument("-q", "--query",     nargs="+", required=True, type=Path,
                    metavar="IMG", help="Query image(s) to identify")
    ap.add_argument("--model",              default="dinov2",
                    choices=["dinov2", "resnet50", "efficientnet"])
    ap.add_argument("--threshold",          default=0.70, type=float,
                    help="Cosine similarity threshold for MATCH decision")
    ap.add_argument("--possible-threshold", default=0.55, type=float,
                    help="Lower bound for POSSIBLE MATCH band")
    args = ap.parse_args()

    # Validate paths
    missing = [p for p in args.reference + args.query if not p.exists()]
    if missing:
        for p in missing:
            print(f"ERROR: file not found: {p}", file=sys.stderr)
        sys.exit(1)

    print(f"\nModel        : {args.model}")
    print(f"References   : {len(args.reference)} image(s)")
    print(f"Queries      : {len(args.query)} image(s)")
    print(f"τ_match      : {args.threshold}  |  τ_possible : {args.possible_threshold}")
    print()

    results = run_inference(
        args.reference, args.query,
        model=args.model,
        tau_match=args.threshold,
        tau_possible=args.possible_threshold,
    )

    # Pretty-print ranked results
    print(f"{'Rank':<5} {'Score':<8} {'Decision':<16} {'Query'}")
    print("─" * 60)
    for rank, r in enumerate(results, start=1):
        print(f"{rank:<5} {r['score']:<8.4f} {r['decision']:<16} {r['query']}")

    print()
    top = results[0]
    print(f"→ Best match: {top['query']}  (score={top['score']}, {top['decision']})")


if __name__ == "__main__":
    main()
