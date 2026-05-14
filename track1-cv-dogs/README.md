# Dog Re-Identification Pipeline

Individual dog ReID using pretrained DINOv2 embeddings and cosine similarity.
Given a reference image (or small gallery) of a dog, the pipeline ranks query
images by how likely they depict the same individual.

---

## Setup

Requires **Python ≥ 3.9**.

```bash
cd track1-cv-dogs
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Quick smoke test (no download required)

Synthetic sample data is committed under `data/sample/`.

```bash
# 1. Run the pipeline
python src/reid_pipeline.py \
    --reference data/sample/reference \
    --query     data/sample/query \
    --output    results/ranked_results.csv \
    --top-k     10 \
    --model     dinov2

# 2. Evaluate
python src/evaluate.py \
    --results  results/ranked_results.csv \
    --labels   data/sample/labels.csv \
    --threshold 0.70 \
    --possible-threshold 0.55 \
    --output   results/metrics.json \
    --sweep    # also writes results/metrics_sweep.csv

# 3. Visualise success and failure cases
python src/visualise.py \
    --results   results/ranked_results.csv \
    --labels    data/sample/labels.csv \
    --reference data/sample/reference \
    --query     data/sample/query \
    --output-dir results
```

Results land in `results/` (gitignored):

| File | Contents |
|---|---|
| `ranked_results.csv` | Per-query ranked similarity scores |
| `metrics.json` | Rank-1, Rank-5, mAP, F1, open-set AUROC |
| `success_cases.png` | Grid of Rank-1 correct retrievals |
| `failure_cases.png` | Grid of Rank-1 wrong retrievals |
| `score_distribution.png` | Histogram of correct vs wrong vs unknown scores |

Expected output on the 3-identity synthetic sample (smoke test):
```json
{"closed_set": {"rank1": 1.0, "rank5": 1.0, "map": 1.0, "f1": 1.0}}
```

---

## Ad-hoc inference (no dataset required)

Run the pipeline on your own images directly — no directory structure needed:

```bash
python src/inference.py \
    -r ref1.jpg ref2.jpg \
    -q query1.jpg query2.jpg query3.jpg \
    --model dinov2

# Output:
# Rank  Score    Decision         Query
# ────────────────────────────────────────────────────────────
# 1     0.9917   MATCH            query1.jpg
# 2     0.7103   MATCH            query2.jpg
# 3     0.4821   UNKNOWN          query3.jpg
```

Multiple reference images are averaged into a single prototype. Decisions follow
the same two-threshold rule as the full pipeline (`--threshold`, `--possible-threshold`).

---

## Full evaluation on DogFaceNet

### 1. Download data

```bash
python src/fetch_dogfacenet.py \
    --output data/dogfacenet/source \
    --max-identities 100 \
    --min-images-per-identity 3
```

Downloads the top-100 most-photographed identities from
`dimidagd/DogFaceNet_224resize` on HuggingFace (~1 GB, one-time download).

### 2. Build identity-disjoint split

```bash
python src/prepare_reid_split.py \
    --source  data/dogfacenet/source \
    --output  data/dogfacenet/split \
    --refs-per-identity    2 \
    --queries-per-identity 3 \
    --open-set-fraction    0.10 \
    --seed 0 \
    --overwrite
```

Writes `split/reference/`, `split/query/`, `split/labels.csv`, and
`split/manifest.json` (reproducibility record).

### 3. Run the pipeline

```bash
python src/reid_pipeline.py \
    --reference data/dogfacenet/split/reference \
    --query     data/dogfacenet/split/query \
    --output    results/ranked_results.csv \
    --top-k     10 \
    --model     dinov2
```

Switch backbone with `--model resnet50` or `--model efficientnet`.

### 4. Evaluate

```bash
python src/evaluate.py \
    --results  results/ranked_results.csv \
    --labels   data/dogfacenet/split/labels.csv \
    --threshold 0.70 \
    --possible-threshold 0.55 \
    --output   results/metrics.json \
    --sweep    # also writes results/metrics_sweep.csv
```

### 5. Cross-validate

```bash
python src/cross_validate.py \
    --reference data/dogfacenet/split/reference \
    --query     data/dogfacenet/split/query \
    --labels    data/dogfacenet/split/labels.csv \
    --output    results/cv_metrics.json
```

Runs leave-one-shot-out CV (one reference image per fold rotates into the
query pool). Reports mean ± std for Rank-1, Rank-5, mAP, F1, AUROC,
and PR AUC across folds.

### 6. Visualise

```bash
python src/visualise.py \
    --results   results/ranked_results.csv \
    --labels    data/dogfacenet/split/labels.csv \
    --reference data/dogfacenet/split/reference \
    --query     data/dogfacenet/split/query \
    --output-dir results \
    --n-cases 5
```

Produces three output files: `success_cases.png`, `failure_cases.png`, and
`score_distribution.png` (overlaid histogram of correct-match, wrong-match,
and unknown query scores with threshold lines).

---

## Backbone comparison

Run steps 3–4 for each `--model` flag and compare the resulting `metrics.json`
files. Latency is printed automatically at the end of each pipeline run.

Measured results on DogFaceNet (300 queries, CPU, batch=16):

| Model | Rank-1 | mAP | AUROC | CPU latency/query |
|---|---|---|---|---|
| DINOv2 ViT-S/14 | **0.941** | **0.968** | 0.838 | **28 ms** |
| EfficientNet-B0 | 0.911 | 0.942 | **0.865** | 66 ms |
| ResNet50 | 0.867 | 0.919 | 0.821 | 127 ms |

---

## Project layout

```
track1-cv-dogs/
├── src/
│   ├── embed.py               # DINOv2 / ResNet50 / EfficientNet feature extractor
│   ├── reid_pipeline.py       # main entry point
│   ├── evaluate.py            # retrieval and threshold metrics
│   ├── visualise.py           # success / failure case grids
│   ├── fetch_dogfacenet.py    # download DogFaceNet from HuggingFace
│   └── prepare_reid_split.py  # identity-disjoint split builder
├── data/
│   └── sample/                # committed synthetic sample (smoke test)
│       ├── reference/         # 3 identities × 2 images each
│       ├── query/             # 9 known + 3 open-set queries
│       └── labels.csv
├── results/                   # gitignored — generated by running the pipeline
├── requirements.txt
├── REPORT.md
└── README.md
```
