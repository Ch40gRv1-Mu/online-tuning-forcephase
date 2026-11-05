"""Summarize the six frozen programs, preserve evidence, and publish a scoped negative result."""
from pathlib import Path
import csv,hashlib,html,json,shutil,subprocess,sys,zipfile
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=Path('/Users/expexp/Documents/Codex/2026-10-28/new-chat/outputs/forcephase_autoresearch')
ITEMS=[('H01_cost_aware_static_rule','原始静态单阈值','Static counts'),('H02_signed_clause_asymmetry','符号不对称','Sign bias'),('H03_root_propagation_residual','根传播残差','Root UP'),('H04_short_original_D_trace','极短D轨迹','D trace'),('H05_relative_phase_response','相对响应＋大小门控','Relative phases'),('H06_conditioned_propagation','条件传播＋大小门控','Branch UP')]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def csvrows(p):
    with p.open(newline='') as f:return list(csv.DictReader(f))
def jsonlines(p):return [json.loads(s) for s in p.read_text().splitlines() if s]
def writecsv(p,rows):
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    sources=ROOT/'work/expanded_parents/results'
    labels=csvrows(sources/'labels.csv');valid=[r for r in labels if r['reason'] not in ('unverified','contended','execution_error','missing')]
    assert len(labels)==300 and len(valid)==291 and sum(bool(r['clear']) for r in valid)==69
    cohort=csvrows(sources/'reused_parents.csv')+csvrows(sources/'new_parents.csv')
    assert len(cohort)==300 and len({r['isohash'] for r in cohort})==300 and all(r['isohash'] not in ('','empty','None') for r in cohort)
    parentruns=jsonlines(sources/'runs.jsonl')+jsonlines(sources/'reused_parent_runs.jsonl')
    assert len(parentruns)==900
    parentby={(r['parent'],r['config']):r for r in parentruns}
    assert len(parentby)==900 and all('total_cpu_s' in r for r in parentruns)
    rows=[];supplement=[];screen=[];checks=[];cpu=[]
    for name,title,english in ITEMS:
        exp=ROOT/'experiments'/name;res=exp/'results'
        assert (exp/'protocol.md').is_file() and (exp/'analysis.md').is_file()
        metrics=csvrows(res/'metrics.csv');chosen=[r for r in metrics if r['cohort']=='combined300' and 'measured' in r['path']]
        assert len(chosen)==1;m=chosen[0];path=m['path']
        preds=[r for r in csvrows(res/'predictions.csv') if r['path']==path]
        assert len(preds)==291 and {r['id'] for r in preds}=={r['id'] for r in valid}
        assert len({(r['family'],r['fold']) for r in preds})==len({r['family'] for r in preds})
        truth={r['id']:r['clear'] for r in valid}
        clear=[r for r in preds if truth[r['id']]]
        assert len(clear)==69
        assert abs(sum(r['prediction']==truth[r['id']] for r in clear)/69-float(m['accuracy']))<1e-12
        assert sum(r['prediction']!='D' for r in clear)==int(m['switch_n'])
        for r in preds:
            expected=parentby[(r['id'],r['prediction'])]['par2']+float(r['feature_cpu_s'])
            assert abs(float(r['selected_PAR2_plus_feature_s'])-expected)<1e-8
        direct_ratio=sum(float(r['selected_PAR2_plus_feature_s']) for r in preds)/sum(parentby[(r['id'],'D')]['par2'] for r in preds)
        assert abs(direct_ratio-float(m['cost_ratio']))<1e-12
        candidates=json.loads((res/'development_candidate.json').read_text())['rules']
        ratio=float(m['cost_ratio']);candidate=candidates[path]
        # All six fail the first pre-set admission condition; no extra post-hoc test is needed.
        assert ratio>=1, 'A candidate may need confirmation; negative conclusion is not justified.'
        screen.append(dict(hypothesis=name,path=path,cost_ratio=ratio,full_development_candidate_exists=candidate is not None,admission='NO',reason='Held-out measured cost point estimate is not below fixed D'))
        rr=dict(hypothesis=name,title=title,path=path,cost_ratio=ratio,delta_percent=100*(ratio-1),ci_low=float(m['cost_ratio_ci_low']),ci_high=float(m['cost_ratio_ci_high']),accuracy=float(m['accuracy']),D_accuracy=float(m['D_accuracy']),switch_n=int(m['switch_n']),switch_coverage=float(m['switch_coverage']),switch_accuracy=float(m['switch_accuracy']) if m['switch_accuracy'] else None,clear_n=69,cost_valid_n=291)
        rows.append(rr)
        selected=sum(float(r['feature_cpu_s'])+parentby[(r['id'],r['prediction'])]['total_cpu_s'] for r in preds)
        baseline=sum(parentby[(r['id'],'D')]['total_cpu_s'] for r in preds)
        supplement.append(dict(hypothesis=name,selected_parent_plus_feature_CPU_including_parent_verification_s=selected,D_total_CPU_including_verification_s=baseline,ratio_including_parent_verification=selected/baseline,role='DESCRIPTIVE_COST_CHECK_NOT_RETUNED'))
        assert selected>=baseline, 'End-to-end accounting needs separate interpretation before conclusion.'
        receipt=json.loads((res/('receipt.json' if name.startswith('H01') else 'analysis_receipt.json')).read_text())
        hashes=receipt.get('source_hashes',{})
        if name.startswith('H01'):
            hashes={str((sources/k).relative_to(ROOT)):v for k,v in receipt['input_sha256'].items()}
            hashes.update({'src/h01_static_rule.py':receipt['source_sha256'],str((exp/'protocol.md').relative_to(ROOT)):receipt['protocol_sha256']})
        for rel,digest in hashes.items():assert sha(ROOT/rel)==digest,rel
        checks.append(dict(hypothesis=name,protocol_present=True,analysis_receipt_present=True,source_hashes_match=len(hashes),distinct_test_predictions=291,family_fold_consistent=True,measured_cost_screen_failed=True))
        if not name.startswith('H01'):
            completion=json.loads((res/'completion.json').read_text())
            measured=completion.get('all_feature_cpu_s',completion.get('cpu_s'))
            build=0.
            if (res/'build_time.txt').exists():
                timing=dict(x.split('=') for x in (res/'build_time.txt').read_text().split());build=float(timing['user_cpu_s'])+float(timing['system_cpu_s'])
            cpu.append(dict(hypothesis=name,timed_worker_CPU_s=measured,build_CPU_s=build,wall_s=completion['wall_s'],note='Excludes local analysis, transfer, controller startup and artifact persistence CPU'))
    writecsv(OUT/'summary.csv',rows);writecsv(OUT/'validation_costs.csv',supplement);writecsv(OUT/'cpu_accounting.csv',cpu)
    (OUT/'candidate_screen.json').write_text(json.dumps(screen,indent=2,ensure_ascii=False)+'\n')
    (OUT/'completion_check.json').write_text(json.dumps(dict(status='PASS_FOR_SCOPED_NEGATIVE_CONCLUSION',hypotheses=checks,original_parents=300,cost_valid=291,clear_labels=69,clear_families=len({r['family'] for r in valid if r['clear']}),distinct_isohashes=300,new_confirmation_run=False,multiseed_confirmation_run=False,reason_confirmation_not_run='No candidate meets pre-set held-out net-cost admission condition',verification_scope='Read existing formal measurements, identities and artifacts; no independent audit or dry run'),indent=2)+'\n')
    # Standalone scientific chart; all numeric values are the saved outer-fold estimates.
    names=[x[2] for x in ITEMS];delta=np.array([r['delta_percent'] for r in rows]);low=100*(np.array([r['ci_low'] for r in rows])-1);high=100*(np.array([r['ci_high'] for r in rows])-1)
    fig,axes=plt.subplots(1,2,figsize=(11,4.3),gridspec_kw={'width_ratios':[1.5,1]})
    y=np.arange(6);axes[0].barh(y,delta,color=['#99726a','#86a18b','#99726a','#99726a','#99726a','#99726a'],alpha=.8)
    axes[0].errorbar(delta,y,xerr=np.array([delta-low,high-delta]),fmt='none',ecolor='#233b40',capsize=3);axes[0].axvline(0,color='#315d51',lw=1)
    axes[0].set_yticks(y,names);axes[0].invert_yaxis();axes[0].set_xlabel('Cost change vs D (%) — lower is better');axes[0].set_title('PAR2 + measured feature costs\n95% family bootstrap intervals')
    accuracy=np.array([r['accuracy'] for r in rows])*100
    axes[1].barh(y,accuracy,color='#73958d');axes[1].axvline(100*33/69,color='#a0604d',ls='--',label='Always D: 47.8%');axes[1].set_yticks(y,names);axes[1].invert_yaxis();axes[1].set_xlim(0,65);axes[1].set_xlabel('Winner accuracy (%) on 69 clear labels');axes[1].legend(loc='lower right',fontsize=8);axes[1].set_title('Coverage and abstention retained\nH02 learns constant D')
    for ax in axes:ax.spines[['top','right']].set_visible(False)
    fig.tight_layout();fig.savefig(OUT/'six_hypotheses.png',dpi=180);fig.savefig(OUT/'six_hypotheses.pdf');plt.close(fig)
    timed=sum(r['timed_worker_CPU_s'] for r in cpu);build=sum(r['build_CPU_s'] for r in cpu)
    lines=['# Forcephase autoresearch：本轮六类检验完成','','结论：在当前300父题、60秒parent预算和预设的小规则集合内，未找到能跨家族改善净成本的简单F+/F−/D选择器。该结论限定本轮检验范围；不能据此证明偏好是非局部的，或不存在其他简单特征。','','## 结果','','主指标按冻结协议为parent solver PAR2加特征/探测完整计时CPU；真实CPU及parent验证费用另列。所有项目按family外层5折评价完整训练程序，包含弃权回退D。','','|检验|成本变化|95%家族区间|明确题准确率|切换命中|','|---|---:|---|---:|---|']
    for r in rows:
        hits='无切换，恒定D' if r['switch_accuracy'] is None else f"{round(r['switch_accuracy']*r['switch_n'])}/{r['switch_n']}"
        lines.append(f"|{r['title']}|{r['delta_percent']:+.3f}%|[{100*(r['ci_low']-1):+.3f}%, {100*(r['ci_high']-1):+.3f}%]|{r['accuracy']:.1%}|{hits}|")
    lines+=['','H01收费为现有完整静态提取器的部分成本，未计单独根UP；它在该有利估计下已未受益。H02的0变化表示返回恒定D，不表示识别了其他配置。所有区间是探索性的，未因六类适应性探索而调整。H06区间仍容许极小改善，本轮未通过筛选不等于排除了所有可能收益。','', '## 证据和边界','', '- 原300题仅作探索：69道明确赢家（D33/F+14/F−22）、46个明确标签家族；291道有效成本题。300个isohash唯一。新增252题中200题三配置均未解，不能把300当300个三分类标签。','- H04出现过小的方向信号：特征免费时仅节省约0.020%，计费后多花0.221%，覆盖3/69、命中1/3；不足成为可靠规则。','- H05/H06在训练集能拟合规则，但按家族留出后失败。筛选没有只保留训练成功或正相关的子集。','- H06有264题完整提取、260题可用、1572条件分支；36未完成、2终局诊断、2完成但超严格预算，均保留父题并回退D。根UP和分支不变量在正式执行中核对。','- 补充计入所选完整parent的model/证明验证CPU后，六种收费程序仍都不优于D，数值见validation_costs.csv；这未被用于重新选择规则。','- 没有候选通过进入确认的第一道门槛（留出家族、计费后成本点估计优于D），因此未启动新题或多seed确认；不能声称已经在新分布或重复运行中证实普遍无效。','', '## 计算与复现','',f'复用900条完整parent测量，新增1800次短solver探测和900个特征/传播任务；没有重跑完整基线。实测新增worker计时CPU合计{timed:.3f}秒，编译{build:.2f}秒，合计约{(timed+build)/60:.2f} CPU分钟。此小计不含本地统计分析、传输、控制器启动和文件持久化CPU，不能当作全系统精确总CPU。', '', '保留每轮冻结协议、原始特征、逐题留出预测、家族折规则、费用、验证记录和源代码。reproduction/提供统计分析输入和程序；原始CNF、stdout与证明保留于原服务器，未删除。报告不包含SSH密码。', '', '## 本轮停止与下一步边界','', '六类预设检验均完成，形成可追溯的有限否定结论，按原工作流结束本轮循环。若以后继续，优先补充可产生有效赢家标签的独立难度分层，或研究固定冲突预算下的动态信号与分布内规则；这些属于下一轮，当前没有自动启动。']
    (OUT/'FINAL_REPORT.md').write_text('\n'.join(lines)+'\n')
    tbody=''.join(f'<tr><td>{html.escape(r["title"])}</td><td>{r["delta_percent"]:+.3f}%</td><td>{100*(r["ci_low"]-1):+.3f}% ～ {100*(r["ci_high"]-1):+.3f}%</td><td>{r["accuracy"]:.1%}</td><td>{r["switch_n"]}/69</td></tr>' for r in rows)
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Forcephase 六类简单规则检验</title><style>body{font:16px/1.8 system-ui,sans-serif;background:#f3f5f1;color:#233b3d;max-width:1080px;margin:auto;padding:32px 22px}h1{font-size:36px;line-height:1.3}h2{margin-top:35px}.badge{background:#e2e9de;display:inline-block;padding:4px 14px;border-radius:20px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px}.card{padding:20px;background:white;border:1px solid #d8ded4;border-radius:14px}.number{display:block;font-size:30px;font-weight:650}img{width:100%;background:white;border-radius:12px}table{border-collapse:collapse;width:100%;background:white}td,th{text-align:left;padding:12px;border-bottom:1px solid #d7e0d5}.scroll{overflow:auto}a{color:#1f6c61}.note{border-left:4px solid #a98470;padding-left:16px}small{color:#607771}</style><span class="badge">预设六类检验完成 · 有限否定结果</span><h1>尚未找到可跨家族改善净成本的<br>简单 F+ / F− / D 选择规则</h1><p>本轮完成了静态计数、符号不对称、根传播残差、极短原题轨迹、三配置相对响应和条件分支传播。证据不足时回退D，探测与失败费用均保留。</p><div class="cards"><div class="card"><small>探索集</small><span class="number">300 题</span>其中69个明确赢家、46个明确标签家族；291题可计成本。</div><div class="card"><small>新增正式测量</small><span class="number">1800 + 900</span>短solver探测 + 特征/传播任务，完整parent基线全部复用。</div><div class="card"><small>进入新题确认</small><span class="number">0 个候选</span>六类计费程序均没有更低的留出家族成本点估计。</div></div><h2>完整结果</h2><img src="six_hypotheses.png" alt="六类程序的成本变化与明确题准确率"><div class="scroll"><table><tr><th>检验</th><th>成本变化</th><th>95%家族区间</th><th>准确率</th><th>切换覆盖</th></tr>__ROWS__</table></div><p><small>成本变化以D为0，越低越好。准确率分母69；默认D为47.8%。H01尚未计单独根UP成本，H02恒定D。区间均为探索性家族bootstrap，未做适应性多重选择校正。</small></p><h2>可以说什么？</h2><p>在当前样本、60秒预算和已冻结的简单规则集合内，没有发现能稳定支付自身探测开销的选择器。H04的免费信号只有约0.020%的成本收益，计费后消失；H05/H06训练集上的规则没有迁移到留出家族。</p><p class="note">这不证明配置偏好必定是非局部特征，也不证明不存在其他简单特征。本轮没有合格候选，因此没有运行新题或多seed确认。原始题量大于有效标签量，是重要限制。</p><h2>资料与复现</h2><p><a href="FINAL_REPORT.md">完整总结</a> · <a href="summary.csv">六类全部指标</a> · <a href="validation_costs.csv">包含parent验证的补充CPU账目</a> · <a href="six_hypotheses.pdf">图表PDF</a> · <a href="../forcephase_autoresearch_results.zip">结果与复现包</a></p><p>全部原始特征、逐题预测、家族折规则、协议、源代码与输入均在复现包中。原CNF、solver日志与证明继续保留在服务器。研究按预设六类范围结束，没有自动扩题或延长预算。</p></html>'''.replace('__ROWS__',tbody)
    (OUT/'index.html').write_text(page);(OUT/'final_report.html').write_text(page)
    for name in ('AUTORESEARCH_WORKFLOW.md','findings.md','research-log.md'):
        shutil.copy2(ROOT/name,OUT/name)
    repro=OUT/'reproduction';repro.mkdir(exist_ok=True)
    (repro/'src').mkdir(exist_ok=True)
    for file in (ROOT/'src').iterdir():
        if file.is_file():shutil.copy2(file,repro/'src'/file.name)
    for name,_,_ in ITEMS:
        source=ROOT/'experiments'/name;dest=repro/'experiments'/name;(dest/'results').mkdir(parents=True,exist_ok=True)
        for file in ('protocol.md','analysis.md'):shutil.copy2(source/file,dest/file)
        for file in (source/'results').iterdir():
            if file.is_file() and file.suffix in ('.csv','.json','.jsonl','.txt','.log'):shutil.copy2(file,dest/'results'/file.name)
    inp=repro/'work/expanded_parents/results';inp.mkdir(parents=True,exist_ok=True)
    for file in ('labels.csv','parent_features.csv','analysis_environment.json','root_propagation.jsonl','reused_root_propagation.jsonl','reused_parents.csv','new_parents.csv','runs.jsonl','reused_parent_runs.jsonl'):
        shutil.copy2(sources/file,inp/file)
    for file in ('AGENTS.md','AUTORESEARCH_WORKFLOW.md','findings.md','research-log.md','research-state.yaml'):
        shutil.copy2(ROOT/file,repro/file)
    (repro/'requirements.txt').write_text('numpy==2.5.4\nmatplotlib==3.11.2\n')
    (repro/'README.md').write_text('统计分析复现包，Python3.12。依赖见requirements.txt。每轮源代码、冻结协议和输入原样保留；原结果目录为只读证据，程序会拒绝覆盖完成结果。若需复算，在另一个副本中移除各results目录的派生analysis_receipt.json、metrics.csv、predictions.csv、fold_rules.json、development_candidate.json；保留features.jsonl与completion等原输入。H01没有新原始特征文件，其results目录可在该副本中整体移除。然后依次运行src/h01_static_rule.py至src/h06_analyze.py（H02/3/4/5/6文件名见src）。这只重新计算统计，不会重新运行solver。原始CNF、stdout和证明保留在服务器/root/forcephase_subinstances_paired_v1_20261028，raw evidence地址见各receipt及run记录；本包不包含密码。\n')
    history=subprocess.run(['git','log','--format=%H %cI %s'],cwd=ROOT,capture_output=True,text=True,check=True).stdout
    (OUT/'protocol_history.txt').write_text(history)
    if '--history' in sys.argv:
        head=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
        bundle=OUT/f'research-history-{head[:8]}.bundle'
        if not bundle.exists():subprocess.run(['git','bundle','create',str(bundle),'--all'],cwd=ROOT,check=True,capture_output=True)
    manifest={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ('MANIFEST.json','research-history.bundle')}
    (OUT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    archive=OUT.parent/'forcephase_autoresearch_results.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(OUT))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    synthesis=dict(status='SCOPED_NEGATIVE_SYNTHESIS_READY',hypotheses=6,confirmation_candidates=0,confirmation_launched=False,timed_new_worker_cpu_s=timed,build_cpu_s=build,measured_total_cpu_s=timed+build,summary=rows,report=str(OUT/'FINAL_REPORT.md'),archive=str(archive),archive_bytes=archive.stat().st_size,archive_sha256=sha(archive))
    (ROOT/'data').mkdir(exist_ok=True);(ROOT/'data/final_synthesis.json').write_text(json.dumps(synthesis,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in synthesis.items() if k!='summary'},ensure_ascii=False))

if __name__=='__main__':main()
