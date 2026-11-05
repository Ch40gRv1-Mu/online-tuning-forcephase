"""H02a/H02b fixed formal exploratory analysis; no retraining on held-out families."""
from pathlib import Path
import hashlib,json,time,sys
import numpy as np
from simple_selection import ROOT,SOURCE,load_data,evaluate,save_csv

EXP=ROOT/'experiments/H02_signed_clause_asymmetry'

def main():
    begin=time.monotonic();out=EXP/'results';out.mkdir(exist_ok=True)
    if (out/'analysis_receipt.json').exists():raise SystemExit('Existing analysis is immutable')
    raw=[json.loads(s) for s in (out/'features.jsonl').read_text().splitlines() if s]
    assert len(raw)==300 and len({r['id'] for r in raw})==300
    by={r['id']:r for r in raw};data=load_data();labels,features,*_=data
    # Checking matched counts and fractions is part of the formal extraction result validation.
    for r in raw:
        f=features[r['id']];assert r['input_sha256']==f['cnf_sha256']
        if r['available']:
            assert r['empty_clauses']==0
            assert r['clauses']==int(f['clauses']) and r['literals']==int(f['literals'])
            for k in ('positive_only_clause_fraction','negative_only_clause_fraction'):
                assert abs(r[k]-float(f[k]))<1e-12,(r['id'],k,r[k],f[k])
    names=['positive_only_clause_fraction','negative_only_clause_fraction','signed_clause_bias']
    X=np.array([[float(features[r['id']]['positive_only_clause_fraction']),float(features[r['id']]['negative_only_clause_fraction']),float(features[r['id']]['positive_only_clause_fraction'])-float(features[r['id']]['negative_only_clause_fraction'])] for r in labels])
    available=np.array([by[r['id']]['available'] for r in labels],dtype=bool)
    Z=np.array([[by[r['id']].get(k,float('nan')) for k in names+['weighted_signed_clause_bias']] for r in labels])
    descriptor=np.array([by[r['id']]['cpu_s'] for r in labels])
    metrics=[];predictions=[];rules=[];candidates={}
    for name,matrix,cols,ok,cost in [('H02a_unweighted_free',X,names,np.ones(len(labels),dtype=bool),np.zeros(len(labels))),('H02b_all_four_free',Z,names+['weighted_signed_clause_bias'],available,np.zeros(len(labels))),('H02b_all_four_measured',Z,names+['weighted_signed_clause_bias'],available,descriptor)]:
        m,p,r,c=evaluate(name,matrix,cols,ok,cost,data)
        metrics+=m;predictions+=p;rules+=r;candidates[name]=c
    save_csv(out/'metrics.csv',metrics);save_csv(out/'predictions.csv',predictions)
    (out/'fold_rules.json').write_text(json.dumps(rules,indent=2)+'\n')
    (out/'development_candidate.json').write_text(json.dumps(dict(role='EXPLORATORY_FULL_FIT_NOT_VALIDATION',rules=candidates),indent=2)+'\n')
    files=[SOURCE/'labels.csv',SOURCE/'parent_features.csv',EXP/'protocol.md',out/'features.jsonl',Path(__file__),ROOT/'src/simple_selection.py']
    receipt=dict(status='FORMAL_EXPLORATORY_ANALYSIS_COMPLETE',input_counts_checked=True,fraction_agreement_checked=True,available_parents=sum(r['available'] for r in raw),parents=300,measured_extraction_cpu_s=sum(r['cpu_s'] for r in raw),wall_s=time.monotonic()-begin,source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},python=sys.version,numpy=np.__version__)
    (out/'analysis_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    lines=['# H02：符号不对称的探索结果','','同一300父题，仅用于探索。291题有有效配置成本、69题有明确赢家。所有区间按家族聚类，2000次bootstrap。','','|路径|成本比D|95%区间|准确率|切换覆盖|切换精度|','|---|---:|---|---:|---:|---:|']
    for r in metrics:
        if r['cohort']=='combined300':
            precision='无切换' if r['switch_accuracy'] is None else f"{r['switch_accuracy']:.1%}"
            lines.append(f"|{r['path']}|{r['cost_ratio']:.4f}|[{r['cost_ratio_ci_low']:.4f},{r['cost_ratio_ci_high']:.4f}]|{r['accuracy']:.1%}|{r['switch_coverage']:.1%}|{precision}|")
    lines+=['',f"正式提取成功 {receipt['available_parents']}/300；累计提取CPU {receipt['measured_extraction_cpu_s']:.3f}秒。全部身份与原始clause/literal计数、纯正/纯负子句比例相符。",'', '免费路径仅表征信号上界；收费路径使用本次解析、身份校验、子进程与特征计算的实测CPU，未隐藏超时或缺失特征的回退行为。已有parent测量未重跑，结果不是新题确认。', '', '完整开发集候选见development_candidate.json；候选在训练集上的表现不能当验证。外层留出成本与覆盖达不到工作流门槛时，不进入新数据确认。']
    (EXP/'analysis.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(receipt=receipt,metrics=[r for r in metrics if r['cohort']=='combined300'],candidates=candidates),ensure_ascii=False))

if __name__=='__main__':main()
