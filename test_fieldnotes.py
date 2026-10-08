import unittest

from fieldnotes import enforce, followup, load_species, rank, resolve_conf, score, shortlist

SP = [
    {"id": "bird-01", "common_name": "A", "category": "bird",
     "key_features": ["red crown cap", "stores acorns"], "habitat": "oak woodlands"},
    {"id": "plant-01", "common_name": "B", "category": "plant",
     "key_features": ["orange petals", "grasslands"], "habitat": "open grasslands"},
    {"id": "insect-01", "common_name": "C", "category": "insect",
     "key_features": ["orange black wings", "milkweed"], "habitat": "ponds"},
]


def _pad(n):
    return [{"id": f"x-{i:02d}", "common_name": "Z", "category": "rock",
             "key_features": ["zzzqqq"], "habitat": "zzzqqq"} for i in range(n)]


class TestScoring(unittest.TestCase):
    def test_score_overlap_counts(self):
        self.assertGreaterEqual(score("red crown and acorns in oak woodlands", SP[0]), 4)
        self.assertEqual(score("something about deep sea submarines", SP[0]), 0)

    def test_shortlist_top_and_bounds(self):
        ranked = shortlist("orange petals grasslands milkweed wings", SP + _pad(10))
        self.assertTrue(6 <= len(ranked) <= 8)
        self.assertIn(ranked[0]["id"], ("plant-01", "insect-01"))
        self.assertEqual(len(shortlist("deep sea submarines", SP + _pad(10))), 6)

    def test_grounding_drops_unknown(self):
        kept, viol = enforce([{"id": "plant-01", "confidence": 0.9},
                              {"id": "made-up-99", "confidence": 0.8}], ["plant-01", "bird-01"])
        self.assertEqual(kept, [{"id": "plant-01", "confidence": 0.9}])
        self.assertTrue(viol)

    def test_grounding_clean(self):
        kept, viol = enforce([{"id": "bird-01", "confidence": 0.5}], ["bird-01"])
        self.assertFalse(viol)
        self.assertEqual(len(kept), 1)


class TestRegions(unittest.TestCase):
    def test_valid_regions_load(self):
        for region in ("gujarat", "california"):
            with self.subTest(region=region):
                sp = load_species(region)
                self.assertEqual(len(sp), 50)
                for s in sp:
                    self.assertEqual(set(s), {"id", "common_name", "category",
                                              "key_features", "habitat"})
                    self.assertTrue(4 <= len(s["key_features"]) <= 6, s["id"])

    def test_invalid_region_errors(self):
        with self.assertRaises(SystemExit):
            load_species("atlantis")


class TestFollowup(unittest.TestCase):
    SHORT = [
        {"id": "a", "key_features": ["red beak", "green body"]},
        {"id": "b", "key_features": ["red beak", "long tail"]},
    ]

    def test_differing_feature(self):
        q = followup(self.SHORT, [{"id": "a"}, {"id": "b"}])
        self.assertTrue(q.startswith("Does it have: ") and q.endswith("?"))
        self.assertIn(q[len("Does it have: "):-1], ("green body", "long tail"))

    def test_identical_features_fallback(self):
        short = [{"id": "a", "key_features": ["red beak"]},
                 {"id": "b", "key_features": ["red beak"]}]
        self.assertEqual(followup(short, [{"id": "a"}, {"id": "b"}]),
                         "What colour is it, and what is it doing?")

    def test_single_candidate_fallback(self):
        self.assertEqual(followup(self.SHORT, [{"id": "a"}]),
                         "What colour is it, and what is it doing?")


class TestConfidence(unittest.TestCase):
    def test_identical_fallback_rank(self):
        cands, src = resolve_conf([{"id": "a", "confidence": 0.5},
                                   {"id": "b", "confidence": 0.5}])
        self.assertEqual(src, "rank")
        self.assertEqual([c["confidence"] for c in cands], [0.6, 0.3])

    def test_missing_fallback_rank(self):
        cands, src = resolve_conf([{"id": "a"}, {"id": "b", "confidence": 0.9}])
        self.assertEqual(src, "rank")
        self.assertEqual([c["confidence"] for c in cands], [0.6, 0.3])

    def test_distinct_keeps_model(self):
        cands, src = resolve_conf([{"id": "a", "confidence": 0.9},
                                   {"id": "b", "confidence": 0.4}])
        self.assertEqual(src, "model")
        self.assertEqual([c["confidence"] for c in cands], [0.9, 0.4])

    def test_no_ids_raises(self):
        with self.assertRaises(ValueError):
            resolve_conf([{"noid": 1}])


class TestRank(unittest.TestCase):
    def test_sorts_descending_top1_highest(self):
        cands = [{"id": "a", "confidence": 0.3}, {"id": "b", "confidence": 0.9},
                 {"id": "c", "confidence": 0.6}]
        ranked = rank(cands)
        self.assertEqual([c["id"] for c in ranked], ["b", "c", "a"])
        self.assertEqual(ranked[0]["confidence"], 0.9)

    def test_ties_keep_model_order(self):
        cands = [{"id": "a", "confidence": 0.5}, {"id": "b", "confidence": 0.5},
                 {"id": "c", "confidence": 0.8}]
        self.assertEqual([c["id"] for c in rank(cands)], ["c", "a", "b"])


if __name__ == "__main__":
    unittest.main()
