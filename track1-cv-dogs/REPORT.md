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
trade-off is measurable.

**Similarity metric — cosine on L2-normalised embeddings.**
After L2 normalisation, cosine similarity is equivalent to dot product.
This is the standard choice for retrieval because it is invariant to
embedding magnitude and has a known range [−1, 1], which makes threshold
selection interpretable.

**Gallery prototype — mean of reference embeddings, re-normalised.**
When multiple reference images exist for one identity, I average their
embeddings and re-normalise. This is a simple and auditable strategy.
It loses view-specific detail compared to storing all reference embeddings
and taking a max-over-references, but it keeps inference cost constant
regardless of gallery size and reduces noise from outlier reference images.

**Open-set recognition.**
I added a two-threshold decision rule: `match` (score ≥ τ_match),
`possible_match` (τ_possible ≤ score < τ_match), and `unknown`
(score < τ_possible). The `possible_match` band acts as a human-review
abstention zone rather than a hard classification, which is more honest
about model uncertainty than a binary threshold.

**Dataset.**
I used DogFaceNet (`dimidagd/DogFaceNet_224resize` on HuggingFace) — a
face-centric dog dataset with identity labels across 1,393 individuals.
I evaluated on the top-100 identities by image count, with an
identity-disjoint split (seed=0, 2 reference images per identity,
3 queries per identity, 10% open-set). Identity-disjoint means no
individual appears in both gallery and unknown pool, which is the correct
evaluation protocol for ReID. I chose DogFaceNet over Stanford Dogs because
Stanford Dogs is breed-labelled rather than identity-labelled, making ReID
evaluation impossible without manual curation.

---

## Failure Modes

**1. Same-coat confusion within visually similar breeds.**
Dogs with uniform dark or light coats can produce cosine similarities of
0.70–0.76 against the wrong identity, with the correct identity sitting at
rank 2 or 3 within 0.02. The model has no problem identifying the right
individual in abstract — it lands in the top-5 almost always — but the
score gap between ranks 1 and 2 is too small to be reliable when coat colour
dominates the embedding.

*Mitigation:* Fine-tune the backbone on identity-labelled pairs with a
triplet or ArcFace loss. Even a small number of identity pairs (50–100
individuals, 5–10 images each) can significantly compress intra-class
distances and expand inter-class distances. Alternatively, segment the
animal first and embed face/head crops separately from body, then fuse.

**2. Open-set queries landing in the abstention band.**
Unknown dogs frequently score between τ_possible (0.55) and τ_match (0.70),
producing `possible_match` rather than a confident rejection. Hard
`unknown_accuracy` is therefore low even when the AUROC (separation signal
in embedding space) is reasonable. The thresholds shipped as defaults are
not calibrated — they are starting points.

*Mitigation:* Run a threshold sweep on a held-out validation fold and pick
τ_match to optimise the operating cost (false-positive match vs.
false-negative rejection). The sweep output is in `results/` after
evaluation. For a production system, thresholds must be frozen on
validation data before final test reporting.

---

## Generalisation to Sheep

Adapting this pipeline to sheep is directly relevant to AgroLedger's product
and harder than the dog case for three structural reasons.

**Visual homogeneity by design.** Sheep within a flock are often the same
breed and selected specifically to look alike. The inter-individual visual
variance that DINOv2 exploits in dogs is much smaller here. Rank-1 accuracy
would drop substantially under the same setup.

**Appearance instability over time.** A dog's coat is relatively stable.
A sheep's appearance changes dramatically with wool growth, shearing, mud,
weather, and season. Two images of the same animal taken three months apart
can look like different individuals to an embedding model. The gallery
prototype strategy (averaging reference images) has no way to model this
temporal drift.

**Limited identity-labelled data.** DogFaceNet has ~1,400 labelled identities.
No comparable public dataset exists for sheep. Without identity labels,
metric learning fine-tuning is not straightforward. Few-shot adaptation
(e.g. prototypical networks) trained on dog identities and transferred to
sheep is plausible but untested at the scale AgroLedger would need.

**What would need to change:**

- The feature extractor would need fine-tuning on sheep-specific data,
  even if starting from DINOv2. Global appearance features are less
  discriminative; local features (ear shape, facial markings, tag position)
  would need to be up-weighted.
- Ear tags are the most reliable individual identifier already deployed
  in the industry. A practical system should detect and OCR the ear tag as
  a primary signal, with visual embedding as a fallback or confirmation.
  AgroLedger's existing farm records (RFID, pen location, weight history)
  could fuse with the visual similarity score rather than replacing it.
- Temporal modelling matters. A gallery should be updated incrementally
  as the animal's appearance changes. Storing multiple reference images
  across time and returning a max-over-references similarity, rather than
  a single averaged prototype, would help handle seasonal variation.
- The open-set case is more important for sheep than for dogs. In a working
  farm setting, new animals arrive regularly. The pipeline should default to
  flagging unknowns for human review rather than forcing a match.

In short: the same retrieval architecture is a valid starting point, but
the assumptions about visual distinctiveness and data availability do not
transfer cleanly. The value of the visual component would be in reducing
human review load — from checking every individual to only checking those
flagged as ambiguous — rather than replacing human judgment entirely.
