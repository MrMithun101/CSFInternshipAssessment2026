"""Feature extraction for dog ReID.

Supports DINOv2 (default), ResNet50, and EfficientNet-B0 as backbones.
All embeddings are L2-normalised before returning.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F
import torchvision.models as tvm
from PIL import Image
from transformers import AutoImageProcessor, AutoModel


class Embedder:
    """Wraps a pretrained backbone and exposes a simple embed() interface."""

    MODEL_IDS = {
        "dinov2": "facebook/dinov2-small",
        "resnet50": None,
        "efficientnet": None,
    }

    def __init__(self, model_name: str = "dinov2", device: Optional[str] = None):
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._build()

    def _build(self):
        if self.model_name == "dinov2":
            hf_id = self.MODEL_IDS["dinov2"]
            self.processor = AutoImageProcessor.from_pretrained(hf_id)
            self.model = AutoModel.from_pretrained(hf_id).to(self.device)
            self.transform = None

        elif self.model_name == "resnet50":
            weights = tvm.ResNet50_Weights.DEFAULT
            backbone = tvm.resnet50(weights=weights)
            # strip the classification head; output is (B, 2048, 1, 1)
            self.model = torch.nn.Sequential(*list(backbone.children())[:-1]).to(self.device)
            self.processor = None
            self.transform = weights.transforms()

        elif self.model_name == "efficientnet":
            weights = tvm.EfficientNet_B0_Weights.DEFAULT
            backbone = tvm.efficientnet_b0(weights=weights)
            backbone.classifier = torch.nn.Identity()
            self.model = backbone.to(self.device)
            self.processor = None
            self.transform = weights.transforms()

        else:
            raise ValueError(f"Unknown model '{self.model_name}'. Choose: dinov2, resnet50, efficientnet")

        self.model.eval()

    @torch.no_grad()
    def embed(self, images: list) -> np.ndarray:
        """Embed a list of PIL Images. Returns (N, D) float32 array, L2-normalised."""
        if self.model_name == "dinov2":
            inputs = self.processor(images=images, return_tensors="pt").to(self.device)
            out = self.model(**inputs)
            vecs = out.last_hidden_state[:, 0]  # CLS token
        else:
            tensors = torch.stack([self.transform(img) for img in images]).to(self.device)
            vecs = self.model(tensors)
            if vecs.dim() == 4:
                vecs = vecs.squeeze(-1).squeeze(-1)

        vecs = F.normalize(vecs, dim=-1)
        return vecs.cpu().numpy().astype(np.float32)

    def embed_image(self, image: Image.Image) -> np.ndarray:
        return self.embed([image])[0]

    def embed_dir(self, directory: Path, batch_size: int = 16) -> dict:
        """Embed all images in a flat directory. Returns {stem: embedding}."""
        paths = sorted(
            p for p in directory.iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )
        result = {}
        for i in range(0, len(paths), batch_size):
            batch = paths[i : i + batch_size]
            imgs = [Image.open(p).convert("RGB") for p in batch]
            embs = self.embed(imgs)
            for p, e in zip(batch, embs):
                result[p.name] = e
        return result
