"""Unit tests for evaluation metric computations."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from evaluate import compute_metrics


def _make_results(entries: list[dict], top_k: int = 5) -> list[dict]:
    """Turn (query, true_id, ranked_ids, scores) into ranked_results.csv format."""
    rows = []
    for e in entries:
        row = {"query_image": e["query"], "decision": "match"}
        for k, (ident, score) in enumerate(zip(e["ranked_ids"], e["scores"]), start=1):
            row[f"identity_{k}"] = ident
            row[f"score_{k}"]    = str(score)
        rows.append(row)
    return rows


def _make_labels(entries: list[dict]) -> dict[str, str]:
    return {e["query"]: e["true_id"] for e in entries}


class TestRank1(unittest.TestCase):
    def test_perfect_rank1(self):
        entries = [
            {"query": "q1.jpg", "true_id": "dog_a",
             "ranked_ids": ["dog_a", "dog_b"], "scores": [0.9, 0.5]},
            {"query": "q2.jpg", "true_id": "dog_b",
             "ranked_ids": ["dog_b", "dog_a"], "scores": [0.8, 0.4]},
        ]
        m = compute_metrics(_make_results(entries), _make_labels(entries), 0.70, 0.55)
        self.assertEqual(m["closed_set"]["rank1"], 1.0)

    def test_zero_rank1(self):
        entries = [
            {"query": "q1.jpg", "true_id": "dog_a",
             "ranked_ids": ["dog_b", "dog_a"], "scores": [0.9, 0.5]},
        ]
        m = compute_metrics(_make_results(entries), _make_labels(entries), 0.70, 0.55)
        self.assertEqual(m["closed_set"]["rank1"], 0.0)

    def test_partial_rank1(self):
        entries = [
            {"query": "q1.jpg", "true_id": "dog_a",
             "ranked_ids": ["dog_a", "dog_b"], "scores": [0.9, 0.5]},
            {"query": "q2.jpg", "true_id": "dog_b",
             "ranked_ids": ["dog_a", "dog_b"], "scores": [0.9, 0.5]},
        ]
        m = compute_metrics(_make_results(entries), _make_labels(entries), 0.70, 0.55)
        self.assertEqual(m["closed_set"]["rank1"], 0.5)


class TestMAP(unittest.TestCase):
    def test_correct_at_rank1_gives_map_1(self):
        entries = [
            {"query": "q1.jpg", "true_id": "dog_a",
             "ranked_ids": ["dog_a", "dog_b", "dog_c"], "scores": [0.9, 0.6, 0.3]},
        ]
        m = compute_metrics(_make_results(entries), _make_labels(entries), 0.70, 0.55)
        self.assertAlmostEqual(m["closed_set"]["map"], 1.0)

    def test_correct_at_rank2_gives_map_half(self):
        entries = [
            {"query": "q1.jpg", "true_id": "dog_a",
             "ranked_ids": ["dog_b", "dog_a", "dog_c"], "scores": [0.9, 0.7, 0.3]},
        ]
        m = compute_metrics(_make_results(entries), _make_labels(entries), 0.70, 0.55)
        self.assertAlmostEqual(m["closed_set"]["map"], 0.5)

    def test_not_in_ranked_gives_map_0(self):
        entries = [
            {"query": "q1.jpg", "true_id": "dog_a",
             "ranked_ids": ["dog_b", "dog_c"], "scores": [0.9, 0.7]},
        ]
        m = compute_metrics(_make_results(entries), _make_labels(entries), 0.70, 0.55)
        self.assertAlmostEqual(m["closed_set"]["map"], 0.0)


class TestF1(unittest.TestCase):
    def test_all_correct_above_threshold(self):
        entries = [
            {"query": "q1.jpg", "true_id": "dog_a",
             "ranked_ids": ["dog_a", "dog_b"], "scores": [0.9, 0.5]},
            {"query": "q2.jpg", "true_id": "dog_b",
             "ranked_ids": ["dog_b", "dog_a"], "scores": [0.9, 0.5]},
        ]
        m = compute_metrics(_make_results(entries), _make_labels(entries), 0.70, 0.55)
        self.assertAlmostEqual(m["closed_set"]["f1"], 1.0)

    def test_all_below_threshold_gives_zero_f1(self):
        entries = [
            {"query": "q1.jpg", "true_id": "dog_a",
             "ranked_ids": ["dog_a", "dog_b"], "scores": [0.5, 0.3]},
        ]
        m = compute_metrics(_make_results(entries), _make_labels(entries), 0.70, 0.55)
        self.assertEqual(m["closed_set"]["f1"], 0.0)


class TestOpenSet(unittest.TestCase):
    def test_perfect_auroc(self):
        # Unknowns always score lower than knowns
        known_entries = [
            {"query": f"k{i}.jpg", "true_id": "dog_a",
             "ranked_ids": ["dog_a"], "scores": [0.95]}
            for i in range(5)
        ]
        unknown_entries = [
            {"query": f"u{i}.jpg", "true_id": "unknown",
             "ranked_ids": ["dog_a"], "scores": [0.30]}
            for i in range(5)
        ]
        entries = known_entries + unknown_entries
        m = compute_metrics(_make_results(entries), _make_labels(entries), 0.70, 0.55)
        self.assertAlmostEqual(m["open_set"]["auroc"], 1.0)

    def test_pr_auc_present(self):
        known_entries = [
            {"query": f"k{i}.jpg", "true_id": "dog_a",
             "ranked_ids": ["dog_a"], "scores": [0.95]}
            for i in range(5)
        ]
        unknown_entries = [
            {"query": f"u{i}.jpg", "true_id": "unknown",
             "ranked_ids": ["dog_a"], "scores": [0.30]}
            for i in range(5)
        ]
        m = compute_metrics(
            _make_results(known_entries + unknown_entries),
            _make_labels(known_entries + unknown_entries),
            0.70, 0.55,
        )
        self.assertIn("pr_auc", m["open_set"])
        self.assertGreater(m["open_set"]["pr_auc"], 0.5)

    def test_non_match_rejection_rate(self):
        # All unknowns score below threshold → nmr = 1.0
        known_entries = [
            {"query": "k1.jpg", "true_id": "dog_a",
             "ranked_ids": ["dog_a"], "scores": [0.9]}
        ]
        unknown_entries = [
            {"query": "u1.jpg", "true_id": "unknown",
             "ranked_ids": ["dog_a"], "scores": [0.4]}
        ]
        m = compute_metrics(
            _make_results(known_entries + unknown_entries),
            _make_labels(known_entries + unknown_entries),
            0.70, 0.55,
        )
        self.assertAlmostEqual(m["open_set"]["non_match_rejection"], 1.0)


if __name__ == "__main__":
    unittest.main()
