"""Frozen H04 variable-budget family-held-out evaluation."""
from pathlib import Path
import hashlib,json,time,sys
import numpy as np
from simple_selection import ROOT,SOURCE,load_data,save_csv
from budgeted_selection import evaluate_options

EXP=ROOT/'experiments/H04_short_original_D_trace'
NAMES=['conflicts_per_cpu_s','decisions_per_cpu_s','propagations_per_cpu_s','conflicts_per_decision','verified_solved']

def main():
    begin=time.monotonic();out=EXP/'results'
    if (out/'analysis_receipt.json').exists():raise SystemExit('Preserving completed analysis')
    raw=[json.loads(s) for s in (out/'features.jsonl').read_text().splitlines() if s]
    assert len(raw)==600 and len({(r['id'],r['budget']) for r in raw})==600
    data=load_data();labels,features,*_=data;by={(r['id'],r['budget']):r for r in raw}
    summary=[]
    for budget in (.1,.3):
        rs=[r for r in raw if r['budget']==budget]
        for r in rs:
            assert r['config']=='D' and r['input_sha256']==features[r['id']]['cnf_sha256']
            if r['available']:
                assert r['probe']['cpu_s']<=budget+.05
                assert all(k in r['probe'] for k in ('conflicts','decisions','propagations'))
                if r['probe']['status'] in ('SAT','UNSAT'):assert r['verification']['verified']
        parsed=[r for r in rs if 'decisions' in r['probe']]
        summary.append(dict(budget=budget,parents=len(rs),available=sum(r['available'] for r in rs),verified_solved=sum(r['verification']['verified'] for r in rs),parsed_stats=len(parsed),zero_decisions=sum(r['probe']['decisions']==0 for r in parsed),zero_decision_fraction=sum(r['probe']['decisions']==0 for r in parsed)/len(parsed) if parsed else None,probe_cpu_s=sum(r['probe']['cpu_s'] for r in rs),all_feature_cpu_s=sum(r['feature_cpu_s'] for r in rs),hard_killed=sum(r['probe']['hard_killed'] for r in rs),cpu_exceeds_target_plus_grace=sum(r['probe']['cpu_s']>budget+.05 for r in rs)))
    metrics=[];predictions=[];rules=[];candidates={}
    for path,charged in [('H04_trace_free',False),('H04_trace_measured',True)]:
        options=[]
        for budget in (.1,.3):
            rs=[by[(r['id'],budget)] for r in labels]
            options.append(dict(budget=budget,names=NAMES,X=np.array([[r.get('features',{}).get(k,float('nan')) for k in NAMES] for r in rs]),available=np.array([r['available'] for r in rs]),charge=np.array([r['feature_cpu_s'] if charged else 0. for r in rs])))
        m,p,r,c=evaluate_options(path,options,data);metrics+=m;predictions+=p;rules+=r;candidates[path]=c
    save_csv(out/'metrics.csv',metrics);save_csv(out/'predictions.csv',predictions);save_csv(out/'probe_summary.csv',summary)
    (out/'fold_rules.json').write_text(json.dumps(rules,indent=2)+'\n')
    (out/'development_candidate.json').write_text(json.dumps(dict(role='EXPLORATORY_FULL_FIT_NOT_VALIDATION',rules=candidates),indent=2)+'\n')
    files=[SOURCE/'labels.csv',SOURCE/'parent_features.csv',EXP/'protocol.md',out/'features.jsonl',Path(__file__),ROOT/'src/budgeted_selection.py',ROOT/'src/simple_selection.py',ROOT/'src/run_short_traces.py']
    receipt=dict(status='FORMAL_EXPLORATORY_ANALYSIS_COMPLETE',jobs=600,available=sum(r['available'] for r in raw),all_feature_cpu_s=sum(r['feature_cpu_s'] for r in raw),policy='probe_then_restart_selected_config_including_already_solved',wall_s=time.monotonic()-begin,source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},python=sys.version,numpy=np.__version__)
    (out/'analysis_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    lines=['# H04：极短原题D轨迹','','同一300题探索；291有效配置成本、69明确赢家。预算与阈值仅在训练家族内选择，留出家族不参与调参。','','|路径|成本比D|95%区间|明确题准确率|切换覆盖|切换精度|','|---|---:|---|---:|---:|---:|']
    for r in metrics:
        if r['cohort']=='combined300':
            precision='无切换' if r['switch_accuracy'] is None else f"{r['switch_accuracy']:.1%}"
            lines.append(f"|{r['path']}|{r['cost_ratio']:.4f}|[{r['cost_ratio_ci_low']:.4f},{r['cost_ratio_ci_high']:.4f}]|{r['accuracy']:.1%}|{r['switch_coverage']:.1%}|{precision}|")
    lines+=['',f"600个正式探测，可用{receipt['available']}；总特征/验证/监控CPU {receipt['all_feature_cpu_s']:.3f}秒。各预算零decision、超预算与硬杀情况见probe_summary.csv。",'', '计费路径包括输入hash、监控、solver、model/证明验证和失败成本；评价保守的探测后重新启动策略，未使用探测早停收益抵扣，且未把探测时间当作60秒完整运行。免费路径只是信号上界。已有基线未重跑。']
    (EXP/'analysis.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(receipt=receipt,summary=summary,metrics=[r for r in metrics if r['cohort']=='combined300'],candidates=candidates),ensure_ascii=False))

if __name__=='__main__':main()
