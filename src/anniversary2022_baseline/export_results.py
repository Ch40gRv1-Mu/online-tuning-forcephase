import argparse
import io
import json
import tarfile
from pathlib import Path
from .common import read, sha


def export(root,out,require_complete=False):
    root,out=Path(root),Path(out)
    if out.exists():raise ValueError("immutable export already exists")
    status=read(root/"progress.json")
    if require_complete and status["status"]!="COMPLETE_VALID_MATRIX":raise ValueError("matrix is incomplete or invalid")
    include=[]
    for p in root.rglob("*"):
        if not p.is_file() or "cache" in p.relative_to(root).parts:continue
        if p.suffix in {".lrat",".sqlite",".lock"} or p.name.startswith("queue.sqlite"):continue
        if p.suffix in {".json",".jsonl",".csv",".log",".gz",".png",".pdf",".html"}:include.append(p)
    manifest={"status":status,"files":[{"path":str(p.relative_to(root)),"sha256":sha(p)} for p in sorted(include)]}
    out.parent.mkdir(parents=True,exist_ok=True);temporary=out.with_suffix(".part")
    with tarfile.open(temporary,"w:gz") as tf:
        for p in sorted(include):tf.add(p,arcname=str(p.relative_to(root)))
        b=(json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode();info=tarfile.TarInfo("MANIFEST.json");info.size=len(b);tf.addfile(info,io.BytesIO(b))
    temporary.replace(out)
    return {"path":str(out),"sha256":sha(out),"files":len(include),"bytes":out.stat().st_size}


def main():
    p=argparse.ArgumentParser();p.add_argument("--root",required=True);p.add_argument("--out",required=True)
    p.add_argument("--require-complete",action="store_true");a=p.parse_args();print(export(a.root,a.out,a.require_complete))


if __name__=="__main__":main()
