"""Source-transformation invariants; never compiles or solves an instance."""
import json
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_observer as patcher


class HookSourceProperties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Path(__file__).resolve().parents[2] / "work/ta100/observer_base"
        if not cls.base.exists():
            raise unittest.SkipTest("qualified readonly source fixture is not attached; no network fetch")
        cls.changed, cls.bindings = patcher.render(cls.base)

    def test_all_search_statements_and_arguments_are_preserved(self):
        for name in ("internal.hpp", "internal.cpp", "clause.hpp", "clause.cpp", "analyze.cpp",
                     "minimize.cpp", "shrink.cpp", "backtrack.cpp", "propagate.cpp", "decide.cpp", "restart.cpp"):
            # The only changes are separate observer statements/metadata.
            without_hooks = "".join(line for line in self.changed[name].splitlines(keepends=True)
                                    if "ta100" not in line.lower())
            nonblank = lambda text: [line for line in text.splitlines() if line.strip()]
            self.assertEqual(nonblank(without_hooks), nonblank((self.base / name).read_text()), name)

    def test_old_phase_action_logic_is_byte_identical(self):
        before = (self.base / "fpcontrol.cpp").read_text()
        after = self.changed["fpcontrol.cpp"]
        start = "void Controller::apply ("
        end = "void Controller::at_restart ("
        self.assertEqual(before[before.index(start):before.index(end)], after[after.index(start):after.index(end)])
        start = "void Controller::compute_features ("
        end = "void Controller::write_features ("
        self.assertEqual(before[before.index(start):before.index(end)], after[after.index(start):after.index(end)])

    def test_cpu_measurement_follows_new_heavy_observation_and_header_new_identity(self):
        source = self.changed["fpcontrol.cpp"]
        self.assertEqual(source.count("ta100-observer-v1"), 1)
        self.assertNotIn("ta-probe-v1", source)
        self.assertLess(source.index("I->ta100->write (log)"), source.index('process_cpu_s'))
        self.assertEqual(source.count('process_cpu_s'), 1)

    def test_fields_are_computed_and_caps_and_birth_assertion_hooks_exist(self):
        cpp = self.changed["ta100_observer.cpp"]
        body = cpp.split("const char *names[20] = {", 1)[1].split("};", 1)[0]
        columns = re.findall(r'"(td_[a-z_]+)"', body)
        self.assertEqual(len(columns), 20)
        self.assertEqual(len(set(columns)), 20)
        self.assertIn("td_clause_target_phase_violation", columns)
        self.assertIn("td_learned_postassertion_reuse_age", columns)
        self.assertIn("EDGE_CAP = 10000", cpp)
        self.assertIn("depth > 256", cpp)
        self.assertIn("size <= LIT_CAP", cpp)
        self.assertIn("std::nth_element", cpp)
        self.assertIn("std::function<int(int,int)> visit", cpp)
        propagation = self.changed["propagate.cpp"]
        a = propagation.index("before_driving_assignment (c)")
        b = propagation.index("search_assign (lit, c)", a)
        c = propagation.index("after_driving_assignment (c)", b)
        self.assertLess(a, b); self.assertLess(b, c)

    def test_anchors_and_all_input_sha_are_exact_not_best_effort(self):
        self.assertEqual(len(self.bindings), 19)
        self.assertEqual(self.bindings["fpcontrol.cpp"], "d92d0ef0638397fb6eddaad64a5b2d8619e8cf5d805d9f56dd469005bef16015")
        with self.assertRaises(ValueError):
            patcher.insert("anchor anchor", "anchor", "changed")
        with self.assertRaises(ValueError):
            patcher.insert("absent", "anchor", "changed")


if __name__ == "__main__":
    unittest.main()
