"""Compile and actually compare the new exact42 extractor on frozen large prefix32."""

import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .linear42_candidate import predict_vector
from .linear42_only_vector import linear42_vector
from .measure_large_linear42 import atomic,timer_for,wait4,CONFIG,MODEL
from .score_static_seed_agreement import load_views
from .structural_clusters import DATA,ROOT,load,read_csv


def run():
    start,cpu=time.monotonic(),time.process_time()
    usage=resource.getrusage(resource.RUSAGE_CHILDREN)
    child0=usage.ru_utime+usage.ru_stime
    out=DATA/"linear42_compact_prefix32_20261111"
    out.mkdir(exist_ok=False)
    work=ROOT/"work/native_linear42_compact_20261111"
    work.mkdir(exist_ok=True)
    native=work/"native_linear42"
    source=ROOT/"src/anniversary2022_baseline/native_linear42.cpp"
    vendor=ROOT/"src/anniversary2022_baseline/vendor_gbdc_base_9f3a418"
    command=["clang++","-std=c++17","-O3","-I"+str(vendor),
        "-I"+str(ROOT/"src/anniversary2022_baseline/vendor_libarchive_headers_3_7_7"),
        str(source),str(vendor/"src/util/CaptureDistribution.cc"),"-larchive","-o",str(native)]
    completed=[]
    try:
        tick=time.monotonic()
        result=subprocess.run(command,capture_output=True,text=True,timeout=120)
        atomic(out/"build.json",{"command":command,"exit":result.returncode,"stderr":result.stderr,"wall_s":time.monotonic()-tick})
        if result.returncode: raise ValueError("compact42 build failed")
        binary_sha=sha(native)
        original=DATA/"linear42_large_cost_20261111"
        old_prefix=json.loads((original/"prefix_32.json").read_text())
        assert old_prefix["status"]=="complete_prefix" and old_prefix["through"]==32
        rows=read_csv(CONFIG/"manifest.csv")[:32]
        keys=load()[0];x,valid=load_views(keys)[0]["linear42"]
        assert valid.all()
        references={k:v.astype(np.float32) for k,v in zip(keys,x)}
        old_payload=joblib.load(MODEL)
        payload={**old_payload,"native_binary_sha256":binary_sha,"native_schema":"linear42.rawstats.v1"}
        model=out/"model.joblib"
        joblib.dump(payload,model,compress=3)
        policy=json.loads((MODEL.parent/"policy.json").read_text())
        policy.update(schema="forcephase.linear42.min3.compact.v1",model_file="model.joblib",
            model_sha256=sha(model),native_binary_sha256=binary_sha,original_model_sha256=sha(MODEL),
            model_weights_retrained=False,extraction="Single-pass exact42 only, upstream quirks retained",
            claim="Candidate input/cost experiment only; no new prediction accuracy or independent confirmation")
        atomic(out/"policy.json",policy)
        with threadpool_limits(limits=1):
            for row in rows:
                key=row["instance_key"]
                old=json.loads((original/"records"/(key+".json")).read_text())
                assert old["identity"]["verified"]
                path=Path(old["download"]["path"])
                assert sha(path)==old["download"]["wire_sha256"]
                tick=time.thread_time();wall=time.monotonic()
                process=subprocess.Popen([str(native),str(path)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                timer=timer_for(process,14)
                try:
                    text=process.stdout.read(1000001);process.stdout.close()
                    if len(text)>1000000: os.kill(process.pid,signal.SIGKILL)
                    code,child,rss=wait4(process)
                finally: timer.cancel()
                wrapper=time.thread_time()-tick
                rec={"instance_key":key,"ordinal":int(row["ordinal"]),"native_exit":code,"native_CPU_s":child,
                    "wrapper_CPU_s":wrapper,"native_wall_s":time.monotonic()-wall,"native_maxrss":rss,
                    "raw_sha256":old["identity"]["raw_sha256"],"wire_sha256":old["download"]["wire_sha256"],
                    "original_acquisition_CPU_s":old["acquisition_CPU_s"],"original_native_exit":old["native"]["native_exit"],
                    "status":"native_error_D_fallback","action":"D","acquisition_CPU_s":child+wrapper}
                if code==0:
                    f=json.loads(text)["features"]
                    tick=time.thread_time();vector=linear42_vector(f);rec["acquisition_CPU_s"]+=time.thread_time()-tick
                    rec["model_input_float32_match"]=bool(np.array_equal(vector.astype(np.float32),references[key]))
                    if not rec["model_input_float32_match"]:
                        atomic(out/"mismatch.json",{**rec,"features":f,"vector":vector.tolist(),"reference":references[key].tolist()})
                        raise ValueError("compact extraction changed a trained42-feature input")
                    tick=time.thread_time();action,gain=predict_vector(payload,vector)
                    rec["decision_CPU_s"]=time.thread_time()-tick
                    assert action==predict_vector(old_payload,references[key])[0]
                    rec.update(status="ok",action=("D","Fplus","Fminus")[action],min_predicted_PAR2_savings=gain.tolist(),features=f)
                atomic(out/"records"/(key+".json"),rec)
                completed.append(rec)
                print(f"COMPACT {len(completed)}/32: {rec['status']}, new={rec['acquisition_CPU_s']:.4f}, old={old['acquisition_CPU_s']:.4f}CPU_s",flush=True)
        old_fees=np.array([r["original_acquisition_CPU_s"] for r in completed])
        fees=np.array([r["acquisition_CPU_s"] for r in completed])
        successes=sum(r["status"]=="ok" for r in completed)
        allowed=successes>=old_prefix["native_ok"] and fees.sum()<old_fees.sum() and all(r.get("model_input_float32_match",True) for r in completed)
        atomic(out/"summary.json",{"status":"complete","parents":32,"sample":"Same frozen count-selected first32, unchanged inputs; no outcome selection",
            "successes":successes,"native_D_fallbacks":32-successes,"original_successes":old_prefix["native_ok"],
            "original_acquisition_CPU_s":float(old_fees.sum()),"compact_acquisition_CPU_s":float(fees.sum()),
            "compact_fee_quantiles_s":np.quantile(fees,[.5,.9,.99,1]).tolist(),"cost_reduction_pct":float(100*(1-fees.sum()/old_fees.sum())),
            "predeclared_cost_interface_continuation_passed":bool(allowed),"model_fits":0,"new_solver_calls":0,
            "native_sha256":binary_sha,"model_sha256":sha(model),"source_sha256":sha(__file__),
            "native_source_sha256":sha(source),"vectorizer_sha256":sha(ROOT/"src/anniversary2022_baseline/linear42_only_vector.py"),
            "scope":"Fixed32 native input and real cost comparison; not whole4719/1876 compatibility, predictive confirmation or same-machine deployment"})
    except BaseException as exc:
        atomic(out/"failure.json",{"status":"failed","error":repr(exc),"completed":len(completed)})
        raise
    finally:
        usage=resource.getrusage(resource.RUSAGE_CHILDREN)
        atomic(out/"resources.json",{"physical_parent_CPU_s":time.process_time()-cpu,
            "physical_child_CPU_s":usage.ru_utime+usage.ru_stime-child0,"wall_s":time.monotonic()-start,
            "new_solver_calls":0,"compilation_included":True,"model_retraining":False})


if __name__=="__main__": run()
