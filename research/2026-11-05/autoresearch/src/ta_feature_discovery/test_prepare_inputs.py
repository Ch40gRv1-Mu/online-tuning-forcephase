"""Synthetic isolation/identity properties for the input joiner; no SAT runs."""
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

MODULE_PATH = Path(__file__).with_name("prepare_inputs.py")
SPEC = importlib.util.spec_from_file_location("prepare_inputs_under_test", MODULE_PATH)
prep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prep)
FIT, FEEDBACK, GATE, OUTSIDE = (str(i) * 32 for i in (1, 2, 3, 4))
SOURCE_SHA, EXTRACTOR_SHA = "a" * 64, "b" * 64


class InputProperties(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.roles = self.root / "roles.csv"
        self.pairs = self.root / "pairs.csv"
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.write_roles()
        self.write_csv(self.pairs, ["hash", "false_result", "true_result", "false_wall_s", "true_wall_s"], [
            [FIT, "SAT", "TIMEOUT", .5, 5001], [FEEDBACK, "TIMEOUT", "TIMEOUT", 5000, 5000],
            # Prohibited outcomes must not be parsed, validated, or exported.
            [GATE, "SECRET_INVALID", "SECRET_INVALID", "private", "private"],
            [OUTSIDE, "SECRET_INVALID", "SECRET_INVALID", "private", "private"],
        ])

    def tearDown(self):
        self.temp.cleanup()

    def write_csv(self, path, header, rows):
        with path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)

    def write_roles(self, cross_group=False, excluded_fit=False):
        self.write_csv(self.roles, ["hash", "role", "isohash", "variables", "clauses", "bytes", "url"], [
            [FIT, "development_fit", "fit-group", 10, 20, 100_000_001 if excluded_fit else 1000, "https://benchmark-database.de/file/" + FIT],
            [FEEDBACK, "development_feedback", "fit-group" if cross_group else "feedback-group", 10, 20, 1000, "https://benchmark-database.de/file/" + FEEDBACK],
            [GATE, "development_gate", "gate-group", 10, 20, 1000, "https://benchmark-database.de/file/" + GATE],
        ])

    def receipt(self, filename="0", cpu=.4, value=1., source=SOURCE_SHA, extractor=EXTRACTOR_SHA):
        path = self.cache / filename / (FIT + ".features.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"hash": FIT, "source_sha256": source, "extractor_sha256": extractor,
                "metadata_count_mismatch": False, "feature_cpu_s": cpu,
                "features": {**{key: value for key in prep.FEATURES}, "g_gate_motifs_exact": 1}}
        path.write_text(json.dumps(data))
        return path

    def checksums(self):
        path = self.root / "checksums.json"
        path.write_text(json.dumps({h: {"sha256_cnf": SOURCE_SHA, "sha256_xz": "c" * 64} for h in (FIT, FEEDBACK)}))
        return path

    def build(self, **kwargs):
        return prep.build_dataset(self.pairs, self.roles, [self.cache],
            extractor_sha=EXTRACTOR_SHA,
            expected_counts={"development_fit": 1, "development_feedback": 1}, **kwargs)

    def test_no_gate_or_outside_performance_export_and_unknown_not_winner(self):
        data, tasks = self.build()
        self.assertEqual([r["id"] for r in data["rows"]], [FIT, FEEDBACK])
        self.assertNotIn("SECRET", json.dumps(data))
        self.assertEqual(data["rows"][1]["costs"], {"false": 10000., "true": 10000.})
        self.assertEqual(data["rows"][1]["statuses"], {"false": "TIMEOUT", "true": "TIMEOUT"})
        self.assertFalse(data["static_complete"])
        self.assertTrue(all(r["feature_status"] == "PENDING" for r in data["rows"]))
        self.assertEqual(tasks["ready_tasks"], [])

    def test_identifier_uses_basename_gbd_prefix_not_hexadecimal_seed(self):
        filename = ("../cnfs/sc2025/99718c1729a8de3347a9946f1836421d-"
                    "bivium-39-200-0s0-0xdcfb6ab71951500b8e460045bd45afee15c87e08b0072eb174-43.cnf.xz")
        self.assertEqual(prep.identifier(filename), "99718c1729a8de3347a9946f1836421d")
        self.assertEqual(prep.identifier("/" + GATE + "/" + FIT + "-seed-" + FEEDBACK + ".cnf"), FIT)
        self.assertEqual(prep.identifier("C:\\source\\" + FIT.upper() + ".cnf"), FIT)

    def test_identifier_does_not_search_arbitrary_name_or_long_hex_run(self):
        for value in ("description-" + FIT + ".cnf", FIT + FEEDBACK, None):
            with self.assertRaisesRegex(ValueError, "basename must start"):
                prep.identifier(value)

    def test_equivalence_cannot_cross_fit_feedback(self):
        self.write_roles(cross_group=True)
        with self.assertRaisesRegex(ValueError, "equivalence group"):
            self.build()

    def test_cached_identity_pinned_and_canonical_cost_not_fastest(self):
        self.receipt("a", cpu=.8)
        self.receipt("z", cpu=.1)
        data, _ = self.build(checksums_paths=[self.checksums()])
        row = data["rows"][0]
        self.assertEqual(row["feature_status"], "AVAILABLE")
        self.assertEqual(row["feature_cpu_s"], .8)
        self.assertEqual(len(row["feature_source"]["equivalent_receipts"]), 2)
        self.assertEqual(row["costs"], {"false": .5, "true": 10000.})
        self.assertNotIn("conflicts", row["features"])

    def test_frozen_public_identity_mismatch_is_fatal(self):
        self.receipt(source="d" * 64)
        with self.assertRaisesRegex(ValueError, "differs from frozen public checksum"):
            self.build(checksums_paths=[self.checksums()])

    def test_task_exact_byte_count_comes_from_checksum_not_gbd_feature(self):
        checksum = self.checksums()
        data = json.loads(checksum.read_text())
        data[FIT]["bytes_cnf"] = 1151  # GBD feature bytes is 1000.
        checksum.write_text(json.dumps(data))
        _, tasks = self.build(checksums_paths=[checksum])
        by_id = {task["instance_id"]: task for task in tasks["ready_tasks"]}
        self.assertEqual(by_id[FIT]["metadata"]["bytes"], 1151)
        self.assertNotIn("bytes", by_id[FEEDBACK]["metadata"])

    def test_same_sha_cannot_have_conflicting_original_byte_lengths(self):
        first, second = self.root / "first.json", self.root / "second.json"
        first.write_text(json.dumps({FIT: {"sha256_cnf": SOURCE_SHA, "bytes_cnf": 1151}}))
        second.write_text(json.dumps({FIT: {"sha256_cnf": SOURCE_SHA, "bytes_cnf": 1152}}))
        with self.assertRaisesRegex(ValueError, "conflicting public checksum"):
            prep.load_checksums([first, second])

    def test_compatible_receipts_cannot_silently_disagree(self):
        self.receipt("a", value=.2)
        self.receipt("b", value=.3)
        with self.assertRaisesRegex(ValueError, "receipts disagree"):
            self.build()

    def test_wrong_extractor_is_pending_not_reused(self):
        self.receipt(extractor="e" * 64)
        data, _ = self.build()
        self.assertEqual(data["rows"][0]["feature_status"], "PENDING")

    def test_resource_exclusion_not_dropped_or_charged_as_cache(self):
        self.write_roles(excluded_fit=True)
        self.receipt()
        data, tasks = self.build(checksums_paths=[self.checksums()])
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual(data["rows"][0]["feature_status"], "EXCLUDED")
        self.assertFalse(data["rows"][0]["eligible"])
        self.assertTrue(all(v is None for v in data["rows"][0]["features"].values()))
        self.assertEqual([task["instance_id"] for task in tasks["ready_tasks"]], [FEEDBACK])

    def test_formal_failed_receipt_is_unavailable_and_not_redispatched(self):
        source = self.root / "extractor.cpp"
        source.write_text("// synthetic identity")
        node = self.root / "node"
        node.mkdir()
        record = {"instance_id": FIT, "role": "development_fit",
            "status": "TIMEOUT", "input_sha256": SOURCE_SHA,
            "extractor_source_sha256": prep.sha(source), "feature_cpu_s": 2.0,
            "profile": prep.NODE_PROFILE, "node_id": "synthetic"}
        record["task_key"] = prep.canonical_sha({k: record[k] for k in ("instance_id", "input_sha256", "extractor_source_sha256", "profile")})
        record["receipt_content_sha256"] = prep.canonical_sha(record)
        (node / "failed.json").write_text(json.dumps(record))
        data, tasks = self.build(checksums_paths=[self.checksums()], extractor_source=source, node_result_dirs=[node])
        row = data["rows"][0]
        self.assertEqual(row["feature_status"], "UNAVAILABLE")
        self.assertEqual(row["feature_cpu_s"], 2.)
        self.assertNotIn(FIT, {task["instance_id"] for task in tasks["tasks"]})
        self.assertFalse(data["static_complete"])  # Feedback still pending.

    def test_node_source_identity_content_binding_and_all_preparation_cost(self):
        source = self.root / "extractor.cpp"
        source.write_text("// synthetic source")
        node = self.root / "node"
        node.mkdir()
        record = {"instance_id": FIT, "role": "development_fit", "status": "COMPLETE",
            "input_sha256": SOURCE_SHA, "extractor_source_sha256": prep.sha(source),
            "extractor_binary_sha256": "e" * 64, "feature_cpu_s": .3,
            "preparation_cpu_s": .2, "total_accounted_cpu_s": .5,
            "profile": prep.NODE_PROFILE,
            "features": {**{key: 1. for key in prep.FEATURES}, "g_gate_motifs_exact": 1}}
        record["task_key"] = prep.canonical_sha({k: record[k] for k in ("instance_id", "input_sha256", "extractor_source_sha256", "profile")})
        record["receipt_content_sha256"] = prep.canonical_sha(record)
        path = node / "complete.json"
        path.write_text(json.dumps(record))
        data, tasks = self.build(checksums_paths=[self.checksums()], extractor_source=source, node_result_dirs=[node])
        self.assertEqual(data["rows"][0]["feature_cpu_s"], .5)
        self.assertEqual(data["rows"][0]["feature_status"], "AVAILABLE")
        self.assertNotIn("dispatchable", tasks["ready_tasks"][0])
        record["features"]["s_mean_length"] = 4.
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "content SHA mismatch"):
            self.build(checksums_paths=[self.checksums()], extractor_source=source, node_result_dirs=[node])

    def test_companion_cost_disagreement_rejected(self):
        companion = self.root / "other.csv"
        companion.write_text(self.pairs.read_text().replace(",0.5,", ",0.6,"))
        with self.assertRaisesRegex(ValueError, "companion paired CSV disagree"):
            self.build(paired_csv=companion)

    def test_immutable_publication_and_same_content_resume(self):
        path = self.root / "snapshot.json"
        prep.save_new(path, {"a": 1})
        prep.save_new(path, {"a": 1})
        with self.assertRaises(FileExistsError):
            prep.save_new(path, {"a": 2})

    def test_xlsx_boolean_modes_and_only_needed_columns(self):
        path = self.root / "source.xlsx"
        rows = [
            '<row r="1"><c r="A1" t="inlineStr"><is><t>ile</t></is></c><c r="B1" t="inlineStr"><is><t>polarity_mode</t></is></c><c r="C1" t="inlineStr"><is><t>result</t></is></c><c r="D1" t="inlineStr"><is><t>wall_time_s</t></is></c><c r="E1" t="inlineStr"><is><t>conflicts</t></is></c></row>'
        ]
        for i, (h, mode) in enumerate(((FIT, False), (FIT, True)), 2):
            rows.append(f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>{h}</t></is></c><c r="B{i}" t="b"><v>{int(mode)}</v></c><c r="C{i}" t="inlineStr"><is><t>SAT</t></is></c><c r="D{i}"><v>0.5</v></c><c r="E{i}"><v>999999</v></c></row>')
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="data" sheetId="1" r:id="rId1"/></sheets></workbook>')
            archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="/xl/worksheets/sheet1.xml"/></Relationships>')
            archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(rows) + '</sheetData></worksheet>')
        loaded = prep.load_labels(path, {FIT})
        self.assertEqual(set(loaded), {(FIT, "false"), (FIT, "true")})
        self.assertEqual(loaded[(FIT, "true")], {"status": "SAT", "wall": .5})
        self.assertNotIn("conflicts", list(prep.xlsx_cells(path))[0])


if __name__ == "__main__":
    unittest.main()
