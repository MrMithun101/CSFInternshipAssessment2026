# Claude Code Context — CSF Internship Assessment 2026

## Who I am
Mithun Selvananthan. This is my take-home internship assessment for AgroLedger — a livestock
traceability company focused on Canadian sheep producers, compliance, disease response, and
making animal data useful for farm management decisions.

---

## Repo structure

```
CSFInternshipAssessment2026/
├── track1-cv-dogs/        ← ACTIVE TRACK — work goes here
│   └── BRIEF.md           ← full task spec, read this first
├── track2-fullstack/      ← COMPLETE — do not touch
└── README.md              ← submission instructions
```

---

## What is already done — DO NOT TOUCH

**Track 2 (fullstack) is fully complete and submitted.**
- Branch: `track2-fullstack` (PR already open on GitHub against `main`)
- All bugs fixed, weight tracking feature implemented, 21 tests passing
- AUDIT.md, RETRO.md, ARCH_PROPOSAL.md all written
- Do not modify anything inside `track2-fullstack/`

---

## Active task — Track 1: Dog Re-Identification (Computer Vision)

### Working branch
Always work on `track1-cv` branch. It was created from `main` (original state).
If not already on it: `git checkout track1-cv`

### What the task is
Build a **re-identification (ReID) pipeline** for dogs. This is NOT breed classification.
The goal is: given a reference image of a specific dog, determine which query images
contain that same individual dog.

Pipeline must:
1. Accept a reference image (or small gallery)
2. Accept a set of query images
3. Return a ranked list or similarity scores — which queries match the reference

### Deliverables (all required)
- [ ] **Runnable prototype** — script or notebook with a clear entry point
- [ ] **Evaluation** — metrics (Rank-1, mAP, or precision/recall), results on positive
      and negative matches, at least one visualisation of successes and failures
- [ ] **`REPORT.md`** (~500 words) covering:
  - Approach and key design decisions (feature extractor, similarity metric, embeddings)
  - At least two specific failure modes with concrete mitigations
  - Generalisation section: how would this pipeline adapt to sheep (less data, different
    visual characteristics)? What assumptions break?
- [ ] **`README.md`** inside `track1-cv-dogs/` with setup and usage instructions
- [ ] **Clean commits** — prefer small, descriptive commits over one big dump

### Optional extension (do if time allows)
Open-set recognition: what happens when a query image contains a dog NOT in the reference
gallery? How does the system handle and signal unknown individuals?

---

## Technical approach guidance

### Recommended starting point
Use a **pretrained vision model** as a feature extractor (do not train from scratch).
Good options:
- `facebook/dinov2-base` or `dinov2-large` via HuggingFace — strong general visual features,
  works well for fine-grained ReID without fine-tuning
- `clip-vit-large-patch14` — good zero-shot similarity via embeddings
- A ResNet/EfficientNet pretrained on ImageNet as a simpler baseline

### Similarity metric
Cosine similarity on L2-normalised embeddings is the standard starting point for ReID.

### Dataset
No dataset is provided — source your own. Good options:
- Stanford Dogs Dataset (http://vision.stanford.edu/aditya86/ImageNetDogs/)
- DogFaceNet (https://github.com/GuillaumeMougeot/DogFaceNet)
- A small curated set of your own images works fine for a prototype

Document your data choices and why you made them. There is no single right answer.

### Do NOT commit
- Virtual environments (`venv/`, `.venv/`, `env/`)
- Model weights or large checkpoints (>50MB)
- Raw datasets or large image folders
- API keys or credentials
- `__pycache__/`, `.ipynb_checkpoints/`

Add a `.gitignore` inside `track1-cv-dogs/` if needed.

---

## Submission requirements (PR description must include all of these)

When the work is ready, the PR is opened from `track1-cv` → `main` on GitHub
at `https://github.com/MrMithun101/CSFInternshipAssessment2026`.

The PR description MUST include:
- Full name: Mithun Selvananthan
- Email address
- Assessment track: Computer Vision (Track 1)
- Concise summary of what was built
- Setup and run instructions
- Test/evaluation results observed
- Screenshots or visualisations of successes and failures
- Discussion of trade-offs, limitations, and what would be done next

---

## What the reviewers care about (AgroLedger context)

- **Sound technical reasoning** — why did you choose this model, this metric, this dataset?
- **Honest evaluation** — show failures, not just successes
- **Generalisation thinking** — the sheep question is not hypothetical; AgroLedger's product
  is about sheep traceability. A strong answer here is directly relevant to the role.
- **Clear communication** — the REPORT.md and PR description matter as much as the code
- **Simplicity** — a working, well-explained prototype beats a complex system that's hard
  to reproduce or understand

---

## How to run track 2 (reference only — do not modify)

```bash
cd track2-fullstack/app/backend
npm install
node seed.js
npm test        # 21 tests, all passing
npm start       # runs on port 3000
```
