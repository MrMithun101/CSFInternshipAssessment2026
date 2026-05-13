"""Download DogFaceNet from HuggingFace and save to identity-folder format.

Source: dimidagd/DogFaceNet_224resize (HuggingFace Datasets)
Each identity gets its own subdirectory: output/{identity_id}/0000.jpg, 0001.jpg, …

Usage:
    python src/fetch_dogfacenet.py \\
        --output data/dogfacenet/source \\
        --max-identities 100 \\
        --min-images-per-identity 3
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))


def fetch(output_dir: Path, max_identities: int, min_images: int):
    try:
        from datasets import load_dataset
    except ImportError:
        print("Missing dependency: pip install datasets")
        sys.exit(1)

    from PIL import Image as PILImage

    print("Loading dimidagd/DogFaceNet_224resize from HuggingFace …")
    ds = load_dataset("dimidagd/DogFaceNet_224resize", split="train",
                      trust_remote_code=True)

    # Identify the label column (second non-image column, usually 'label' or 'labels')
    id_col = next(
        (c for c in ds.column_names if c != "image"),
        ds.column_names[1]
    )
    print(f"Using column '{id_col}' as identity label")

    counts = Counter(ds[id_col])
    eligible = sorted(
        [(ident, cnt) for ident, cnt in counts.items() if cnt >= min_images],
        key=lambda x: -x[1],
    )
    selected = {ident for ident, _ in eligible[:max_identities]}
    print(f"Selected {len(selected)} identities "
          f"(top-{max_identities} by image count, min {min_images} images each)")

    output_dir.mkdir(parents=True, exist_ok=True)
    per_id: dict[str, int] = {}

    for item in tqdm(ds, desc="Saving images"):
        ident = str(item[id_col])
        if ident not in selected:
            continue

        id_dir = output_dir / ident
        id_dir.mkdir(exist_ok=True)

        idx = per_id.get(ident, 0)
        out_path = id_dir / f"{idx:04d}.jpg"

        raw = item["image"]
        img = raw if isinstance(raw, PILImage.Image) else PILImage.fromarray(raw)
        img.convert("RGB").save(out_path, quality=95)
        per_id[ident] = idx + 1

    total = sum(per_id.values())
    print(f"Saved {total} images across {len(per_id)} identities → {output_dir}")


def main():
    ap = argparse.ArgumentParser(description="Fetch DogFaceNet from HuggingFace")
    ap.add_argument("--output",                    required=True, type=Path)
    ap.add_argument("--max-identities",            default=100,   type=int)
    ap.add_argument("--min-images-per-identity",   default=3,     type=int)
    args = ap.parse_args()
    fetch(args.output, args.max_identities, args.min_images_per_identity)


if __name__ == "__main__":
    main()
