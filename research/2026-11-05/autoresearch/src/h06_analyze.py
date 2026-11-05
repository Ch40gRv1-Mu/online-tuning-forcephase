"""H06 root/branch invariants and the pre-fixed cost-sensitive gated evaluation."""
from pathlib import Path
import hashlib,json,time,sys
import numpy as np
from simple_selection import ROOT,SOURCE,load_data,save_csv
from gated_selection import evaluate

EXP=ROOT/'experiments/H06_conditioned_propagation'
NAMES=['branch_conflict_fraction','mean_assigned_gain_fraction','signed_assigned_asymmetry','absolute_assigned_asymmetry','signed_clause_asymmetry']

def main():
    begin=time.monotonic();out=EXP/'results'
    if (out/'analysis_receipt.json').exists():raise SystemExit('Preserving completed H06')
    raw=[json.loads(s) for s in (out/'features.jsonl').read_text().splitlines() if s]
    assert len(raw)==300 and len({r['id'] for r in raw})==300
    data=load_data();labels,features,*_=data;by={r['id']:r for r in raw};prior={}
    for name in ('root_propagation.jsonl','reused_root_propagation.jsonl'):
        for s in (SOURCE/name).read_text().splitlines():
            r=json.loads(s);prior[r['parent']]=r
    checked=[];branches=0;diagnostics=0;timeouts=0
    for r in raw:
        assert r['input_sha256']==features[r['id']]['cnf_sha256']
        expected=int(hashlib.sha256(('forcephase-autoresearch-h06-v1:'+r['id']).encode()).hexdigest()[:16],16)
        assert r['seed']==expected
        if r.get('returncode')==2 and 'bad_alloc' not in r.get('stderr',''):raise RuntimeError('Unexpected extraction error: '+str(r))
        if not r['extraction_complete']:
            timeouts+=1;continue
        checked.append(r['id']);old=prior[r['id']]
        for k in ('root_assigned_variables','root_remaining_clauses','root_conflict'):
            assert r[k]==old[k],(r['id'],k,r[k],old[k])
        if not r['root_conflict']:assert r['root_free_variables']==old['eligible_free_variables']
        assert r['branch_pairs']<=3 and len(r['branches'])==2*r['branch_pairs']
        assert len({b['variable'] for b in r['branches']})==r['branch_pairs']
        diagnostics+=r['directly_solved_diagnostic'];branches+=len(r['branches'])
        for b in r['branches']:
            assert b['sign'] in (-1,1)
            assert 0<=b['assigned']-r['root_assigned_variables']<=r['root_free_variables']
        if r['available']:assert r['cpu_s']<=.3 and r['wall_s']<=3 and r['usable_branch']
        assert not any(s in r['stderr'] for s in ('root assignment changed','invalid assignment gain','branch unit lost'))
        status=features[r['id']]['verified_status']
        proves_sat=(not r['root_conflict'] and r['root_remaining_clauses']==0) or any(not b['conflict'] and b['remaining_clauses']==0 for b in r['branches'])
        proves_unsat=r['root_conflict'] or any(r['branches'][i]['conflict'] and r['branches'][i+1]['conflict'] for i in range(0,len(r['branches']),2))
        assert not(proves_sat and proves_unsat)
        assert not(status=='SAT' and proves_unsat) and not(status=='UNSAT' and proves_sat)
    X=np.array([[by[r['id']].get(k,float('nan')) for k in NAMES] for r in labels]);available=np.array([by[r['id']]['available'] for r in labels]);charge=np.array([by[r['id']]['cpu_s'] for r in labels]);sizes=np.array([by[r['id']]['file_bytes'] for r in labels]);gatefee=np.array([by[r['id']]['charged_gate_cpu_s'] for r in labels])
    metrics=[];predictions=[];rules=[];classes=[];candidates={}
    for path,charged in [('H06_conditioned_free',False),('H06_conditioned_measured',True)]:
        option=dict(budget=.3,names=NAMES,X=X,available=available,charge=charge if charged else np.zeros(len(labels)),bytes=sizes,gatefee=gatefee if charged else np.zeros(len(labels)))
        m,p,r,cl,c=evaluate(path,[option],data);metrics+=m;predictions+=p;rules+=r;classes+=cl;candidates[path]=c
    for name,rows in [('metrics.csv',metrics),('predictions.csv',predictions),('class_metrics.csv',classes)]:save_csv(out/name,rows)
    (out/'fold_rules.json').write_text(json.dumps(rules,indent=2)+'\n')
    (out/'development_candidate.json').write_text(json.dumps(dict(role='EXPLORATORY_FULL_FIT_NOT_VALIDATION',rules=candidates),indent=2)+'\n')
    files=[SOURCE/'labels.csv',EXP/'protocol.md',out/'features.jsonl',SOURCE/'root_propagation.jsonl',SOURCE/'reused_root_propagation.jsonl',Path(__file__),ROOT/'src/gated_selection.py',ROOT/'src/branch_features.cpp',ROOT/'src/propagation_features.hpp',ROOT/'src/run_branch_features.py']
    receipt=dict(status='FORMAL_EXPLORATORY_ANALYSIS_COMPLETE',parents=300,root_agreement_checked=len(checked),conditioned_branches=branches,directly_solved_diagnostics=diagnostics,extraction_incomplete=timeouts,feature_available=sum(r['available'] for r in raw),extraction_cpu_s=sum(r['cpu_s'] for r in raw),wall_s=time.monotonic()-begin,source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},python=sys.version,numpy=np.__version__)
    (out/'analysis_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    lines=['# H06：少量条件分支的纯传播特征','','同一300题探索；291有效成本、69明确赢家。每题最多3对互补unit条件，只做UP，合计0.3CPU秒。所有门槛和选择都在训练家族内，留出家族独立评价。','','|路径|成本比D|95%区间|明确题准确率|切换覆盖|切换精度|','|---|---:|---|---:|---:|---:|']
    for r in metrics:
        if r['cohort']=='combined300':
            precision='无切换' if r['switch_accuracy'] is None else f"{r['switch_accuracy']:.1%}"
            lines.append(f"|{r['path']}|{r['cost_ratio']:.4f}|[{r['cost_ratio_ci_low']:.4f},{r['cost_ratio_ci_high']:.4f}]|{r['accuracy']:.1%}|{r['switch_coverage']:.1%}|{precision}|")
    lines+=['',f"完整传播提取{len(checked)}/300，实际条件分支{branches}个；可用特征{receipt['feature_available']}/300，直接终结原题的诊断{diagnostics}题，未完成提取{timeouts}题。累计提取CPU {receipt['extraction_cpu_s']:.3f}秒。",'', '所有已完成root状态与旧精确传播逐题相符，条件分支内部不变量成立，直接逻辑诊断与已有验证结果无矛盾。终局诊断与失败题均保留并回退D，成本没有因缺失而消失。', '', '免费路径只检验信号上界；收费路径包含输入读取、hash、根及条件传播、失败开销及门控费。本轮没有新的完整parent测量，也未运行独立audit或dryrun。若六类探索均无合格候选，则按预设流程总结否定证据，不能声称不存在其他简单特征。']
    (EXP/'analysis.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(receipt=receipt,metrics=[r for r in metrics if r['cohort']=='combined300'],candidates=candidates),ensure_ascii=False))

if __name__=='__main__':main()
