"""Exact logging-only TA100 observer transformation; never builds or runs SAT."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ASSETS = Path(__file__).resolve().parent / "observer"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def insert(text, anchor, replacement, expected=1):
    if text.count(anchor) != expected:
        raise ValueError("qualified source anchor count differs: " + repr(anchor))
    return text.replace(anchor, replacement)


def render(source_dir):
    source_dir = Path(source_dir)
    bindings = json.loads((ASSETS / "BASE_SOURCES.json").read_text())["files"]
    for name, digest in bindings.items():
        if sha(source_dir / name) != digest:
            raise ValueError("unqualified base source: " + name)
    original = {name: (source_dir / name).read_text() for name in bindings}
    result = dict(original)
    result["internal.hpp"] = insert(result["internal.hpp"], '#include "fpcontrol.hpp"',
        '#include "fpcontrol.hpp"\n#include "ta100_observer.hpp"')
    result["internal.hpp"] = insert(result["internal.hpp"], '  FPC::Counters fpcc;',
        '  TA100::Observer *ta100 = nullptr; // passive observation only\n  FPC::Counters fpcc;')
    result["internal.cpp"] = insert(result["internal.cpp"], '  delete fpc;\n',
        '  delete ta100;\n  delete fpc;\n')
    result["internal.cpp"] = insert(result["internal.cpp"], 'int Internal::cdcl_loop_with_inprocessing () {\n',
        'int Internal::cdcl_loop_with_inprocessing () {\n  if (opts.fpc && !ta100) ta100 = new TA100::Observer (this);\n')
    result["clause.hpp"] = insert(result["clause.hpp"], '  int glue;\n',
        '  int glue;\n  uint16_t ta100_depth; // observation metadata, never read by search\n')
    result["clause.cpp"] = insert(result["clause.cpp"], '  c->glue = glue;\n',
        '  c->glue = glue;\n  c->ta100_depth = 0;\n')
    a = result["analyze.cpp"]
    a = insert(a, 'void Internal::bump_variable (int lit) {\n',
        'void Internal::bump_variable (int lit) {\n  if (ta100) ta100->bumped (lit);\n')
    a = insert(a, '\n  analyzed.push_back (lit);\n',
        '\n  if (ta100) ta100->analyzed_literal (lit);\n  analyzed.push_back (lit);\n', expected=2)
    a = insert(a, '  bump_clause (reason);\n',
        '  if (ta100) ta100->analyze_reason (reason);\n  bump_clause (reason);\n')
    a = insert(a, '  // First update moving averages of trail height at conflict.\n',
        '  if (ta100) ta100->begin_analysis ();\n\n  // First update moving averages of trail height at conflict.\n')
    a = insert(a, '  fpcc.minsize_sum += size;\n',
        '  fpcc.minsize_sum += size;\n  if (ta100) ta100->learned (glue, uip);\n')
    a = insert(a, '  Clause *driving_clause = new_driving_clause (glue, jump, driving);\n',
        '  Clause *driving_clause = new_driving_clause (glue, jump, driving);\n  if (ta100) ta100->driving (driving_clause);\n')
    anchor = '  return res;\n}\n\n/*------------------------------------------------------------------------*/\n\nvoid Internal::eagerly_subsume_recently_learned_clauses'
    a = insert(a, anchor, '  if (ta100) ta100->set_chrono (res > jump || opts.chronoalways);\n' + anchor)
    result["analyze.cpp"] = a
    result["minimize.cpp"] = insert(result["minimize.cpp"],
        '  assert (v.reason != external_reason);\n  const const_literal_iterator end = v.reason->end ();',
        '  assert (v.reason != external_reason);\n  if (ta100) ta100->dependency (v.reason);\n  const const_literal_iterator end = v.reason->end ();')
    result["shrink.cpp"] = insert(result["shrink.cpp"],
        '    const Clause &c = *v.reason;\n', '    if (ta100) ta100->dependency (v.reason);\n    const Clause &c = *v.reason;\n')
    result["backtrack.cpp"] = insert(result["backtrack.cpp"], '  set_val (lit, 0);\n',
        '  if (ta100) ta100->unassigned (lit);\n  set_val (lit, 0);\n')
    result["backtrack.cpp"] = insert(result["backtrack.cpp"], '  stats.backtracks++;\n',
        '  stats.backtracks++;\n  if (ta100) ta100->begin_backtrack ();\n')
    result["backtrack.cpp"] = insert(result["backtrack.cpp"], '  assert (num_assigned == trail.size ());\n}\n',
        '  assert (num_assigned == trail.size ());\n  if (ta100) ta100->end_backtrack ();\n}\n')
    result["propagate.cpp"] = insert(result["propagate.cpp"], '  trail.push_back (lit);\n',
        '  trail.push_back (lit);\n  if (ta100) ta100->assigned (lit, reason);\n')
    result["propagate.cpp"] = insert(result["propagate.cpp"], '  search_assign (lit, c);\n',
        '  if (ta100) ta100->before_driving_assignment (c);\n  search_assign (lit, c);\n'
        '  if (ta100) ta100->after_driving_assignment (c);\n')
    result["propagate.cpp"] = insert(result["propagate.cpp"], '      const signed char b = val (w.blit);\n',
        '      const signed char b = val (w.blit);\n      if (ta100) ta100->watch (b > 0);\n')
    result["decide.cpp"] = insert(result["decide.cpp"], '        fpcc.dec_free++;\n',
        '        fpcc.dec_free++;\n        if (ta100) ta100->free_decision (decision);\n')
    result["restart.cpp"] = insert(result["restart.cpp"], '  backtrack (reuse_trail ());\n',
        '  if (ta100) ta100->before_restart ();\n  backtrack (reuse_trail ());\n  if (ta100) ta100->after_restart ();\n')
    f = insert(result["fpcontrol.cpp"], 'ta-probe-v1', 'ta100-observer-v1')
    old = ('      fprintf (log, ",\\"learned\\":%" PRId64\n'
           '                    ",\\"process_cpu_s\\":%.9f",\n'
           '               now.learned, absolute_process_time ());\n')
    f = insert(f, old, '      fprintf (log, ",\\"learned\\":%" PRId64, now.learned);\n')
    f = insert(f, '      write_features (features_cp);\n      fputs ("}\\n", log);',
        '      write_features (features_cp);\n      if (I->ta100) I->ta100->write (log);\n'
        '      fprintf (log, ",\\"process_cpu_s\\":%.9f", absolute_process_time ());\n'
        '      fputs ("}\\n", log);')
    result["fpcontrol.cpp"] = f
    changed = {name: text for name, text in result.items() if text != original[name]}
    for name in ("ta100_observer.cpp", "ta100_observer.hpp"):
        changed[name] = (ASSETS / name).read_text()
    return changed, bindings


def apply_observer(source_root, output_root):
    source_root, output_root = Path(source_root).resolve(), Path(output_root).resolve()
    if source_root == output_root or output_root.exists() or source_root in output_root.parents:
        raise ValueError("new isolated observer root must not exist or be inside original source")
    changed, base = render(source_root / "src")
    shutil.copytree(source_root, output_root, symlinks=True)
    for name, text in changed.items():
        (output_root / "src" / name).write_text(text)
    files = {name: sha(output_root / "src" / name) for name in sorted(changed)}
    all_source_files = {str(path.relative_to(output_root / "src")): sha(path)
                        for path in sorted((output_root / "src").rglob("*"))
                        if path.is_file() and path.suffix in (".cpp", ".hpp", ".h", ".c")}
    receipt = {"schema": "ta100.observer_source_bundle.v1", "observer": "ta100-observer-v1",
               "base_files": base, "files": files,
               "all_source_files": all_source_files,
               "observer_source_sha256": hashlib.sha256(canonical(all_source_files)).hexdigest(),
               "patcher_sha256": sha(__file__), "source_only_no_build": True,
               "output_root": str(output_root)}
    (output_root / "TA100_SOURCE_BINDINGS.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(apply_observer(args.source_root, args.output_root), sort_keys=True))


if __name__ == "__main__":
    main()
