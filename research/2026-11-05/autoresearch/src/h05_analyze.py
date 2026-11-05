"""H05 relative traces and cheap gating; all choices train-family-only."""
from pathlib import Path
import hashlib,json,time,sys
import numpy as np
from simple_selection import ROOT,SOURCE,load_data,save_csv
from gated_selection import evaluate

EXP=ROOT/'experiments/H05_relative_phase_response'
NAMES=[f'{c}_{k}_minus_D' for c in ('Fplus','Fminus') for k in ('log_conflicts','log_decisions','log_propagations','verified_solved')]

def main():
    begin=time.monotonic();out=EXP/'results'
    if (out/'analysis_receipt.json').exists():raise SystemExit('Preserving completed H05')
    raw=[json.loads(s) for s in (out/'features.jsonl').read_text().splitlines() if s]
    dpath=ROOT/'experiments/H04_short_original_D_trace/results/features.jsonl'
    old=[json.loads(s) for s in dpath.read_text().splitlines() if s]
    assert len(raw)==1200 and len(old)==600
    allrows=raw+old;by={(r['id'],r['config'],r['budget']):r for r in allrows};assert len(by)==1800
    data=load_data();labels,features,*_=data
    for r in allrows:
        assert r['input_sha256']==features[r['id']]['cnf_sha256']
        if r['available']:
            assert r['probe']['cpu_s']<=r['budget']+.05
            if r['probe']['status'] in ('SAT','UNSAT'):assert r['verification']['verified']
    baseoptions=[];summary=[]
    for budget in (.1,.3):
        X=[];available=[];cost=[];sizes=[];gatefees=[]
        for parent in labels:
            rr={c:by[(parent['id'],c,budget)] for c in ('D','Fplus','Fminus')};ok=all(r['available'] for r in rr.values())
            available.append(ok);cost.append(sum(r['feature_cpu_s'] for r in rr.values()))
            assert rr['Fplus']['file_bytes']==rr['Fminus']['file_bytes']
            sizes.append(rr['Fplus']['file_bytes']);gatefees.append(max(rr['Fplus']['charged_gate_cpu_s'],rr['Fminus']['charged_gate_cpu_s']))
            vals=[]
            for c in ('Fplus','Fminus'):
                for key in ('conflicts','decisions','propagations'):
                    vals.append(float(np.log1p(rr[c]['probe'][key])-np.log1p(rr['D']['probe'][key])) if ok else float('nan'))
                vals.append(int(rr[c]['verification']['verified'])-int(rr['D']['verification']['verified']) if ok else float('nan'))
            X.append(vals)
        baseoptions.append(dict(budget=budget,names=NAMES,X=np.array(X),available=np.array(available),charge=np.array(cost),bytes=np.array(sizes),gatefee=np.array(gatefees)))
        relevant=[r for r in allrows if r['budget']==budget]
        summary.append(dict(budget=budget,parents=300,cost_valid_joint_available=int(sum(available)),all_parent_joint_available=sum(all(by[(pid,c,budget)]['available'] for c in ('D','Fplus','Fminus')) for pid in {r['id'] for r in raw}),new_probe_cpu_s=sum(r['probe']['cpu_s'] for r in raw if r['budget']==budget),new_total_feature_cpu_s=sum(r['feature_cpu_s'] for r in raw if r['budget']==budget),all_config_feature_cpu_s=sum(r['feature_cpu_s'] for r in relevant),verified_solved=sum(r['verification']['verified'] for r in relevant)))
    metrics=[];predictions=[];rules=[];classes=[];candidates={}
    for path,charged in [('H05_relative_free',False),('H05_relative_measured',True)]:
        options=[dict(o,charge=o['charge'] if charged else np.zeros(len(labels)),gatefee=o['gatefee'] if charged else np.zeros(len(labels))) for o in baseoptions]
        m,p,r,cl,c=evaluate(path,options,data);metrics+=m;predictions+=p;rules+=r;classes+=cl;candidates[path]=c
    for name,rows in [('metrics.csv',metrics),('predictions.csv',predictions),('probe_summary.csv',summary),('class_metrics.csv',classes)]:save_csv(out/name,rows)
    (out/'fold_rules.json').write_text(json.dumps(rules,indent=2)+'\n')
    (out/'development_candidate.json').write_text(json.dumps(dict(role='EXPLORATORY_FULL_FIT_NOT_VALIDATION',rules=candidates),indent=2)+'\n')
    files=[SOURCE/'labels.csv',EXP/'protocol.md',out/'features.jsonl',dpath,Path(__file__),ROOT/'src/gated_selection.py',ROOT/'src/run_phase_traces.py',ROOT/'src/run_short_traces.py']
    receipt=dict(status='FORMAL_EXPLORATORY_ANALYSIS_COMPLETE',new_jobs=1200,reused_D_jobs=600,new_feature_cpu_s=sum(r['feature_cpu_s'] for r in raw),wall_s=time.monotonic()-begin,source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},python=sys.version,numpy=np.__version__,batch_warning='D cached from H04; phase probes new batch; interleaved confirmation required')
    (out/'analysis_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    lines=['# H05：相对phase响应与廉价门控','','同一300题探索；291成本有效题、69明确赢家。最多两特征两层：字节规模门控后使用一个相对响应阈值。全部训练选择在家族留出折内完成。','','|路径|成本比D|95%区间|明确题准确率|切换覆盖|切换精度|','|---|---:|---|---:|---:|---:|']
    for r in metrics:
        if r['cohort']=='combined300':
            precision='无切换' if r['switch_accuracy'] is None else f"{r['switch_accuracy']:.1%}"
            lines.append(f"|{r['path']}|{r['cost_ratio']:.4f}|[{r['cost_ratio_ci_low']:.4f},{r['cost_ratio_ci_high']:.4f}]|{r['accuracy']:.1%}|{r['switch_coverage']:.1%}|{precision}|")
    lines+=['',f"新增1200探测，新增特征/验证CPU {receipt['new_feature_cpu_s']:.3f}秒；复用D的600次科研测量，但部署成本照计。",'', '收费路径按门控触发实际收取三个配置的探测/验证费用，门外仍收取至少1ms的stat开销。缺失轨迹在门内照计失败成本并回退D。免费结果仅是信号上界。', '', 'D来自前一批，F+/F−为本批，存在跨批次噪声；新题与交织重复确认尚未完成，因此不能称稳定部署结果。全部每类覆盖/精度和折规则保留。']
    (EXP/'analysis.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(receipt=receipt,summary=summary,metrics=[r for r in metrics if r['cohort']=='combined300'],candidates=candidates),ensure_ascii=False))

if __name__=='__main__':main()
