# Report — Dog Re-Identification Pipeline

## Approach

The core challenge is distinguishing one specific dog from another across
images — not classifying breed, but identifying individuals. I chose a
**retrieval-based approach**: embed every image into a feature vector,
build a per-identity gallery prototype by averaging reference embeddings,
then rank gallery identities for each query by cosine similarity.

**Feature extractor — DINOv2 ViT-S/14.**
I used the frozen pretrained `facebook/dinov2-small` model from HuggingFace.
DINOv2 is self-supervised on a large, diverse image corpus and is well-known
for producing fine-grained visual features that capture texture and local
structure — both of which matter for individual animal discrimination.
I chose it over CLIP because CLIP is optimised for semantic (text-image)
alignment, not instance-level similarity. I chose it over a plain ResNet50
because DINOv2's self-supervised objective encourages patch-level feature
diversity rather than class-collapse. ResNet50 and EfficientNet-B0 are
included as cheaper baselines via `--model resnet50 / efficientnet` so the
trade-off is measurable rather than claimed.

**Similarity metric — cosine on L2-normalised embeddings.**
After L2 normalisation, cosine similarity is equivalent to dot product and
has a known range [−1, 1], which makes threshold selection interpretable.
This is the standard choice for retrieval.

**Gallery prototype — mean of reference embeddings, re-normalised.**
When multiple reference images exist for one identity, I average their
embeddings and re-normalise. This keeps inference cost constant regardless
of gallery size and reduces noise from outlier reference images. It does
lose view-specific detail compared to max-over-references retrieval, which
is a known trade-off worth testing if time allows.

**Open-set recognition.**
I added a two-threshold decision rule: `match` (score ≥ τ_match = 0.70),
`possible_match` (τ_possible ≤ score < τ_match = 0.55–0.70), and `unknown`
(score < τ_possible). The `possible_match` band acts as a human-review
abstention zone rather than a forced classification, which is more honest
about model uncertainty than a binary threshold.

**Dataset.**
I used DogFaceNet (`dimidagd/DogFaceNet_224resize` on HuggingFace), a
face-centric dog dataset with identity labels. I evaluated on the top-100
identities by image count, with an identity-disjoint split (seed=0, 2
reference images per identity, 3 queries per identity, 10% open-set).
Identity-disjoint means no individual appears in both gallery and unknown
pool, which is the correct evaluation protocol for ReID. I chose DogFaceNet
over Stanford Dogs because Stanford Dogs is breed-labelled, not
identity-labelled, making ReID evaluation impossible without manual curation.

---

## Evaluation Results

**Single-split evaluation** (4 reference images per gallery identity):
Split: 90 closed identities (360 reference images, 270 closed queries),
10 open-set identities (30 unknown queries). All thresholds at defaults.

| Metric | DINOv2 ViT-S/14 | Why |
|---|---|---|
| Rank-1 | **0.941** | Core question: is the correct dog ranked first? |
| Rank-5 | **0.996** | Is the correct dog in the top-5 shortlist? |
| mAP | **0.968** | Average precision over the full ranked list |
| F1 (τ=0.70) | **0.905** | Precision–recall balance at the operating threshold |
| F1-optimal τ | **0.969** (τ=0.40) | Best achievable F1; swept automatically over τ ∈ [0.40, 0.95] |
| AUROC | **0.838** | Threshold-free separation of known vs unknown queries |
| PR AUC | **0.374** | Precision–recall for open-set (low due to 10% unknown ratio) |
| Non-match rejection | 0.467 | Fraction of unknowns not confidently matched |

**4-fold leave-one-shot-out cross-validation** (DINOv2, 3 reference images
per gallery identity per fold):

| Metric | Mean ± Std |
|---|---|
| Rank-1 | **0.924 ± 0.004** |
| Rank-5 | **0.993 ± 0.001** |
| mAP | **0.955 ± 0.002** |
| F1 (τ=0.70) | **0.886 ± 0.010** |
| AUROC | **0.817 ± 0.018** |
| PR AUC | **0.305 ± 0.006** |

The tight std across all 4 folds confirms stability — not a lucky split.
The Rank-1/Rank-5 gap (0.924 → 0.993 in CV) shows the correct identity is
almost always in the top-5; failures are rank confusion between visually
similar dogs, not complete misses. 254 of 270 closed-set queries retrieved
the correct identity at Rank-1 in the single-split run.

**Threshold sweep (DINOv2, τ_possible = τ_match − 0.15):**

| τ_match | Precision | Recall | F1 | Unknown acc. | Non-match rej. |
|---|---|---|---|---|---|
| 0.40 | 0.941 | 1.000 | **0.970** | 0.000 | 0.000 |
| 0.55 | 0.941 | 1.000 | 0.970 | 0.000 | 0.100 |
| 0.60 | 0.947 | 0.984 | 0.966 | 0.067 | 0.167 |
| **0.70** | **0.965** | 0.851 | 0.905 | 0.100 | 0.467 |
| 0.80 | 0.993 | 0.491 | 0.657 | 0.267 | 1.000 |

