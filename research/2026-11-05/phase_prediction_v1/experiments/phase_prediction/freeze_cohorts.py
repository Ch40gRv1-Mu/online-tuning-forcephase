"""Identity-only GBD equivalence/size audit and frozen, outcome-blind cohorts.

Never reads family, filenames, application names, or GBD result columns.
"""

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


def read(path):
    return list(csv.DictReader(path.open()))


def write(path, rows, fields):
    with path.open("w", newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--meta",type=Path,required=True)
    p.add_argument("--base",type=Path,required=True)
    a=p.parse_args();out=a.out
    tests=read(out/"test_candidates.csv");dev=read(out/"development_candidates.csv")
    prior={r["hash"] for r in read(out/"exposed_identifiers.csv")}
    wanted=prior|{r["hash"] for r in tests+dev}
    meta=sqlite3.connect(f"file:{a.meta.resolve()}?mode=ro",uri=True)
    base=sqlite3.connect(f"file:{a.base.resolve()}?mode=ro",uri=True)
    iso={};sizes={};hs=sorted(wanted)
    for i in range(0,len(hs),400):
        block=hs[i:i+400];marks=",".join("?" for _ in block)
        for h,value in meta.execute(f"select hash,isohash from features where hash in ({marks})",block):
            if value and str(value).lower() not in {"none","unknown","-"}:iso[h]=str(value)
        for h,n,m,b in base.execute(f"select hash,variables,clauses,bytes from features where hash in ({marks})",block):
            if n is not None and m is not None and b is not None:sizes[h]=(int(n),int(m),int(b))
    protected_iso={iso[r["hash"]] for r in tests if r["hash"] in iso}
    prior_iso={iso[h] for h in prior if h in iso}
    dev_groups=defaultdict(list);excluded=[]
    for r in dev:
        h=r["hash"]
        if h not in iso or h not in sizes:
            excluded.append({"hash":h,"reason":"metadata_or_isohash_missing"});continue
        if iso[h] in protected_iso:
            excluded.append({"hash":h,"reason":"equivalent_to_protected_test_candidate"});continue
        dev_groups[iso[h]].append(h)
    representatives=[min(v) for v in dev_groups.values()]
    def order(h):return hashlib.sha256(("phase-prediction-v1-20261103:"+h).encode()).hexdigest()
    representatives.sort(key=order)
    n=len(representatives);fit_n=n*3//5;feedback_n=n//5
    frozen=[]
    for index,h in enumerate(representatives):
        role="development_fit" if index<fit_n else "development_feedback" if index<fit_n+feedback_n else "development_gate"
        nv,nc,nb=sizes[h]
        frozen.append({"hash":h,"url":f"https://benchmark-database.de/file/{h}","isohash":iso[h],
                       "role":role,"variables":nv,"clauses":nc,"bytes":nb,"equivalence_group_size":len(dev_groups[iso[h]])})
    fields=["hash","url","isohash","role","variables","clauses","bytes","equivalence_group_size"]
    write(out/"development_frozen.csv",frozen,fields)
    write(out/"development_excluded.csv",excluded,["hash","reason"])
    pilot=[r for r in frozen if r["role"]=="development_fit" and r["bytes"]<=100000000 and r["variables"]<=5000000][:48]
    write(out/"pilot_frozen.csv",pilot,fields)
    test_groups=defaultdict(list);test_records=[]
    for r in tests:
        h=r["hash"]
        reason=""
        if h in prior:reason="exact_exposure"
        elif h not in iso:reason="missing_equivalence_metadata"
        elif iso[h] in prior_iso:reason="equivalent_to_exposed_identifier"
        if not reason:test_groups[iso[h]].append(h)
        test_records.append({"hash":h,"isohash":iso.get(h,""),"exclusion_reason":reason})
    clean_reps=[min(v) for v in test_groups.values()]
    clean_reps.sort(key=lambda h:hashlib.sha256(("phase-confirmation-v1-20261103:"+h).encode()).hexdigest())
    confirm=[]
    for h in clean_reps:
        if h not in sizes:continue
        nv,nc,nb=sizes[h]
        if nb>100000000 or nv>5000000:continue
        confirm.append({"hash":h,"url":f"https://benchmark-database.de/file/{h}","isohash":iso[h],
                        "role":"sealed_confirmation","variables":nv,"clauses":nc,"bytes":nb,
                        "equivalence_group_size":len(test_groups[iso[h]])})
        if len(confirm)==96:break
    write(out/"test_equivalence_audit.csv",test_records,["hash","isohash","exclusion_reason"])
    write(out/"confirmation_sealed.csv",confirm,fields)
    hashes={p.name:sha(p) for p in [out/"development_frozen.csv",out/"pilot_frozen.csv",out/"confirmation_sealed.csv"]}
    info={"feature_metadata_columns_used":["hash","isohash","variables","clauses","bytes"],
          "meta_sha256":sha(a.meta),"base_sha256":sha(a.base),"source_test_candidates":len(tests),
          "development_before_equivalence":len(dev),"development_after_equivalence":len(frozen),
          "development_excluded":len(excluded),"fit":fit_n,"feedback":feedback_n,"gate":n-fit_n-feedback_n,
          "pilot":len(pilot),"unexposed_test_equivalence_groups":len(clean_reps),"sealed_confirmation":len(confirm),
          "frozen_files_sha256":hashes,"status":"No new test performance was read; GBD isohash is a practical deduplication aid, not a full isomorphism proof."}
    (out/"cohort_freeze.json").write_text(json.dumps(info,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(info,ensure_ascii=False))


if __name__=="__main__":main()
