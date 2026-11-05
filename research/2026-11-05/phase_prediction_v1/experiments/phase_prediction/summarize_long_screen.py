"""Descriptive paired-parent uncertainty for a complete, validated long matrix.

This is a fit-screen report, never a policy reward or a confirmation decision.
"""
import argparse,itertools,json,math,random,statistics,time
from pathlib import Path
import run_pilot as common

ACTIONS=['D','Fplus','Fminus','Iminus']

def describe(cases,iterations=2000):
    if not cases or len({r['hash'] for r in cases})!=len(cases):
        raise ValueError('independent parent rows required')
    if any(r['role'] not in ('development_fit','development_feedback') for r in cases):
        raise ValueError('protected data cannot enter a development screen')
    roles={r['role'] for r in cases}
    if len(roles)!=1:raise ValueError('report fit and feedback separately')
    if any(set(r['costs'])!=set(ACTIONS) for r in cases):raise ValueError('missing static control')
    for r in cases:
        if any(not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 for x in r['costs'].values()):
            raise ValueError('invalid measured cost')
        for rows in r['outcomes'].values():
            if any(x['cutoff_s']!=600 for x in rows):raise ValueError('T600 is the primary cutoff')
    values={a:[r['costs'][a] for r in cases] for a in ACTIONS}
    values['three_action_oracle']=[min(r['costs'][a] for a in ACTIONS[:3]) for r in cases]
    means={a:statistics.mean(v) for a,v in values.items()}
    baseline=min(ACTIONS,key=lambda a:(means[a],a))
    rng=random.Random(20261104)
    draws=[[rng.randrange(len(cases)) for _ in cases] for _ in range(iterations)]
    def paired(first,second):
        x=values[first];y=values[second]
        rewards=[]
        for ids in draws:
            denom=sum(y[i] for i in ids)
            if denom>0:rewards.append(1-sum(x[i] for i in ids)/denom)
        rewards.sort()
        if means[second]<=0 or not rewards:raise ValueError('nonpositive reference mean')
        return {'first':first,'second':second,'mean_delta_s':means[first]-means[second],
                'relative_improvement':1-means[first]/means[second],
                'descriptive_paired_parent_95pct':[rewards[int((len(rewards)-1)*.025)],
                                                 rewards[int((len(rewards)-1)*.975)]]}
    all_censored=sum(all(not o['resolved'] for rows in r['outcomes'].values() for o in rows) for r in cases)
    return {'role':next(iter(roles)),'independent_parents':len(cases),'cutoff_s':600,
            'mean_par2_s':means,'best_static_on_this_fit_screen':baseline,
            'oracle_vs_best_static':paired('three_action_oracle',baseline),
            'static_pairwise':[paired(a,b) for a,b in itertools.combinations(ACTIONS,2)],
            'all_four_actions_censored_parents':all_censored,
            'at_least_one_action_verified_parents':len(cases)-all_censored,
            'oracle_scope':'Minimum of D/Fplus/Fminus only, no feature cost, seed means within each parent. Iminus remains a static control.',
            'interval_scope':'Descriptive fit-screen paired bootstrap, 2000 draws with seed20261104; best static was selected on these same fit rows. No gate/confirmation claim; timeout is cutoff censoring, not a true runtime.',
            'bootstrap_iterations':iterations}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--analysis',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);a=parser.parse_args();start=time.process_time()
    integrity=json.loads((a.analysis/'integrity.json').read_text())
    summary=json.loads((a.analysis/'summary.json').read_text())
    if not integrity['complete_and_valid'] or summary['mode']!='static':
        raise ValueError('complete valid static matrix required')
    cases=[json.loads(x) for x in (a.analysis/'cases.jsonl').read_text().splitlines() if x]
    if integrity['parents']!=len(cases):raise ValueError('changed analysis parent count')
    report=describe(cases)
    report.update(cases_sha256=common.sha(a.analysis/'cases.jsonl'),
                  summary_sha256=common.sha(a.analysis/'summary.json'),
                  analysis_identity=summary['identity'],reporter_sha256=common.sha(Path(__file__)))
    a.out.mkdir(parents=True,exist_ok=False)
    c=report['oracle_vs_best_static'];lo,hi=c['descriptive_paired_parent_95pct']
    lines=['# 600秒完整矩阵：开发筛查','',
        f"独立父题{len(cases)}个；四配置均删失{report['all_four_actions_censored_parents']}个。主要cutoff为600秒，120/300只作原报告中的诊断。",'',
        '| 配置 | 平均PAR2（秒） |','|---|---:|']
    lines += [f'| {name} | {value:.6f} |' for name,value in report['mean_par2_s'].items()]
    lines += ['',f"本面板最佳静态为{report['best_static_on_this_fit_screen']}。三动作免费oracle相对它的改善为{100*c['relative_improvement']:.3f}%，描述性父题配对区间[{100*lo:.3f}%, {100*hi:.3f}%]。",'',
        'oracle假设每题预知D/F+/F−中谁最好且不付特征费。I−只作为强静态对照。上述区间来自同一fit筛查，不能充当未见数据上的策略收益，也不能把多seed/轨迹当独立父题。', '',
        '该报告不是RICL reward、真实策略部署或整个目标完成。完整长预算筛查后仍需冻结开发面板、实际反馈迭代、费用与部署核对，以及满足门槛后的条件确认。']
    (a.out/'LONG600_SCREEN.md').write_text('\n'.join(lines)+'\n')
    report['local_report_cpu_s']=time.process_time()-start
    common.write(a.out/'long600_screen_report.json',report)
    print(json.dumps({'parents':len(cases),'best_static':report['best_static_on_this_fit_screen'],
                      'oracle_comparison':c,'local_report_cpu_s':report['local_report_cpu_s']}))

if __name__=='__main__':main()
