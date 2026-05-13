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

**Single-split evaluation** (2 reference images per gallery identity):
Split: 90 closed identities (180 reference images, 270 closed queries),
10 open-set identities (30 unknown queries). All thresholds at defaults.

| Metric | DINOv2 ViT-S/14 | ResNet50 | EfficientNet-B0 |
|---|---|---|---|
| Rank-1 | **0.907** | 0.804 | 0.837 |
| Rank-5 | **0.996** | 0.982 | 0.970 |
| mAP | **0.942** | 0.881 | 0.894 |
| F1 (τ=0.70) | 0.824 | **0.861** | 0.776 |
| Open-set AUROC | 0.716 | 0.668 | **0.797** |
| PR AUC | 0.277 | 0.198 | **0.309** |
| Non-match rejection | 0.533 | 0.267 | 0.733 |

**2-fold leave-one-shot-out cross-validation** (DINOv2, 1 reference image
per gallery identity per fold):

| Metric | Mean ± Std |
|---|---|
| Rank-1 | 0.781 ± 0.006 |
| Rank-5 | 0.960 ± 0.007 |
| mAP | 0.853 ± 0.006 |
| F1 (τ=0.70) | 0.632 ± 0.014 |
| AUROC | 0.644 ± 0.010 |
| PR AUC | 0.181 ± 0.016 |

The CV numbers are lower than the single-split numbers because each fold
uses only 1 reference image per gallery identity — the harder, more
realistic scenario representing minimal enrollment (one photo per animal).
The held-out reference images also become additional known queries,
introducing harder positive cases. The low std (± 0.006 on Rank-1) confirms
the numbers are stable across folds, not a lucky draw.

DINOv2 leads the single-split on closed-set retrieval. The Rank-1/Rank-5
gap (0.907 → 0.996) shows the correct identity is almost always in the
top-5; failures are rank confusion between visually similar dogs, not
complete misses.

One notable result: EfficientNet-B0 outperforms DINOv2 on open-set AUROC
and PR AUC. DINOv2's high closed-set confidence scores compress the
similarity range, reducing separation between known and unknown queries.
Open-set performance does not simply follow closed-set retrieval quality.

**Threshold sweep (DINOv2, τ_possible = τ_match − 0.15):**

| τ_match | Precision | Recall | F1 | Unknown acc. | Non-match rej. |
|---|---|---|---|---|---|
| 0.40 | 0.907 | 1.000 | **0.951** | 0.000 | 0.000 |
| 0.55 | 0.909 | 0.976 | 0.941 | 0.000 | 0.100 |
| 0.60 | 0.922 | 0.944 | 0.933 | 0.067 | 0.200 |
| **0.70** | **0.964** | 0.719 | 0.824 | 0.100 | 0.533 |
| 0.80 | 1.000 | 0.293 | 0.453 | 0.267 | 1.000 |

F1 peaks at τ=0.40 (0.951) but rejects zero unknowns there — the model
confidently assigns every unknown to the nearest gallery identity. The
default τ=0.70 is a deliberate operating compromise: precision 0.964 with
53% of unknowns rejected, at the cost of recall dropping to 0.719. The
right threshold depends on the cost of a false-positive match vs. the cost
of sending a query to human review, and must be picked on a validation fold
rather than the test set.

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
`non_match_rejection` (rejected as unknown or possible_match) is 0.533.
AUROC 0.716 confirms the separation signal exists in the embedding space;
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
