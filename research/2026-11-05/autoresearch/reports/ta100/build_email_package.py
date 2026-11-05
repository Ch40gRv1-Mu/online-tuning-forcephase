"""Package existing TA100 rules and results for the user's requested email.
No solver, fitting, scoring, protected-data reads or email side effects.
"""
import base64
import csv
import hashlib
import html
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports/ta100"
DELIVERY = REPORTS / "email_delivery"
WORK = ROOT / "work/ta100/email_delivery_v1"
SUBJECT = "SAT相位选择研究：全部100轮规则、13种实际策略与完整结果"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def esc(value):
    return html.escape(str(value))


def pct(value):
    return f"{100*float(value):+.4f}%"


def rule_lines(node, conditions=()):
    if "action" in node:
        return [(conditions, node["action"])]
    f, t = node["feature"], repr(node["threshold"])
    return rule_lines(node["left"], conditions+(f"{f} <= {t}",)) + rule_lines(
        node["right"], conditions+(f"{f} > {t}",))


def render_rule(policy):
    return "<ul>"+"".join("<li><code>"+esc(" AND ".join(c))+"</code> → <b>phase="+a+"</b></li>"
        for c,a in rule_lines(policy["tree"]))+"</ul>"


def main():
    DELIVERY.mkdir(exist_ok=True)
    WORK.mkdir(parents=True,exist_ok=True)
    records = list(csv.DictReader((REPORTS/"LEADERBOARD.csv").open()))
    catalogue = json.loads((REPORTS/"FEATURE_CATALOGUE.json").read_text())
    summary = json.loads((REPORTS/"SUMMARY.json").read_text())
    if len(records)!=100 or catalogue["candidate_count"]!=100 or summary["rounds"]!=100:
        raise ValueError("requires all100 existing records")
    candidates = {c["round_id"]:c for c in catalogue["candidates"]}
    groups, ordered, raw = {}, [], {}
    for row in records:
        path = ROOT/row["result_path"]
        if sha(path)!=row["result_sha256"]:
            raise ValueError("changed immutable result")
        r = json.loads(path.read_text()); raw[row["round"]]=r
        policy = {k:r["policy"].get(k) for k in ("baseline_action","tree","fallback_policy","required_dynamic_features")}
        if policy["fallback_policy"] is not None:
            raise ValueError("observed policies must have no nested fallback")
        key = json.dumps(policy,sort_keys=True,separators=(",",":"))
        if key not in groups:
            group = {"rank":len(ordered)+1,"representative_round":row["round"],"policy":policy,
                "gain_vs_old_static":float(row["feedback_gain_vs_old_static"]),
                "gain_vs_fixed_true":float(row["feedback_gain_vs_fixed_true"]),"members":[]}
            groups[key]=group;ordered.append(group)
        groups[key]["members"].append(row["round"])
    if len(ordered)!=13 or sorted(len(g["members"]) for g in ordered)!=[1]*12+[88]:
        raise ValueError("policy grouping differs from reported study")
    policy_for_round = {rid:g["rank"] for g in ordered for rid in g["members"]}
    (DELIVERY/"ALL_13_POLICIES.json").write_text(json.dumps(ordered,ensure_ascii=False,indent=2)+"\n")
    existing_code=(REPORTS/"top10_policies.py").read_text()
    predictor=existing_code[existing_code.index("def choose_phase"):].replace("<= 10:","<= 13:").replace("rank must be1..10","rank must be1..13")
    code='''"""All13 existing distinct policies. Input feature definitions remain unchanged.
Rank is exploratory feedback order. Missing required reached-branch field => true.
"""
import json
import math
POLICIES = json.loads(r\'\'\'\n'''+json.dumps(ordered,ensure_ascii=False,indent=2)+'''\n\'\'\')\n\n'''+predictor
    compile(code,"all_13_policies.py","exec")
    (DELIVERY/"all_13_policies.py").write_text(code)

    intro='''<h1>SAT相位选择：全部规则与结果</h1>
<p>本报告覆盖已完成的TA100研究：100轮探索，70项输入端结构/有界辅助计算、30项原生求解器动态机制；输入端包含两项局部搜索辅助轨迹。10次workflow修订均保留。</p>
<p>全部标签复用TA原false/true计时。训练180题、开发反馈60题，192合格题采集字段；完整240父题保留缺失回退。此处仅指TA false/true，不补造D标签，不重建完整相位耗时矩阵。gate与最终测试未用于TA100。</p>
<p><b>100轮产生13种实际规则</b>：88轮没有采用其新增字段，最终得到同一旧静态规则。88轮共享同一批数据，不是88次独立验证。下面既给13种实际决策树，也逐项保留100个特征提案及结果。</p>
<p>最终fit树采用新字段12次；1个反馈点估计改善、11个变差、88个未选。最佳I001相对旧静态规则改善0.1601%，95%探索区间[-0.1685%,+0.6910%]，fit组外CV为-0.6347%；相对始终true总收益5.4392%。未证明稳定新增收益。</p>
<p>“免费Oracle”是假设预先知道每题两个相位的成本、每题选较小者、预测/提取费为零的理论参照。此60题旧静态成本331107.082，Oracle328185.791，剩余空间0.8823%。只有24题明确偏好标签；所有成本按TA的PAR2约定（超时记10000）计算，不能直接当实际省下的墙钟秒。</p>
<p>所有收益未扣除特征/探针费用；服务器CPU与TA另一硬件wall分列。新增已计量计算1077.183 CPU秒，约18核分钟；未计量工程保持unknown。新D192短前缀物理CPU218.720738481秒、wall29.7954秒：104合格、73缺失、15早解未验证未采纳。3项理由DAG字段只有7或10个fit观测、各1个feedback观测，应称覆盖不足。5列当前fit恒定。</p>
<p>基础字段：<code>s_positive_fraction</code>为正文字出现占比；<code>s_mean_length</code>为平均子句长度；<code>s_length_std</code>为子句长度标准差；<code>g_cycle_excess_per_incidence</code>为按incidence归一化环冗余；<code>s_mean_polarity_imbalance</code>为原提取器的按变量聚合正负不平衡均值。新字段的精确有界定义逐项列在后文。</p>
<p><b>执行语义：</b>下面树中所有数值保留原精度，左支为≤、右支为&gt;。资源资格不满足，或当前访问分支所需字段缺失/非有限时返回phase=true。低层分支未访问的字段无需存在；没有默认回退另一棵静态树。</p>
<p>100次使用开发反馈后的区间未做整个自适应搜索的多重校正，均为探索性结果；特征未选中不等于证明其无用。全部定义、来源、负结果、覆盖、误选、费用及10次workflow记录均包含在附件包内。</p>'''
    ranking='<h2>13种不同实际策略排名</h2><table><tr><th>排名</th><th>代表轮</th><th>相同规则轮数</th><th>相对旧静态增量</th><th>相对固定true总收益</th></tr>'
    for g in ordered:
        ranking+=f'<tr><td>{g["rank"]}</td><td><a href="#policy-{g["rank"]}">{g["representative_round"]}</a></td><td>{len(g["members"])}</td><td>{pct(g["gain_vs_old_static"])}</td><td>{pct(g["gain_vs_fixed_true"])}</td></tr>'
    ranking+='</table>'
    policy_sections=''
    for g in ordered:
        policy_sections+=f'<section id="policy-{g["rank"]}"><h3>策略{g["rank"]} · {g["representative_round"]}</h3>'+render_rule(g['policy'])
        policy_sections+='<p>对应轮次：'+esc(', '.join(g['members']))+'</p></section>'
    per_round='<h2>全部100轮特征、规则与结果</h2>'
    combined=[]
    for row in records:
        rid=row['round']; c=candidates[rid];r=raw[rid];m=r['evaluation']['metrics']
        d={'round':rid,'existing_ranking_row':row,'distinct_policy_rank':policy_for_round[rid],
           'feature_description':{k:c[k] for k in ['columns','plain_definition','formal_definition','formula','object','operator','conditioning','source_inspiration_urls','status_interpretation']},
           'observed':c['observed'],'numeric_diagnostics_fit_only':r['numeric_diagnostics_fit_only'],
           'policy':r['policy'],'result_path':row['result_path'],'result_sha256':row['result_sha256']}
        combined.append(d)
        fitobs=' / '.join(f'{k}: {v}/180' for k,v in r['coverage']['development_fit'].items())
        fbobs=' / '.join(f'{k}: {v}/60' for k,v in r['coverage']['development_feedback'].items())
        ci=m['bootstrap']['improvement_95']
        per_round+=f'<section id="round-{rid}"><h3>{rid} · {esc(c["name"])}</h3>'
        per_round+=f'<p>实际规则：<a href="#policy-{policy_for_round[rid]}">策略{policy_for_round[rid]}</a>；新增字段采用：{"是" if r["used_new_columns"] else "否"}。</p>'
        for label,key in [('字段','columns'),('描述','plain_definition'),('对象','object'),('操作','operator'),('条件/采样范围','conditioning'),('精确定义','formal_definition'),('公式','formula')]:
            per_round+=f'<p><b>{label}：</b><code>{esc(c[key])}</code></p>'
        per_round+=f'<p><b>覆盖：</b>fit {esc(fitobs)}；feedback {esc(fbobs)}。</p>'
        per_round+=f'<p><b>结果：</b>相对旧静态{pct(row["feedback_gain_vs_old_static"])}，相对固定true{pct(row["feedback_gain_vs_fixed_true"])}；fit组外CV{pct(row["fit_group_cv_gain"])}；探索95%区间[{pct(ci[0])}, {pct(ci[1])}]。</p>'
        per_round+=f'<p>所选成本{m["policy_total_cost_s"]:.6f}，旧静态成本{m["baseline_total_cost_s"]:.6f}；切换{m["switches"]}题，其中明确偏好{m["clear_switches"]}题；最大单题误选新增成本{m["max_regression_s"]:.6f}（TA PAR2成本单位）。</p>'
        per_round+='<p>状态说明：'+esc(c['status_interpretation'])+'；fit诊断：<code>'+esc(json.dumps(r['numeric_diagnostics_fit_only'],ensure_ascii=False))+'</code>。</p>'
        per_round+='<p>来源：'+'；'.join(f'<a href="{esc(u)}">{esc(u)}</a>' for u in c['source_inspiration_urls'])+'</p></section>'
    (DELIVERY/'ALL_100_RULES_AND_RESULTS.json').write_text(json.dumps(combined,ensure_ascii=False,indent=2)+'\n')
    revisions='<h2>10次workflow修订原文</h2>'
    for p in sorted((ROOT/'refine-logs/ta100').glob('workflow_revision_*.md')):
        revisions+='<details><summary>'+esc(p.name)+'</summary><pre>'+esc(p.read_text())+'</pre></details>'
    css='body{font:16px/1.6 system-ui,sans-serif;max-width:1200px;margin:32px auto;padding:0 20px;color:#17202a}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd1d1;padding:7px;text-align:left}th{background:#eaf2f8}section{border-top:1px solid #ccd1d1;margin-top:24px;padding-top:8px}code,pre{white-space:pre-wrap;overflow-wrap:anywhere;font-family:monospace}pre{background:#f4f6f6;padding:12px}a{color:#1261a0}'
    document='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TA100完整规则与结果</title><style>'+css+'</style><body>'+intro+ranking+'<h2>13种实际规则的完整条件</h2>'+policy_sections+per_round+revisions+'</body></html>'
    html_path=DELIVERY/'TA100_COMPLETE_REPORT.html';html_path.write_text(document)
    readme='''# TA100完整规则与结果

先打开 reports/ta100/email_delivery/TA100_COMPLETE_REPORT.html：包含13种不同实际策略的全精度规则、100轮特征定义/来源/覆盖/结果，以及10次workflow修订。

100轮不等于100种不同最终策略：88轮没有采用新增字段，重复得到旧静态规则；共13种不同决策树。排名前10只是13种中的前10，负增量也保留。

all_13_policies.py提供choose_phase(rank,features,eligible=True)，rank为1..13，features须来自原定义的提取器。不会自动采集特征或运行SAT。缺失/非有限的当前分支字段、资源资格不满足时选true。

ALL_100_RULES_AND_RESULTS.json是逐轮定义/结果/模型的汇总，LEADERBOARD.csv是已有100轮排名。outputs/ta100/B01..B10保留全部原始逐轮结果、逐题预测、五折结果、proposal及完成标记；configs/src/refine-logs保留冻结定义、源码、协议和workflow。MANIFEST.json列文件SHA。

指标是TA原false/true计时的PAR2约定（超时10000），不是新增测得wall。数据角色为180fit/60feedback、192合格采集项；所有结果都是探索性，未使用gate或最终测试，未证明部署净加速。服务器CPU和TA wall分列。每轮原始模型不变，本次仅包装既有记录发送邮件。
'''
    (DELIVERY/'README_ZH.md').write_text(readme)
    selected={p.relative_to(ROOT).as_posix():p for p in REPORTS.iterdir() if p.is_file() and p.suffix in ('.md','.json','.csv','.py')}
    for folder,pattern in [(ROOT/'outputs/ta100','B??/**/*.json'),(ROOT/'outputs/ta100','features*.json'),
            (ROOT/'configs/ta100','*.json'),(ROOT/'src/ta100','**/*.py'),(ROOT/'src/ta100','**/*.cpp'),
            (ROOT/'src/ta100','**/*.hpp'),(ROOT/'src/ta100','**/*.json'),(ROOT/'refine-logs/ta100','*.md')]:
        for p in folder.glob(pattern):
            if p.is_file() and '__pycache__' not in p.parts:selected[p.relative_to(ROOT).as_posix()]=p
    for name in ['ALL_13_POLICIES.json','all_13_policies.py','ALL_100_RULES_AND_RESULTS.json','TA100_COMPLETE_REPORT.html','README_ZH.md']:
        p=DELIVERY/name
        selected[p.relative_to(ROOT).as_posix()]=p
    for rel in ['outputs/ta_feature_discovery/development_static_v2.json','outputs/ta_feature_discovery/TA_R01/matched_simple_tree.json','src/ta_feature_discovery/learning.py']:
        selected[rel]=ROOT/rel
    manifest={'scope':'Existing TA100 permitted fit/feedback evidence only. No gate/test, credentials or remote connection state.',
        'files':{rel:{'sha256':sha(p),'bytes':p.stat().st_size} for rel,p in sorted(selected.items())}}
    manifest_path=DELIVERY/'MANIFEST.json';manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    archive=DELIVERY/'TA100_ALL_RULES_AND_RESULTS.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for rel,p in sorted(selected.items()):z.write(p,rel)
        z.write(manifest_path,'MANIFEST.json')
        z.write(DELIVERY/'README_ZH.md','README_ZH.md')
    if archive.stat().st_size>15_000_000:raise ValueError('archive exceeds chosen email size envelope')
    body='<div style="font:15px/1.6 sans-serif">'+intro+ranking+'<h2>13条实际规则（完整阈值）</h2>'+policy_sections+'''<h2>附件说明</h2><ul>
<li><b>TA100_COMPLETE_REPORT.html</b>：离线可读，含全部100轮详细定义、公式、来源、覆盖、结果和13条完整规则。</li>
<li><b>TA100_LEADERBOARD.csv</b>：全部100轮排名、增益、区间、覆盖、误选与原结果身份。</li>
<li><b>TA100_ALL_RULES_AND_RESULTS.zip</b>：完整研究记录，包括原始逐轮结果/逐题预测/五折、所有规则JSON及Python、特征表、源码、协议、10次workflow和文件SHA清单。</li></ul>
<p>这是你本次明确要求发送的完整结果邮件。100轮已结束，没有因打包而新增求解、拟合或评分。</p></div>'''
    parts=[{'mime_type':'text/html','charset':'UTF-8','body':{'content':body}}]
    attachments=[]
    for p,name,mime in [(html_path,'TA100_COMPLETE_REPORT.html','text/html'),(REPORTS/'LEADERBOARD.csv','TA100_LEADERBOARD.csv','text/csv'),(archive,archive.name,'application/zip')]:
        parts.append({'mime_type':mime,'filename':name,'content_disposition':'attachment',
            'body':{'base64_url_content':base64.urlsafe_b64encode(p.read_bytes()).decode()}})
        attachments.append({'filename':name,'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)})
    payload={'mime_type':'multipart/mixed','parts':parts}
    payload_path=WORK/'mime_payload.json';payload_path.write_text(json.dumps(payload,ensure_ascii=True,separators=(',',':')))
    metadata={'recipient':'ccmuagent@gmail.com','subject':SUBJECT,'payload_path':str(payload_path),
        'payload_bytes':payload_path.stat().st_size,'payload_sha256':sha(payload_path),'attachments':attachments,
        'rounds':100,'distinct_policies':13,'same_old_policy_rounds':88,'new_scoring':False,'status':'PREPARED_NOT_SENT'}
    (DELIVERY/'PREPARED.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(metadata,ensure_ascii=False))


if __name__=='__main__':main()