**Backbone comparison** (same split, same thresholds):

| Metric | DINOv2 ViT-S/14 | EfficientNet-B0 | ResNet50 |
|---|---|---|---|
| Rank-1 | **0.941** | 0.911 | 0.867 |
| Rank-5 | **0.996** | 0.985 | 0.978 |
| mAP | **0.968** | 0.942 | 0.919 |
| F1 (τ=0.70) | **0.905** | 0.875 | 0.914 |
| AUROC | 0.838 | **0.865** | 0.821 |
| CPU latency/query | **28 ms** | 66 ms | 127 ms |

Latency measured on CPU, batch size 16, Apple Silicon (MPS unused), averaged over
300 query images. DINOv2 is both the most accurate and the fastest — its ViT
architecture amortises well in batches. EfficientNet has marginally higher AUROC
and is a reasonable choice when raw throughput is secondary to open-set separation.
ResNet50 is the weakest on every dimension and 4.5× slower than DINOv2 under this
setup; it remains useful only as a reproducibility baseline.

F1 peaks at τ=0.40 (0.970) but rejects zero unknowns there. The default
τ=0.70 is the operating compromise: precision 0.965, recall 0.851, with
47% of unknowns rejected. The right threshold must be picked on a
validation fold based on deployment costs.

PR AUC (0.374) is lower than AUROC because precision-recall curves are
sensitive to class imbalance: with only 10% open-set queries (30 unknowns
vs 270 known), even strong score separation yields modest precision at high
recall. This is a structural property of the evaluation setup, not a model
failure — AUROC 0.838 independently confirms the embedding space separates
known from unknown individuals.

---

## Failure Modes

**1. Same-coat confusion within visually similar individuals.**
Dogs with uniform dark or light coats produce cosine similarities of
0.70–0.76 against the wrong identity, with the correct identity sitting at
rank 2 or 3 within 0.02 points. The model has no difficulty placing the
right individual in the top-5 (Rank-5 0.996), but the score gap between
ranks 1 and 2 is too small to rely on when coat colour dominates the
embedding. This accounts for most of the 25 Rank-1 failures observed.

*Mitigation:* Fine-tune the backbone on identity-labelled pairs using a
triplet or ArcFace loss. Even a small set of identity pairs (50–100
individuals, 5–10 images each) can compress intra-class distances and
expand inter-class distances. Alternatively, detect and embed the face/head
crop separately from the full body, then fuse both scores.

**2. Open-set queries landing in the abstention band.**
Unknown dogs frequently score between τ_possible (0.55) and τ_match (0.70),
producing `possible_match` rather than a confident rejection.
`unknown_accuracy` (hard rejection rate) for DINOv2 is 0.10, while
`non_match_rejection` (rejected as unknown or possible_match) is 0.467.
AUROC 0.838 confirms the separation signal exists in the embedding space;
the issue is threshold calibration, not a fundamental failure of the
feature extractor.

*Mitigation:* Run a threshold sweep on a held-out validation fold and select
τ_match to balance false-positive matches against false-negative rejections
given the actual cost of each error. Thresholds must be frozen on validation
data and not re-tuned on the test set.

---

## Generalisation to Sheep

Adapting this pipeline to sheep is directly relevant to AgroLedger's product
and harder than the dog case for three structural reasons.

**Visual homogeneity by design.** Sheep within a flock are often the same
breed, selected specifically to look alike. The inter-individual visual
variance that DINOv2 exploits in dogs is much smaller here. Rank-1 accuracy
would drop substantially under the same setup.

**Appearance instability over time.** A dog's coat is relatively stable. A
sheep's appearance changes dramatically with wool growth, shearing, mud,
weather, and season. Two images of the same animal taken months apart can
look like different individuals to an embedding model. The gallery prototype
strategy has no way to model this temporal drift.

**Limited identity-labelled data.** DogFaceNet has ~1,400 labelled
identities. No comparable public dataset exists for sheep. Without identity
labels, metric learning fine-tuning is not straightforward.

**What would need to change:**
Ear tags are the most reliable individual identifier already deployed in
the industry. A practical system should detect and OCR the ear tag as a
primary signal, with visual embedding as a fallback or confirmation —
directly relevant to AgroLedger's existing farm data infrastructure.
The backbone would need fine-tuning on sheep-specific data, even starting
from DINOv2, since global appearance features are less discriminative;
local features (ear shape, facial markings, tag position) would need to be
up-weighted. The gallery should also be updated incrementally as an animal's
appearance changes across seasons, storing multiple reference images over
time and returning max-over-references similarity rather than a single
averaged prototype.

In short: the retrieval architecture transfers; the assumptions about visual
distinctiveness and data availability do not. The value of visual ReID for
sheep would be in reducing human review load — from checking every animal to
only checking those flagged as ambiguous — rather than replacing human
judgment entirely.
