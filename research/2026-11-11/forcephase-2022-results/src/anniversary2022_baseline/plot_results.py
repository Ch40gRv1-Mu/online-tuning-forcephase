import argparse
import base64
import html
import itertools
import json
from pathlib import Path
from .common import ACTIONS, read, sha, write


def plot(snapshot):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    snapshot=Path(snapshot); summary=read(snapshot/"summary.json"); all_cases=read(snapshot/"instances.json")
    cases=[c for c in all_cases if set(c["outcomes"])==set(ACTIONS)]
    note=f'{summary["scope"]}: {len(cases)}/{summary["full_cohort"]} complete parent triads; T={summary["cutoff_s"]} CPU s'
    figures=[]; curves={}
    for metric,label in [("cpu_s","Solver CPU seconds"),("conflicts","Conflicts (solved within the CPU budget in the title)")]:
        fig,ax=plt.subplots(figsize=(7,4.5)); data={a:[] for a in ACTIONS};data["VBS"]=[]
        for c in cases:
            resolved=[]
            for a,r in c["outcomes"].items():
                if r["resolved"] and r[metric] is not None:
                    data[a].append(r[metric]);resolved.append(r[metric])
            if resolved:data["VBS"].append(min(resolved))
        for a,values in data.items():
            values=sorted(values)
            endpoint=summary["cutoff_s"] if metric=="cpu_s" else max([v for vv in data.values() for v in vv]+[1])
            ax.step([0,*values,endpoint],[0,*range(1,len(values)+1),len(values)],where="post",label=a)
        ax.set(xlabel=label,ylabel="Verified instances solved",title=note);ax.legend();ax.grid(alpha=.25)
        if metric=="cpu_s":ax.set_xlim(0,summary["cutoff_s"])
        else:ax.set_xscale("symlog",linthresh=1)
        ax.set_ylim(0,max(1,len(cases)));fig.tight_layout()
        name="cumulative_"+metric;fig.savefig(snapshot/(name+".png"),dpi=160);fig.savefig(snapshot/(name+".pdf"));plt.close(fig)
        figures.append(name);curves[metric]=data
        fig,axes=plt.subplots(1,3,figsize=(13,4))
        for ax,(a,b) in zip(axes,itertools.combinations(ACTIONS,2)):
            xy=[(c["outcomes"][a][metric],c["outcomes"][b][metric]) for c in cases
                if c["outcomes"][a]["resolved"] and c["outcomes"][b]["resolved"]
                and c["outcomes"][a][metric] is not None and c["outcomes"][b][metric] is not None]
            if xy:ax.scatter([x for x,y in xy],[y for x,y in xy],s=16)
            maximum=max([x for pair in xy for x in pair]+[.001 if metric=="cpu_s" else 1])*1.1
            for factor,style in [(1,"-"),(2,"--"),(10,":")]:
                ax.plot([0,maximum],[0,factor*maximum],style,color="gray",linewidth=.7)
                if factor>1:ax.plot([0,factor*maximum],[0,maximum],style,color="gray",linewidth=.7)
            threshold=.001 if metric=="cpu_s" else 1
            ax.set_xscale("symlog",linthresh=threshold);ax.set_yscale("symlog",linthresh=threshold)
            ax.set(xlim=(0,maximum),ylim=(0,maximum),xlabel=f"{a} {metric}",ylabel=f"{b} {metric}",title=f"Both solved: {len(xy)}/{len(cases)}")
        fig.suptitle(note+"; one-sided/unsolved retained in matrix.csv");fig.tight_layout()
        name="scatter_"+metric;fig.savefig(snapshot/(name+".png"),dpi=160);fig.savefig(snapshot/(name+".pdf"));plt.close(fig);figures.append(name)
    write(snapshot/"curve_data.json",curves)
    body="<html><meta charset='utf-8'><title>Force-phase baseline</title><h1>CaDiCaL three-action baseline</h1><p>"+html.escape(note)+"</p>"
    body+="<p>Time-VBS and conflict-VBS minimize different quantities. Timeout conflict counts are not solve costs. Scatter plots show both-solved pairs; missing and one-sided results remain in matrix.csv.</p>"
    for name in figures:
        encoded=base64.b64encode((snapshot/(name+".png")).read_bytes()).decode()
        body+='<img style="max-width:100%" src="data:image/png;base64,'+encoded+'">'
    body+="</html>";(snapshot/"baseline.html").write_text(body)
    write(snapshot/"plot_receipt.json",{"plotter_sha256":sha(Path(__file__)),"matplotlib":matplotlib.__version__,
        "source_summary_sha256":sha(snapshot/"summary.json"),"scope":summary["scope"],
        "scatter_scope":"both solved only; raw values and true 1x/2x/10x lines on symlog axes; other statuses retained in matrix.csv",
        "files":{p.name:sha(p) for p in snapshot.iterdir() if p.suffix in {".png",".pdf",".html"}}})
    return figures


def main():
    p=argparse.ArgumentParser();p.add_argument("--snapshot",required=True);a=p.parse_args();print(plot(a.snapshot))


if __name__=="__main__":main()
