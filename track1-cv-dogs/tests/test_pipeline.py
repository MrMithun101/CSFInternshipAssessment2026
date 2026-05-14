"""Unit tests for the ReID pipeline core logic."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestGalleryPrototype(unittest.TestCase):
    """Gallery prototype is L2-normalised mean of reference embeddings."""

    def _make_proto(self, vecs: list[list[float]]) -> np.ndarray:
        import torch
        import torch.nn.functional as F
        embs  = np.array(vecs, dtype=np.float32)
        # Normalise each embedding first (as Embedder does)
        norms = np.linalg.norm(embs, axis=1, keepdims=True)
        embs  = embs / np.where(norms > 1e-8, norms, 1.0)
        proto = embs.mean(axis=0)
        norm  = np.linalg.norm(proto)
        return proto / norm if norm > 1e-8 else proto

    def test_single_ref_is_unit(self):
        proto = self._make_proto([[3.0, 4.0]])
        self.assertAlmostEqual(float(np.linalg.norm(proto)), 1.0, places=5)

    def test_multi_ref_is_unit(self):
        proto = self._make_proto([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        self.assertAlmostEqual(float(np.linalg.norm(proto)), 1.0, places=5)

    def test_identical_refs_equal_single(self):
        single = self._make_proto([[3.0, 4.0]])
        double = self._make_proto([[3.0, 4.0], [3.0, 4.0]])
        np.testing.assert_allclose(single, double, atol=1e-5)


class TestCosineSimilarity(unittest.TestCase):
    """L2-normalised cosine similarity behaves as expected."""

    def _cosine(self, a: list[float], b: list[float]) -> float:
        a_n = np.array(a, dtype=np.float32)
        b_n = np.array(b, dtype=np.float32)
        a_n /= np.linalg.norm(a_n)
        b_n /= np.linalg.norm(b_n)
        return float(a_n @ b_n)

    def test_identical_vectors_score_one(self):
        self.assertAlmostEqual(self._cosine([1, 2, 3], [1, 2, 3]), 1.0, places=5)

    def test_orthogonal_vectors_score_zero(self):
        self.assertAlmostEqual(self._cosine([1, 0], [0, 1]), 0.0, places=5)

    def test_opposite_vectors_score_minus_one(self):
        self.assertAlmostEqual(self._cosine([1, 0], [-1, 0]), -1.0, places=5)

    def test_ranking_order(self):
        gallery = {
            "dog_a": np.array([1.0, 0.0], dtype=np.float32),
            "dog_b": np.array([0.0, 1.0], dtype=np.float32),
        }
        query = np.array([0.9, 0.1], dtype=np.float32)
        query /= np.linalg.norm(query)
        scores = {k: float(query @ v) for k, v in gallery.items()}
        ranked = sorted(scores, key=lambda k: -scores[k])
        self.assertEqual(ranked[0], "dog_a")
        self.assertEqual(ranked[1], "dog_b")


class TestDecisionThresholds(unittest.TestCase):
    def _decision(self, score: float, tau_match: float, tau_possible: float) -> str:
        if score >= tau_match:
            return "match"
        elif score >= tau_possible:
            return "possible_match"
        return "unknown"

    def test_above_match_threshold(self):
        self.assertEqual(self._decision(0.75, 0.70, 0.55), "match")

    def test_in_possible_band(self):
        self.assertEqual(self._decision(0.60, 0.70, 0.55), "possible_match")

    def test_below_possible_threshold(self):
        self.assertEqual(self._decision(0.40, 0.70, 0.55), "unknown")

    def test_at_match_boundary(self):
        self.assertEqual(self._decision(0.70, 0.70, 0.55), "match")

    def test_at_possible_boundary(self):
        self.assertEqual(self._decision(0.55, 0.70, 0.55), "possible_match")


if __name__ == "__main__":
    unittest.main()
