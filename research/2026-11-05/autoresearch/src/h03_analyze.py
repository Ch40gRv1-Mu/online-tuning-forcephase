"""Formal H03 analysis with prior exact-UP state agreement as an input invariant."""
from pathlib import Path
import hashlib,json,time,sys
import numpy as np
from simple_selection import ROOT,SOURCE,load_data,evaluate,save_csv

EXP=ROOT/'experiments/H03_root_propagation_residual'
NAMES=['residual_active_variable_fraction','residual_clause_fraction','delta_binary_fraction','delta_negative_literal_fraction','residual_weighted_signed_clause_bias']

def main():
    begin=time.monotonic();out=EXP/'results';out.mkdir(exist_ok=True)
    if (out/'analysis_receipt.json').exists():raise SystemExit('Existing analysis is immutable')
    raw=[json.loads(s) for s in (out/'features.jsonl').read_text().splitlines() if s]
    assert len(raw)==300 and len({r['id'] for r in raw})==300
    previous={}
    for name in ('root_propagation.jsonl','reused_root_propagation.jsonl'):
        for s in (SOURCE/name).read_text().splitlines():
            r=json.loads(s);previous[r['parent']]=r
    assert len(previous)==300
    by={r['id']:r for r in raw};data=load_data();labels,features,*_=data
    checks=[]
    for r in raw:
        f=features[r['id']];assert r['input_sha256']==f['cnf_sha256']
        if 'root_conflict' in r:
            assert r['clauses']==int(f['clauses']) and r['literals']==int(f['literals'])
            prior=previous[r['id']]
            for k in ('root_assigned_variables','root_remaining_clauses','root_conflict'):
                assert r[k]==prior[k],(r['id'],k,r[k],prior[k])
            checks.append(r['id'])
    available=np.array([by[r['id']]['available'] and by[r['id']].get('usable_residual',False) for r in labels])
    X=np.array([[by[r['id']].get(k,float('nan')) for k in NAMES] for r in labels])
    descriptor=np.array([by[r['id']]['cpu_s'] for r in labels]);metrics=[];predictions=[];rules=[];candidates={}
    for name,charge in [('H03_residual_free',np.zeros(len(labels))),('H03_residual_measured',descriptor)]:
        m,p,r,c=evaluate(name,X,NAMES,available,charge,data)
        metrics+=m;predictions+=p;rules+=r;candidates[name]=c
    save_csv(out/'metrics.csv',metrics);save_csv(out/'predictions.csv',predictions)
    (out/'fold_rules.json').write_text(json.dumps(rules,indent=2)+'\n')
    (out/'development_candidate.json').write_text(json.dumps(dict(role='EXPLORATORY_FULL_FIT_NOT_VALIDATION',rules=candidates),indent=2)+'\n')
    files=[SOURCE/'labels.csv',SOURCE/'parent_features.csv',SOURCE/'root_propagation.jsonl',SOURCE/'reused_root_propagation.jsonl',EXP/'protocol.md',out/'features.jsonl',ROOT/'src/root_features.cpp',Path(__file__),ROOT/'src/simple_selection.py']
    receipt=dict(status='FORMAL_EXPLORATORY_ANALYSIS_COMPLETE',root_UP_agreement_parents=len(checks),extraction_available_parents=sum(r['available'] for r in raw),usable_residual_parents=sum(r['available'] and r.get('usable_residual',False) for r in raw),parents=300,measured_extraction_cpu_s=sum(r['cpu_s'] for r in raw),wall_s=time.monotonic()-begin,source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},python=sys.version,numpy=np.__version__)
    (out/'analysis_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    lines=['# H03：根传播残余特征','','同一300题探索；291成本有效、69明确赢家。缺失特征或传播直接解题回退D，保留其成本。','','|路径|成本比D|95%区间|准确率|切换覆盖|切换精度|','|---|---:|---|---:|---:|---:|']
    for r in metrics:
        if r['cohort']=='combined300':
            precision='无切换' if r['switch_accuracy'] is None else f"{r['switch_accuracy']:.1%}"
            lines.append(f"|{r['path']}|{r['cost_ratio']:.4f}|[{r['cost_ratio_ci_low']:.4f},{r['cost_ratio_ci_high']:.4f}]|{r['accuracy']:.1%}|{r['switch_coverage']:.1%}|{precision}|")
    lines+=['',f"正式提取成功 {receipt['extraction_available_parents']}/300，可用残余 {receipt['usable_residual_parents']}/300。原始计数与{len(checks)}题的旧根UP状态逐题相符。累计提取CPU {receipt['measured_extraction_cpu_s']:.3f}秒。",'', '免费路径仅信号上界；实测路径包括读取、hash、子进程与完整根UP的CPU。训练若回退恒定D，部署无需提取特征，其成本不等于研究实际免费。', '', '这是已看过数据上的新探索程序，没有获得新题确认。全部折规则、逐题预测和候选均保留。']
    (EXP/'analysis.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(receipt=receipt,metrics=[r for r in metrics if r['cohort']=='combined300'],candidates=candidates),ensure_ascii=False))

if __name__=='__main__':main()
