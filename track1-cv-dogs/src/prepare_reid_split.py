"""Build an identity-disjoint ReID split from a source image directory.

Identities are randomly partitioned into closed-set (appear in gallery) and
open-set (query-only, labelled 'unknown'). A manifest.json records all
parameters for exact reproducibility.

Usage:
    python src/prepare_reid_split.py \\
        --source  data/dogfacenet/source \\
        --output  data/dogfacenet/split \\
        --refs-per-identity    2 \\
        --queries-per-identity 3 \\
        --open-set-fraction    0.10 \\
        --seed 0 \\
        --overwrite

Output layout:
    split/
      reference/{identity}/{0000.jpg, 0001.jpg, …}   ← gallery images
      query/{identity_stem.jpg, …}                    ← flat query pool
      labels.csv                                      ← query_image, identity
      manifest.json                                   ← reproducibility record
"""

import argparse
import csv
import json
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def build_split(
    source_dir: Path,
    output_dir: Path,
    refs_per_id: int,
    queries_per_id: int,
    open_set_frac: float,
    seed: int,
    overwrite: bool,
):
    if output_dir.exists():
        if not overwrite:
            print(f"{output_dir} already exists — use --overwrite to regenerate.")
            return
        shutil.rmtree(output_dir)

    rng = random.Random(seed)

    ref_dir   = output_dir / "reference"
    query_dir = output_dir / "query"
    ref_dir.mkdir(parents=True)
    query_dir.mkdir(parents=True)

    identities = sorted(d.name for d in source_dir.iterdir() if d.is_dir())
    rng.shuffle(identities)

    n_open = max(1, round(len(identities) * open_set_frac))
    open_ids   = set(identities[:n_open])
    closed_ids = identities[n_open:]

    labels: list[dict] = []
    skipped = 0

    # ── Closed-set: reference + query images ────────────────────────────────
    for ident in closed_ids:
        imgs = sorted((source_dir / ident).glob("*.jpg"))
        rng.shuffle(imgs)
        needed = refs_per_id + queries_per_id
        if len(imgs) < needed:
            skipped += 1
            continue

        (ref_dir / ident).mkdir()
        for i, src in enumerate(imgs[:refs_per_id]):
            shutil.copy(src, ref_dir / ident / f"{i:04d}.jpg")

        for src in imgs[refs_per_id:needed]:
            dst = f"{ident}_{src.stem}.jpg"
            shutil.copy(src, query_dir / dst)
            labels.append({"query_image": dst, "identity": ident})

    # ── Open-set: query only (not in gallery) ───────────────────────────────
    for ident in open_ids:
        imgs = sorted((source_dir / ident).glob("*.jpg"))
        rng.shuffle(imgs)
        for src in imgs[:queries_per_id]:
            dst = f"open_{ident}_{src.stem}.jpg"
            shutil.copy(src, query_dir / dst)
            labels.append({"query_image": dst, "identity": "unknown"})

    # ── labels.csv ──────────────────────────────────────────────────────────
    labels.sort(key=lambda x: x["query_image"])
    with open(output_dir / "labels.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["query_image", "identity"])
        w.writeheader()
        w.writerows(labels)

    # ── manifest.json ───────────────────────────────────────────────────────
    n_ref_imgs = sum(
        len(list(d.iterdir()))
        for d in ref_dir.iterdir() if d.is_dir()
    )
    manifest = {
        "seed":                seed,
        "refs_per_identity":   refs_per_id,
        "queries_per_identity": queries_per_id,
        "open_set_fraction":   open_set_frac,
        "n_closed_identities": len(closed_ids) - skipped,
        "n_open_identities":   len(open_ids),
        "n_reference_images":  n_ref_imgs,
        "n_query_images":      len(labels),
        "skipped_identities":  skipped,
    }
    with open(output_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Split ready:")
    print(f"  Closed: {manifest['n_closed_identities']} identities, "
          f"{n_ref_imgs} reference images, "
          f"{len(labels) - len(open_ids) * queries_per_id} closed queries")
    print(f"  Open:   {manifest['n_open_identities']} identities, "
          f"{len(open_ids) * queries_per_id} unknown queries")
    print(f"  Total queries: {len(labels)}")
    if skipped:
        print(f"  Skipped {skipped} identities with fewer than {refs_per_id + queries_per_id} images")


def main():
    ap = argparse.ArgumentParser(description="Build identity-disjoint ReID split")
    ap.add_argument("--source",                  required=True, type=Path)
    ap.add_argument("--output",                  required=True, type=Path)
    ap.add_argument("--refs-per-identity",       default=2,    type=int)
    ap.add_argument("--queries-per-identity",    default=3,    type=int)
    ap.add_argument("--open-set-fraction",       default=0.10, type=float)
    ap.add_argument("--seed",                    default=0,    type=int)
    ap.add_argument("--overwrite",               action="store_true")
    args = ap.parse_args()

    build_split(
        args.source, args.output,
        args.refs_per_identity, args.queries_per_identity,
        args.open_set_fraction, args.seed, args.overwrite,
    )


if __name__ == "__main__":
    main()
