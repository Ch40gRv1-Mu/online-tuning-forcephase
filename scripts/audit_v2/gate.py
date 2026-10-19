"""Strict data gate for the audit v2 (see docs/CORRECTION_PROTOCOL.md §4).

Shared by scripts/audit_v2/integrity.py, scripts/audit_v2/m3_build_strict.py and
tests/audit_v2/test_gate.py.  Pure functions over already-loaded records so
that the regression tests can feed hand-made records.

Categories for a same-state pair (one row per instance, base, alt, K, track,
direction):
  valid_pair            label-producing pair (prefix digest equal, exactly one
                        schedule switch at that checkpoint, right action/track)
  solved_before_K       base telemetry complete, no checkpoint covering K, base solved
  budget_before_K       base telemetry complete, no checkpoint covering K, base timeout
  censored_unmatched    base reached K, alt did not reach the checkpoint, both timeout
  (appendix A: a run SIGKILLed after the CPU cutoff may lack only the 'final'
  telemetry record; its earlier records are used, see killed_after_cutoff())
  base_missing, alt_missing, telemetry_missing, telemetry_corrupt,
  telemetry_incomplete, digest_mismatch, switch_error, direction_error,
  duplicate_key, unexpected_alt                       -> data errors
"""

import gzip
import json
import os

LEGAL = ("valid_pair", "solved_before_K", "budget_before_K")
EXCEPTION = ("censored_unmatched",)
ERRORS = ("base_missing", "alt_missing", "telemetry_missing", "telemetry_corrupt", "telemetry_incomplete",
          "digest_mismatch", "switch_error", "direction_error", "duplicate_key", "unexpected_alt")
TERMINAL = ("solved", "timeout")


class GateError(RuntimeError):
    pass


def load_telemetry(path):
    """Return (records, problem) where problem is None or one of
    telemetry_missing / telemetry_corrupt / telemetry_incomplete."""
    if path is None or not os.path.exists(path):
        return [], "telemetry_missing"
    recs = []
    try:
        opener = gzip.open if path.endswith(".gz") else open
        with opener(path, "rt") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    return recs, "telemetry_corrupt"
    except (OSError, EOFError):
        return recs, "telemetry_corrupt"
    if not recs or recs[0].get("type") != "header":
        return recs, "telemetry_corrupt"
    if not any(r.get("type") == "final" for r in recs):
        return recs, "telemetry_incomplete"
    return recs, None


def checkpoint_at(recs, K):
    for r in recs:
        if r.get("type") == "checkpoint" and r["crossed"][0] <= K <= r["crossed"][1]:
            return r
    return None


def header(recs):
    return recs[0] if recs and recs[0].get("type") == "header" else {}


def final(recs):
    for r in reversed(recs):
        if r.get("type") == "final":
            return r
    return None


def killed_after_cutoff(run, T=300.0):
    """Protocol appendix A: SIGKILLed after the CPU cutoff (telemetry lacks only 'final')."""
    return (run is not None and run.get("status") == "timeout" and run.get("terminated_by") == "cpu"
            and run.get("exit_code") == -9 and (run.get("cpu") or 0) >= T)


def _accept(run, tel):
    """Return the telemetry problem after applying appendix A, plus a flag."""
    recs, problem = tel
    if problem == "telemetry_incomplete" and killed_after_cutoff(run) and recs and recs[0].get("type") == "header":
        return None, True
    return problem, False


def classify_pair(base, base_tel, alt, alt_tel, K, expect_action, expect_track):
    """Classify one same-state pair.

    base / alt: run summaries with at least 'status' (or None if missing);
    base_tel / alt_tel: (records, problem) from load_telemetry, or None if no
    alt run is planned for this instance.  expect_action: action name after
    the switch ('NEGATIVE' or 'NATIVE'); expect_track: 'C' or 'P'.
    Returns (category, details dict).
    """
    if base is None:
        return "base_missing", {}
    recs = base_tel[0]
    problem, base_killed = _accept(base, base_tel)
    if problem:
        return problem, {"side": "base"}
    notes = {"base_killed_after_cutoff": True} if base_killed else {}
    if base["status"] not in TERMINAL:
        return "telemetry_incomplete", {"side": "base", "status": base["status"]}
    cp = checkpoint_at(recs, K)
    if cp is None:
        if alt is not None:
            return "unexpected_alt", {"reason": "alt run exists although base has no decision point"}
        return ("solved_before_K" if base["status"] == "solved" else "budget_before_K"), notes
    if alt is None or alt_tel is None:
        return "alt_missing", {}
    arecs = alt_tel[0]
    aproblem, alt_killed = _accept(alt, alt_tel)
    if aproblem:
        return aproblem, {"side": "alt"}
    if alt_killed:
        notes["alt_killed_after_cutoff"] = True
    if alt["status"] not in TERMINAL:
        return "telemetry_incomplete", {"side": "alt", "status": alt["status"]}
    acp = checkpoint_at(arecs, K)
    switches = [r for r in arecs if r.get("type") == "switch"]
    fin = final(arecs)
    if acp is None:
        if base["status"] == "timeout" and alt["status"] == "timeout" and not switches:
            return "censored_unmatched", dict(notes, base_cp_conflicts=cp["conflicts"], base_cp_time=cp["time"])
        return "switch_error", {"reason": "alt has no checkpoint at K"}
    if acp["digest"] != cp["digest"]:
        return "digest_mismatch", {"base": cp["digest"], "alt": acp["digest"]}
    h = header(arecs)
    if h.get("track") != expect_track:
        return "direction_error", {"reason": f"track {h.get('track')} != {expect_track}"}
    if len(switches) != 1 or (not alt_killed and (fin or {}).get("switches") != 1):
        return "switch_error", {"switch_records": len(switches), "final_switches": (fin or {}).get("switches")}
    s = switches[0]
    if s.get("reason") != "schedule" or s["conflicts"] != acp["conflicts"]:
        return "switch_error", {"reason": "switch not at the checkpoint restart", "switch": s.get("conflicts"),
                                "checkpoint": acp["conflicts"]}
    if s.get("action") != expect_action:
        return "direction_error", {"reason": f"switched to {s.get('action')} expected {expect_action}"}
    return "valid_pair", dict(notes, cp_conflicts=cp["conflicts"], cp_time=cp["time"], switch_conflicts=s["conflicts"])


def enforce(categories, allow=EXCEPTION):
    """Raise GateError if any category is a data error (not legal, not allowed)."""
    bad = {}
    for c in categories:
        if c not in LEGAL and c not in allow:
            bad[c] = bad.get(c, 0) + 1
    if bad:
        raise GateError(f"data gate failed: {bad}")
