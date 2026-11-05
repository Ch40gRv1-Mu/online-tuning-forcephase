"""Publish compact, user-facing progress artifacts without exposing access details."""
from pathlib import Path
import csv, html, json, shutil, zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = Path('/Users/expexp/Documents/Codex/2026-10-28/new-chat/outputs/forcephase_autoresearch')

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ('AUTORESEARCH_WORKFLOW.md', 'findings.md', 'research-log.md'):
        shutil.copy2(ROOT/name, OUT/name)
    source = ROOT/'experiments/H01_cost_aware_static_rule'
    target = OUT/'H01_static_rule'
    target.mkdir(exist_ok=True)
    shutil.copy2(source/'analysis.md', target/'analysis.md')
    shutil.copy2(source/'protocol.md', target/'protocol.md')
    for file in (source/'results').iterdir():
        if file.is_file():
            shutil.copy2(file, target/file.name)
    later=[]
    for exp_name in ('H02_signed_clause_asymmetry','H03_root_propagation_residual','H04_short_original_D_trace'):
        exp=ROOT/'experiments'/exp_name
        if not (exp/'analysis.md').exists():
            continue
        dest=OUT/exp_name;dest.mkdir(exist_ok=True)
        for name in ('analysis.md','protocol.md'):
            shutil.copy2(exp/name,dest/name)
        for file in (exp/'results').iterdir():
            if file.is_file() and file.suffix in ('.json','.jsonl','.csv','.txt','.log'):
                shutil.copy2(file,dest/file.name)
        mm=list(csv.DictReader((exp/'results/metrics.csv').open()))
        chosen=[r for r in mm if r['cohort']=='combined300' and 'measured' in r['path']][0]
        later.append(f'<article><small>{html.escape(exp_name)}</small><strong>{(float(chosen["cost_ratio"])-1)*100:+.3f}%</strong><p>留出家族成本变化，计入特征开销</p><p>明确题准确率 {float(chosen["accuracy"]):.1%}；切换 {chosen["switch_n"]} 题。</p><a href="{exp_name}/analysis.md">查看结果与限制</a></article>')
    rows = list(csv.DictReader((source/'results/metrics.csv').open()))
    h01 = [r for r in rows if r['cohort']=='combined300']
    cards = ''.join(f'<article><small>{html.escape(r["path"])}</small><strong>{(float(r["cost_ratio"])-1)*100:+.2f}%</strong><p>相对直接D的成本变化</p><p>明确题准确率 {float(r["accuracy"]):.1%}</p></article>' for r in h01)
    text = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Forcephase autoresearch</title><style>
    :root{font-family:system-ui,sans-serif;color:#172d38;background:#f2f5f2}body{max-width:1050px;margin:auto;padding:36px 22px}h1{font-size:38px;line-height:1.2}h2{font-size:24px;margin-top:38px}p,li{line-height:1.8}small{color:#587073}.tag{background:#dcecdf;color:#1e633c;display:inline-block;border-radius:24px;padding:5px 14px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:15px}article{background:white;border:1px solid #d8e2da;border-radius:15px;padding:23px}strong{display:block;font-size:32px;margin:14px 0 0}.flow{display:flex;flex-wrap:wrap;gap:10px}.step{background:#173e40;color:white;padding:12px 16px;border-radius:9px}td,th{text-align:left;padding:13px;border-bottom:1px solid #d1dbd5}table{border-collapse:collapse;width:100%}a{color:#146c6b}.note{border-left:4px solid #8ba89a;padding-left:16px}footer{margin-top:38px;color:#587073}button{cursor:pointer;background:#173e40;color:white;border:0;border-radius:8px;padding:10px 15px}summary{cursor:pointer}</style>
    <span class="tag">研究目标 ACTIVE · 每20分钟继续</span><h1>寻找简单、便宜、持续有效的<br>F+ / F− / D 选择特征</h1><p>输入原题，用最多两个特征和两层规则做选择。证据不足时回退D。有效性由新题、跨家族、重复运行与实际净收益共同判断。</p>
    <div class="flow"><span class="step">假设与机制</span>→<span class="step">先锁定协议</span>→<span class="step">正式实验</span>→<span class="step">成本与泛化</span>→<span class="step">保留正负结果</span>↻</div>
    <h2>什么才算 consistent？</h2><div class="grid"><article><small>成本</small><strong>≥1% 净节省</strong><p>计入特征与探测开销，家族区间支持优于D；两个固定新区块均保持收益。</p></article><article><small>预测</small><strong>≥5 个百分点</strong><p>明确题准确率相对D提高，区间下界大于零。切换覆盖至少20%，触发准确率至少75%。</p></article><article><small>重复</small><strong>3 seeds + 重跑</strong><p>各seed保持收益方向，明确赢家一致率至少80%。新家族证据单独报告。</p></article></div>
    <p class="note">这些是提前设定的研究门槛，不是当前已经达到的结果。样本不足就写证据不足；找不到也保留完整否定结论。</p>
    <h2>第一轮：原始静态单阈值未通过</h2><div class="grid">__CARDS__</div><p>69道明确题上，直接D准确率47.8%。完整开发集拟合最终回退D，没有可进入确认的候选。上面的收费路径尚未计入单独根传播时间，只作部分成本估计。</p>
    <h2>后续路线</h2><table><thead><tr><th>假设</th><th>检验内容</th><th>当前状态</th></tr></thead><tbody><tr><td>H01</td><td>原始静态特征，单阈值与回退D</td><td>完成 · 负结果</td></tr><tr><td>H02</td><td>纯正/纯负子句与长度加权不对称</td><td>协议已锁定 · 下一步</td></tr><tr><td>H03</td><td>根传播后剩余结构的变化</td><td>待检验</td></tr><tr><td>H04</td><td>极短D原题轨迹</td><td>待检验</td></tr><tr><td>H05</td><td>极短F+/F−响应差异</td><td>待检验</td></tr><tr><td>H06</td><td>固定少量变量后的纯传播差分</td><td>待检验</td></tr></tbody></table>
    <h2>数据与研究边界</h2><p>已有300题仅用于探索：69个明确赢家、46个明确标签家族，291个有效成本三元组。最多6类假设，最终仅一个冻结候选进入最多160个新父题确认；不根据确认结果继续调规则。</p><p>沿用8CPU服务器，独立任务动态补位，parent预算60秒；不做独立audit或dryrun。正式结果仍验证模型或证明。每两类假设总结一次，有实质变化才通知。</p>
    <details><summary>查看完整工作流与第一轮数据</summary><p><a href="AUTORESEARCH_WORKFLOW.md">完整协议与成功标准</a> · <a href="findings.md">累计认识</a> · <a href="H01_static_rule/metrics.csv">H01全部指标</a> · <a href="H01_static_rule/predictions.csv">逐题留出预测</a></p></details><footer>2026-10-29 · 研究已启动；尚未发现稳定可部署特征。阈值或预算变更需在下一协议中明确记录。</footer></html>'''
    text=text.replace('__CARDS__',cards)
    if later:
        text=text.replace('<h2>后续路线</h2>','<h2>后续正式探索结果</h2><div class="grid">'+''.join(later)+'</div><p>H02退回D；H03及H04未带来开销后的净收益。当前没有进入新题确认的候选。</p><h2>后续路线</h2>')
        text=text.replace('协议已锁定 · 下一步','完成 · 无切换候选')
        text=text.replace('<td>根传播后剩余结构的变化</td><td>待检验</td>','<td>根传播后剩余结构的变化</td><td>完成 · 未通过泛化</td>')
        text=text.replace('<td>极短D原题轨迹</td><td>待检验</td>','<td>极短D原题轨迹</td><td>下一步</td>')
        if (ROOT/'experiments/H04_short_original_D_trace/analysis.md').exists():
            text=text.replace('<td>极短D原题轨迹</td><td>下一步</td>','<td>极短D原题轨迹</td><td>完成 · 开销超过收益</td>')
            text=text.replace('<td>极短F+/F−响应差异</td><td>待检验</td>','<td>极短F+/F−响应差异</td><td>协议已锁定 · 下一步</td>')
    (OUT/'index.html').write_text(text)
    with zipfile.ZipFile(OUT.parent/'forcephase_autoresearch_setup.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(OUT.rglob('*')):
            if path.is_file():
                z.write(path, path.relative_to(OUT))
    print(json.dumps(dict(html=str(OUT/'index.html'), archive=str(OUT.parent/'forcephase_autoresearch_setup.zip'))))

if __name__ == '__main__':
    main()
