import importlib.util
from pathlib import Path
import sys
import unittest

MODULE = Path(__file__).resolve().parents[1] / "parking_allocation_demo.py"
spec = importlib.util.spec_from_file_location("parking_demo", MODULE)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class AllocationTests(unittest.TestCase):
    def test_touching_boundaries_are_not_conflicts(self):
        self.assertFalse(m.overlap(0, 10, 10, 20))
        self.assertTrue(m.overlap(0, 10, 9.99, 20))

    def test_single_bay_selects_best_total_weight(self):
        req = [m.Request("long", 0, 20, 8, 0),
               m.Request("a", 0, 10, 5, 0), m.Request("b", 10, 20, 5, 0)]
        chosen = m.solve(req, bays=1)
        self.assertEqual({a.request.key for a in chosen}, {"a", "b"})

    def test_guarded_solution_obeys_expanded_intervals(self):
        sol = m.solve(m.requests_for_demo(), buffered=True)
        for i, a in enumerate(sol):
            for b in sol[i+1:]:
                if a.bay == b.bay:
                    self.assertFalse(m.overlap(a.request.start-a.request.guard,
                                               a.request.end+a.request.guard,
                                               b.request.start-b.request.guard,
                                               b.request.end+b.request.guard))

    def test_more_constraints_cannot_raise_optimal_weight(self):
        req = m.requests_for_demo()
        score = lambda sol: sum(a.request.weight for a in sol)
        self.assertLessEqual(score(m.solve(req, buffered=True)), score(m.solve(req)))

    def test_seed_reproduces_entire_report(self):
        req = m.requests_for_demo()
        self.assertEqual(m.experiment(req, trials=50, seed=4),
                         m.experiment(req, trials=50, seed=4))

    def test_zero_guards_give_identical_policies(self):
        req = [m.Request("a", 0, 30, 1, 0), m.Request("b", 30, 60, 1, 0)]
        r = m.experiment(req, trials=100)
        self.assertEqual(r["policies"]["nominal"], r["policies"]["buffered"])

    def test_empty_and_invalid_inputs(self):
        r = m.experiment([], trials=2)
        self.assertIsNone(r["policies"]["nominal"]["request_conflict_rate"])
        with self.assertRaises(ValueError):
            m.Request("bad", 10, 0, 1, 0)
        with self.assertRaises(ValueError):
            m.solve([], bays=0)
        with self.assertRaises(ValueError):
            m.experiment([], trials=0)
        with self.assertRaises(ValueError):
            m.solve([m.Request("a", 0, 10, 1, 0), m.Request("a", 10, 20, 1, 0)])


if __name__ == "__main__":
    unittest.main()
