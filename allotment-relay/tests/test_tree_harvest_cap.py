"""果树收茬上限 — 按种苗成本算寿命，不能无限薅。"""

import unittest

from server.catalog import CROPS
from server.farming import calc_tree_harvest_max


class TreeHarvestCapTests(unittest.TestCase):
    def test_lime_cheaper_than_durian(self):
        lime = calc_tree_harvest_max("lime")
        durian = calc_tree_harvest_max("durian")
        self.assertGreaterEqual(lime, 4)
        self.assertGreaterEqual(durian, lime)
        self.assertLessEqual(lime, 10)
        self.assertLessEqual(durian, 17)

    def test_only_trees(self):
        for key, meta in CROPS.items():
            if not meta.get("tree"):
                continue
            mx = calc_tree_harvest_max(key)
            self.assertGreaterEqual(mx, 4, key)
            self.assertLessEqual(mx, 17, key)


if __name__ == "__main__":
    unittest.main()
