"""Independent LPN-semantics check of every SAT answer in an experiment ledger:
decode e from the witness and require wt(e) <= t and y+e in colspace(A).
Also flags UNSAT on planted instances (planted instances are SAT by
construction). Must run BEFORE verify_runs.py, which strips witnesses.

Usage: python3 scripts/lpn_check.py --exp lpn_dry
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fplib  # noqa: E402
import lpn_gen as L  # noqa: E402



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True)
    a = ap.parse_args()
    d = fplib.RESULTS / a.exp
    latest = {}
    for l in open(d / "runs.jsonl"):
        r = json.loads(l)
        r.setdefault("attempt", 1)
        latest[r["run_id"]] = r
    out, bad = [], []
    for r in latest.values():
        vkey = f"{r['run_id']}#a{r['attempt']}"
        meta = json.loads((L.LPN_DIR / f"{r['hash']}.json").read_text())
        rec = {"run_id": r["run_id"], "vkey": vkey, "status": r["status"]}
        if r["status"] == "SAT":
            model = fplib.parse_witness(Path(r["log"]).read_text(errors="replace"))
            if not model:
                rec["semantic"] = "NO_WITNESS"
            else:
                ok, sol = L.check_semantics(meta, model)
                rec.update({"semantic": "LPN_OK" if ok else "LPN_INVALID", "wt_e": sol["e"].bit_count(),
                            "wt_s": None if sol["s"] is None else sol["s"].bit_count(),
                            "equals_planted": meta["e"] is not None and sol["e"] == meta["e"]})
        elif r["status"] == "UNSAT" and meta["kind"] == "planted":
            rec["semantic"] = "WRONG_UNSAT_ON_PLANTED"
        else:
            continue
        if rec["semantic"] != "LPN_OK":
            bad.append(rec)
        out.append(rec)
    with open(d / "lpn_semantic.jsonl", "w") as f:
        for rec in out:
            f.write(json.dumps(rec) + "\n")
    print(f"{len(out)} answers checked; problems: {bad if bad else 'none'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
