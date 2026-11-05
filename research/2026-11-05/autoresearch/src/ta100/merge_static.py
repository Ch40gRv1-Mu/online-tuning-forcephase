#!/usr/bin/env python3
"""Merge a complete SHA-bound192 public static group, without TA labels/scoring."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path

import static_worker as worker

TERMINAL={"COMPLETE","TIMEOUT","RESOURCE_LIMIT","FAILED","RESOURCE_UNAVAILABLE"}


def save_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x") as out:
        out.write(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+"\n")


def merge(manifest_path,result_dirs,*,expected_count=192):
    manifest_path=Path(manifest_path)
    manifest=json.loads(manifest_path.read_text())
    if manifest.get("profile")!=worker.PROFILE or set(manifest.get("method",{}))!=worker.METHOD_FIELDS:
        raise ValueError("collection profile/full source method differs from frozen static contract")
    tasks=[worker.normalize_task(task,manifest) for task in manifest["tasks"]]
    bykey={t["task_key"]:t for t in tasks}
    if len(tasks)!=expected_count or len(bykey)!=expected_count or len({t["instance_id"] for t in tasks})!=expected_count:
        raise ValueError("original manifest must declare the complete unique eligible192")
    roles=dict(collections.Counter(t["role"] for t in tasks))
    if expected_count==192 and roles!={"development_fit":144,"development_feedback":48}:
        raise ValueError("eligible population must retain frozen144fit/48feedback roles")
    columns=manifest["feature_keys"]
    if any(not worker.FEATURE_NAME.fullmatch(c) for c in columns) or len(set(columns))!=len(columns):
        raise ValueError("invalid frozen columns")
    selected={};equivalent=collections.defaultdict(list)
    for directory in result_dirs:
        for path in sorted(Path(directory).glob("*.json")):
            task=bykey.get(path.stem)
            if task is None:raise ValueError("receipt directory contains an out-of-manifest task")
            record=worker.reusable(path,task,manifest)
            if record.get("instance_id")!=task["instance_id"] or record.get("id")!=task["instance_id"]:
                raise ValueError("receipt input association differs from frozen task")
            if record.get("status") not in TERMINAL:
                raise ValueError("nonterminal static group receipt")
            if not isinstance(record.get("blocks"),dict) or set(record["blocks"])!=set(columns):
                raise ValueError("all terminal blocks require the full frozen schema")
            for cost in ("feature_cpu_s","feature_wall_s","preparation_cpu_s","preparation_wall_s","controller_cpu_s","total_accounted_cpu_s"):
                value=record.get(cost)
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                    raise ValueError("missing/invalid actual group cost: "+cost)
            total=sum(record[k] for k in ("feature_cpu_s","preparation_cpu_s","controller_cpu_s"))
            if not math.isclose(total,record["total_accounted_cpu_s"],rel_tol=1e-10,abs_tol=1e-8):
                raise ValueError("group costs do not reconcile")
            if record["status"]=="COMPLETE":
                if record.get("source_check")!="input_sha256_match":raise ValueError("complete vector lacks verified raw input")
                worker.validate_output({"schema":"ta100.static.v1","group":manifest["method"]["group"],
                    "features":record.get("features"),"blocks":record.get("blocks"),
                    "metadata":record.get("extractor_metadata")},manifest,task)
            elif set(record.get("features",{}))!=set(columns) or any(value is not None for value in record["features"].values()):
                raise ValueError("failed/missing group must retain nulls for all registered columns")
            file_sha=worker.base.sha(path)
            if task["task_key"] in selected:
                if selected[task["task_key"]][2]!=file_sha:
                    raise ValueError("multiple nonidentical measurements for one task; central recovery selection required")
            else:selected[task["task_key"]]=(record,path,file_sha)
            equivalent[task["task_key"]].append(str(path))
    if set(selected)!=set(bykey):
        raise ValueError("partial feature population; every original eligible task needs a terminal receipt")
    features={};index=[];statuses={};costs=collections.Counter()
    for task in tasks:
        record,path,file_sha=selected[task["task_key"]]
        features[task["instance_id"]]=record["features"]
        statuses[task["instance_id"]]={"status":record["status"],"role":record["role"],
            "blocks":{k:v.get("status") for k,v in record["blocks"].items()},"source_check":record.get("source_check")}
        index.append({"task_key":task["task_key"],"instance_id":task["instance_id"],"role":task["role"],
            "input_sha256":task["input_sha256"],"receipt_path":str(path),"receipt_file_sha256":file_sha,
            "receipt_content_sha256":record["receipt_content_sha256"],"equivalent_paths":equivalent[task["task_key"]]})
        for key in ("feature_cpu_s","preparation_cpu_s","controller_cpu_s","total_accounted_cpu_s"):costs[key]+=record[key]
    bindings={"base_manifest_sha256":manifest["public_manifest_sha256"],
        "source_sha256":manifest["method"]["extractor_source_sha256"],
        "collection_manifest_sha256":worker.base.sha(manifest_path),"method":manifest["method"],
        "profile":manifest["profile"],"table_builder_sha256":worker.base.sha(__file__),
        "worker_import_source_sha256":worker.base.sha(worker.__file__),
        "receipt_index_content_sha256":hashlib.sha256(worker.base.canonical(index)).hexdigest()}
    for key in ("base_manifest_sha256","source_sha256"):
        if not worker.base.SHA.fullmatch(str(bindings[key])):raise ValueError("required public/source binding missing")
    table={"schema":"ta100.feature_table.v1","complete":True,"columns":columns,
        "expected_instance_ids":[t["instance_id"] for t in tasks],"features":features,"bindings":bindings,
        "statuses":statuses,"physical_costs":dict(costs),"coverage":{key:sum(v[key] is not None for v in features.values()) for key in columns},
        "terminal_status_counts":dict(collections.Counter(s["status"] for s in statuses.values())),
        "role_counts":dict(collections.Counter(t["role"] for t in tasks)),"no_TA_labels_read":True}
    return table,{"schema":"ta100.static_receipt_index.v1","bindings":bindings,"records":index}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",required=True,type=Path)
    parser.add_argument("--result-dir",required=True,nargs="+",type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--index-output",required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists() or args.index_output.exists():raise FileExistsError("immutable merged artifact already exists")
    table,index=merge(args.manifest,args.result_dir)
    save_new(args.index_output,index);save_new(args.output,table)
    print(json.dumps({"output":str(args.output),"parents":len(table["features"]),"statuses":table["terminal_status_counts"],
        "physical_costs":table["physical_costs"],"coverage":table["coverage"]}))


if __name__=="__main__":main()
