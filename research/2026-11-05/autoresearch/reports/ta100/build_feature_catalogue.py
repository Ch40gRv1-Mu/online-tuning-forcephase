#!/usr/bin/env python3
"""Document frozen TA100 proposals and existing metadata; never fit or rescore.

The required cross-block feature dedup is computed FIRST from FIT numeric inputs
only. No result/feedback outcome is an argument to that calculation. Later report
assembly copies existing coverage and fit diagnostics without changing results.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / 'reports/ta100'
CACHE = {}
INPUT_SHA = {}


def read(relative):
    relative = str(relative)
    if relative not in CACHE:
        path = ROOT / relative
        if not path.exists():
            return None
        raw = path.read_bytes()
        CACHE[relative] = json.loads(raw)
        INPUT_SHA[relative] = hashlib.sha256(raw).hexdigest()
    return CACHE[relative]


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def support_sha(rows):
    return hashlib.sha256('\n'.join(h for h, _ in rows).encode()).hexdigest()


def fit_only_dedup(vectors, ids):
    """Formal reporting diagnostic. Argument contains FIT features, no labels."""
    exact, monotone, constants, noobs = defaultdict(list), defaultdict(list), [], []
    for column, rows in vectors.items():
        support = tuple(h for h, _ in rows)
        values = tuple(v for _, v in rows)
        if not values:
            noobs.append({'column': column, 'round_id': ids[column]})
            continue
        levels = sorted(set(values))
        if len(levels) == 1:
            constants.append({'column': column, 'round_id': ids[column], 'fit_support': len(rows), 'support_sha256': support_sha(rows), 'observed_value': levels[0]})
            continue
        exact[(support, values)].append(column)
        rank = {v: j for j, v in enumerate(levels)}
        ranks = tuple(rank[v] for v in values)
        inverse = tuple(len(levels) - 1 - r for r in ranks)
        monotone[(support, min(ranks, inverse))].append(column)
    def groups(mapping):
        out = []
        for (support, _), columns in mapping.items():
            if len(columns) > 1:
                out.append({'columns': sorted(columns), 'round_ids': sorted(ids[c] for c in columns), 'fit_support': len(support), 'support_sha256': hashlib.sha256('\n'.join(support).encode()).hexdigest(), 'semantic_resolution': 'REQUIRES_ROOT_NONALIAS_WITNESS_OR_REPLACEMENT; finite-panel equivalence alone is not a proof of mechanism identity.'})
        return out
    high = []
    for a, b in itertools.combinations(sorted(vectors), 2):
        x, y = vectors[a], vectors[b]
        if len(x) < 2 or tuple(h for h, _ in x) != tuple(h for h, _ in y):
            continue
        mx, my = math.fsum(v for _, v in x) / len(x), math.fsum(v for _, v in y) / len(y)
        dx, dy = [v - mx for _, v in x], [v - my for _, v in y]
        xx, yy = math.fsum(v*v for v in dx), math.fsum(v*v for v in dy)
        if not xx or not yy:
            continue
        r = math.fsum(u*v for u, v in zip(dx, dy)) / math.sqrt(xx*yy)
        if abs(r) >= .995:
            high.append({'columns': [a, b], 'round_ids': [ids[a], ids[b]], 'fit_support': len(x), 'support_sha256': support_sha(x), 'pearson_r': max(-1., min(1., r)), 'interpretation': 'FINITE_PANEL_HIGH_CORRELATION_ONLY; not semantic duplication and not a new outcome/acceptance criterion.', 'semantic_resolution': 'Compare frozen object/operator definitions; retain a nonalias witness or flag for root review.'})
    return {'schema': 'ta100.required_fit_only_feature_dedup.v1', 'scope': 'Only FIT numeric feature values; identical nonempty observation-ID support required. No labels, feedback values/results, model fits or rescoring.', 'same_support_rule': 'Entire observation support must match; no intersection-only comparisons.', 'exact_value_groups': groups(exact), 'monotonic_tie_pattern_groups': groups(monotone), 'high_pearson_threshold_diagnostic_only': .995, 'high_pearson_pairs': high, 'constants': constants, 'no_observation_columns': noobs, 'available_columns_checked': len(vectors), 'scheduled_columns': len(ids), 'all_scheduled_columns_checked': set(vectors) == set(ids), 'missing_feature_tables_for_rounds': sorted(ids[c] for c in ids if c not in vectors), 'semantic_alias_note': 'Constant/no-observation rows are reported as uninformative on this panel. They do not establish an original invention or create extra iterations. High correlations do not force a mechanism merge.'}


GRAPH = [
 ('变量—子句边','度与arity的Pearson相关','完整非重言 incidence；零端点方差缺失'),
 ('文字sign与子句arity','归一化互信息','固定arity桶；sign熵为零缺失'),
 ('Horn/非Horn共享变量','共享incidence质量','非重言原始输入；无UP'),
 ('共同出现在子句中的变量对','butterfly重叠碰撞计数','完整有界pair枚举；超限缺失'),
 ('无向incidence图','递归2-core剥离','剥离到固定点；无赋值'),
 ('无向图单变量割点','最大被割开变量对质量','完整incidence图；不使用有向SCC'),
 ('无符号归一化邻接算子','S^4随机trace/返回估计','8个固定探针；不是signed leading-mode'),
 ('变量共现primal图','三角形/闭合wedge比例','精确有界投影；超限缺失'),
 ('已验证AND数据流','中间输出fanout共享','只用无歧义完整门模板'),
 ('恢复电路与残余约束','输出在非门子句中的incidence比例','已识别门定义并集外部界面'),
 ('有界incidence样本的社区','四轮label传播后的modularity','≤128节点固定样本；非全图最优值'),
 ('图距离几何','半径1/2/4球覆盖的log斜率','≤128节点样本；非全图fractal维数证书'),
 ('incidence非平面wiring','K3,3共同邻居见证率','有界变量三元组；零不证明平面'),
 ('primal样本分解','贪心min-fill消除宽度','≤96变量诱导样本；非全图treewidth证书'),
 ('多点随机删除后的连接','最大分量曲线AUC','固定删除率与种子；非逻辑restriction'),
 ('无向最短路径流','最大归一化betweenness','固定16个源的有界样本'),
 ('变量对距离','倒数距离平均','有界样本；不连通对计零'),
 ('删去单边后的替代路径','倒数detour长度平均','≤32样本边；断开取零'),
 ('不立即反向的有向边walk','三步nonbacktracking增长','有界样本；非普通walk返回率'),
 ('无符号support超图','GYO删除后的剩余质量','有界sample；与signed subsumption不同'),
 ('子句support对','相交但互不包含的crossing比例','有界support集合'),
 ('support set-system','三变量八种交集mask的shattering见证','有界三元组；无literal sign或SAT判定'),
 ('无符号incidence的平衡cut','cross-cut GF2 rank','固定16个样本cut；非逻辑XOR rank'),
 ('primal诱导图','MCS后邻居非clique缺陷','≤96变量；与宽度阈值不同'),
 ('四点距离结构','归一化Gromov delta','≤128个连通quadruple'),
 ('六子句majority/carry关系','完整MAJ门输出覆盖','要求全部六句；不计XOR/ITE'),
 ('门依赖fanin','两hop共同祖先reconvergence','唯一、完整门；截断cone不作零'),
 ('门输出literal','signed AND输出正负方向差','保留绝对输出orientation'),
 ('变量的局部函数定义','多个完整定义的歧义比例','精确重复不是新定义'),
 ('signed input-pair函数类','重复计算同函数的congruence','不要求输出变量拥有相同外部邻域'),
 ('可求值组合门cone','CC0/CC1 forcing-cost递推','排除歧义/循环部分并记录coverage'),
 ('界面向内部的门cone','反向CO observability递推','相同可求值gate portion'),
 ('两hop signed祖先集合','同源相反sign的binate比例','有界cone；非无符号reconvergence'),
 ('3–4变量局部Boolean关系','非保留模板的total函数决定性','排除affine/AND/OR/MAJ/ITE/cardinality'),
 ('局部Boolean满足谓词','最大嵌套canalization深度','≤16 truth rows；固定有界support'),
 ('局部Boolean满足谓词','GF2 ANF最高非零次数','排除affine；不是实数energy Walsh'),
 ('同arity的clause sign-count','相对独立二项分布的KL','width1..64条件人口；非clause-pair subcube'),
 ('样本社区的编码方向','社区间signed bias加权方差','复用固定partition，仅样本变量'),
 ('邻接节点的lazy邻域测度','16×16最小成本transport曲率','≤32边；经验邻居测度非全图证书'),
 ('primal clique二复形','triangle-boundary GF2同调beta1','≤96变量；三角形填充后留下的hole'),
]
CORE = [
 ('原始子句的signed literals','原始宽度减去去重宽度','共享parser原始统计'),
 ('单个原始子句','互补literal是否同句','不把普通重复当重言'),
 ('短canonical子句多重集','相同signed clause重复率','固定短子句上下文'),
 ('signed子句包含关系','较短子句subsumes较长子句','固定context与完整环境检查'),
 ('含pivot的子句对','self-subsuming resolution可缩短率','width4与完整证书'),
 ('pivot的正负occurrence','Davis–Putnam潜在交叉fanout','输入静态计数；非实际solver消解'),
 ('有界resolution parents','resolvent重言比例','有界parent与partner环境'),
 ('原始clause/literal环境','blockedness与signed对比','所有所需partner检查完成才有值'),
 ('原始变量列','完全相同occurrence列twins','精确全列相等；非graph WL近似'),
 ('majority参考赋值','单变量flip收益','静态固定赋值；不是双翻合作逃逸'),
]
ROOT_OBJECTS = [
 ('变量sign重命名与子句正literal对','12轮coordinate下降','F*；不称精确renamable-Horn'),
 ('signed pairwise coupling J','12轮spin下降后的frustration','F*；有非零|J|质量'),
 ('raw signed coupling J','负系数|J|质量比例','原坐标；不进行gauge优化'),
 ('完整signed clause多重集','literal-complement配对','F*；保留重复row'),
 ('固定majority下的变量集合','验证后的autarky剥离固定点','F*；≤128轮且实际条件验证'),
 ('clause-variable二部图','精确最大matching deficiency','F*；空子句为unmatched row'),
 ('变量不相交clauses与hitting变量','贪心cover-packing差','F*；空子句使cover未定义'),
 ('signed J与线性bias h','16步mode与h绝对对齐','F*；零mode或bias范数缺失'),
 ('分数变量的convex hinge目标','64步投影subgradient后的方向','F*；固定算法，非LP最优解'),
 ('OR-factor cavity messages','12轮同步阻尼BP后的方向','F*；clamp固定，不称真实marginal'),
 ('signed clause-row实数矩阵','Gaussian numerical rank deficiency','first64 F*行；≤1024列；1e-9 pivot'),
 ('实数unsatisfied-clause-count energy','degree≥3 Walsh平方质量','first128 F* width≤8；保留duplicate'),
 ('canonical-name signed token流','LZ78描述比','F*首次出现变量编号；明确order-sensitive'),
 ('majority附近LOCALcube','双翻优于所有单翻的合作比例','top12 degree变量，其余固定majority'),
 ('相同energy的LOCALcube子图','参考点所在中性连通分量','q=0前瞻缺失；非单翻gain'),
 ('LOCALcube上固定noisy walk状态','128步state recurrence','seed0；总129状态；允许uphill'),
 ('同一walk触及的clauses','持续129状态均unsat的约束比例','仅触及local core且曾unsat的clauses'),
 ('clause-pair falsifying subcubes','精确joint-product相对差','F*所有pair；不是within-clause KL'),
]
DYNAMIC = [
 ('主冲突回退事件','chronological份额','共同native-D动作前前缀'),
 ('自然restart事件','保留决策层的份额','不以restart频率代替'),
 ('target/saved/其余phase来源','来源分布归一化熵','同一checkpoint三个互斥来源桶'),
 ('已定义target的活跃变量样本','target覆盖比例','固定变量样本；未知值保留缺失'),
 ('best与target进度记忆','归一化signed lag','共同checkpoint的两个记忆状态'),
 ('trail长度EMA','快/慢前沿momentum','当前solver mode动作前状态'),
 ('保留的学习数据库','冗余/不可冗余数据库负荷','共同checkpoint；不读终局'),
 ('target与saved phase向量','两者负phase边际差','target已定义样本与完整活跃样本'),
 ('学习子句宽度EMA/前缀累计均值','宽度regime shift','共同prefix与当前mode，不能混终局'),
 ('actual backtrack与potential jump层','归一化保留层差','与冲突层/平均jump分别定义'),
 ('新学习clause的sign构成','全正/全负coherence差','非空学习clauses；未到checkpoint缺失'),
 ('有唯一决策祖先的隐含赋值','祖先sign传播对齐','固定sample与唯一祖先条件'),
 ('已完整观测的赋值生命周期','负/正平均存活期差','明确发生撤销；右删失不伪造'),
 ('主冲突resolution使用的reasons','不同reason数/最终1UIP宽度','最终有效学习clause事件'),
 ('冲突literal到决策/root的reason链','最长祖先路径深度中位数','固定冲突literal sample'),
 ('reason祖先遍历边','重新访问祖先的reconvergence','固定有界祖先遍历'),
 ('当前decision level的trail','1UIP到层尾相对位置','最终1UIP与当前层trail长度'),
 ('学习clause按decision level的占比','normalized level entropy','单层clause按冻结定义取0'),
 ('完整已定义TARGET向量下的学习clause','TARGET全部否定兼容率','仅完整可评价事件；替换旧TD19'),
 ('相邻128冲突窗口的分析变量集','bottom-k Jaccard turnover','固定k256与seed；非精确全set声称'),
 ('冲突分析variable bump计数','Herfindahl注意力集中度','共同动作前prefix；非原始activity尺度'),
 ('最近学习clause变量与checkpoint activity rank','top decile enrichment','当前动作前rank，非历史pre-bump rank'),
 ('相邻128学习clause窗口','signed minhash最近复发相似度','每clause固定8 minhash'),
 ('学习lemma首次后续reason复用','跳过birth assertion的复用年龄','bottom-k256；右删失；替换旧TD24'),
 ('传播watch entries','blocking-literal shortcut成功率','只加计数，不改变watch顺序'),
 ('restart前后相同变量赋值','负/正same-sign保留率差','同256样本，两个sign均需支持'),
 ('chrono撤销后同变量下次decision','signed redecision transition','匹配后消费状态，非边际saved比例'),
 ('相邻冲突的decision gap','renewal burstiness/CV','至少32个间隔；非mean rate'),
 ('学习clause width与glue联合桶','有序桶相关','81格；常数边缘分布缺失'),
 ('学习clause之间的reason证明祖先','lemma依赖深度累积','原始reasons深度0；溢出缺失'),
]


def metadata_triplet(registry_id):
    if registry_id.startswith('S') and registry_id[1:].isdigit():
        return GRAPH[int(registry_id[1:])-1]
    if registry_id.startswith('RA'):
        return ROOT_OBJECTS[int(registry_id[2:])-1]
    if registry_id.startswith('TD'):
        number = int(registry_id[2:].replace('v2',''))
        return DYNAMIC[number-1]
    if registry_id.startswith('nodes_'):
        return CORE[int(registry_id.split('_')[1])-1]
    if registry_id == 'NODE_EX01':
        return ('covered-literal resolution候选环境','非重言RC的literal intersection减去原clause','first256 context；完整admitted complementary环境')
    if registry_id == 'NODE_EX02':
        return ('四个不同变量的ITE/MUX关系','完整四子句输出覆盖','first256 ternary context；四句必须齐备')
    raise ValueError(registry_id)


def source_info(registry, candidate, extra=None):
    urls = list(candidate.get('source_urls') or candidate.get('sources') or [])
    if candidate.get('source_ids'):
        for source in candidate['source_ids']:
            item = registry.get('source_registry', {}).get(source, {})
            if item.get('url') and item['url'] not in urls:
                urls.append(item['url'])
    for source in candidate.get('primary_sources', []):
        item = registry.get('sources', {}).get(source)
        if isinstance(item, str):
            urls.append(item)
        elif isinstance(item, dict):
            url = item.get('url') or item.get('source_url')
            if url:
                urls.append(url)
    if extra and extra.get('source_url'):
        urls.append(extra['source_url'])
    return list(dict.fromkeys(urls))


def main():
    proposals = []
    for number in range(1, 11):
        path = f'configs/ta100/B{number:02d}.json'
        block = read(path)
        registry = read(block['registry_path'])
        if INPUT_SHA[block['registry_path']] != block['registry_sha256']:
            raise ValueError(f'frozen catalogue registry identity mismatch: {path}')
        candidates = {r.get('id', r.get('candidate_id')): r for r in registry['candidates']}
        for proposal in block['rounds']:
            candidate = candidates[proposal['registry_id']]
            proposals.append((path, block, registry, proposal, candidate))
    ids = {c: p['id'] for _, _, _, p, _ in proposals for c in p['columns']}
    if len(proposals) != 100 or len(ids) != 100 or len({p['mechanism_key'] for _,_,_,p,_ in proposals}) != 100:
        raise ValueError('catalogue requires exactly100 scheduled distinct frozen keys')
    roles = {t['instance_id']: t['role'] for t in read('configs/ta_feature_discovery/public_eligible192.json')['tasks']}
    tables = []
    for path in sorted((ROOT/'outputs/ta100').glob('features*.json')):
        relative = str(path.relative_to(ROOT))
        table = read(relative)
        if isinstance(table.get('features'), dict):
            tables.append((relative, table))
    selected = {}
    vectors = {}
    # FIT-only dedup is completed before any scoring result is opened.
    for column in ids:
        matches = [(p,t) for p,t in tables if column in t.get('columns', [])]
        if len(matches) > 1:
            raise ValueError(f'ambiguous feature table provenance for {column}')
        if not matches:
            continue
        path, table = matches[0]
        selected[column] = (path, table)
        vectors[column] = tuple((h, float(row[column])) for h,row in sorted(table['features'].items()) if roles.get(h) == 'development_fit' and finite(row.get(column)))
    dedup = fit_only_dedup(vectors, ids)
    dedup['feature_table_sha256'] = {p: INPUT_SHA[p] for p, _ in tables}
    dedup['generated_utc'] = datetime.now(timezone.utc).isoformat()
    # Reporting stage below copies completed records. It does not feed dedup.
    node_extra = read('work/ta100/core_extra_definitions.json')
    node_fields = {r['feature_key']:r for r in node_extra['fields']}
    entries = []
    for config_path, block, registry, proposal, candidate in proposals:
        registry_id, columns = proposal['registry_id'], proposal['columns']
        column = columns[0]
        extra = node_fields.get(column)
        source = candidate
        if extra:
            source = {**candidate, **extra}
        object_name, operator, conditioning = metadata_triplet(registry_id)
        definition = source.get('primary_definition') or source.get('definition') or source.get('formal_definition') or source.get('formula') or proposal['hypothesis']
        name = source.get('name') or source.get('title') or source.get('formal_definition') or source.get('feature_name') or ({'NODE_EX01':'覆盖literal交集暴露','NODE_EX02':'完整ITE输出覆盖'}.get(registry_id)) or registry_id
        plain = source.get('mechanism') if registry_id.startswith(('S','RA')) else None
        if not plain or isinstance(plain, list):
            plain = source.get('formal_definition') or source.get('title') or source.get('name') or definition
        kind = 'native_solver_dynamic' if registry_id.startswith('TD') else 'input_side'
        computation_type = ('native_solver_prefix' if registry_id.startswith('TD') else 'input_auxiliary_trajectory' if registry_id in ['RA16','RA17'] else 'input_auxiliary_landscape' if registry_id in ['RA14','RA15'] else 'input_fixed_iteration' if registry_id in ['RA01','RA02','RA05','RA08','RA09','RA10'] else 'input_structural_or_algebraic')
        result_path = f"outputs/ta100/{block['block_id']}/{proposal['id']}/result.json"
        result = read(result_path)
        observed = {'fit_population':180, 'feedback_population':60, 'eligible_fit_population':144, 'eligible_feedback_population':48, 'fit':None, 'feedback':None, 'table_terminal':False}
        collection_identity = None
        table_path = None
        if column in selected:
            table_path, table = selected[column]
            observed['table_terminal'] = bool(table.get('complete'))
            counts = Counter()
            for h,row in table['features'].items():
                if finite(row.get(column)):
                    counts[roles.get(h, 'unknown')] += 1
            observed['fit'], observed['feedback'] = counts['development_fit'], counts['development_feedback']
            observed['eligible_total_observed'] = counts['development_fit'] + counts['development_feedback']
            observed['eligible_total_population'] = 192
            observed['source'] = 'Exact count of already-published numeric feature cells; no target/performance labels.'
            statuses = Counter()
            for h,status in table.get('statuses', {}).items():
                block_status = status.get('blocks', {}).get(column, status.get('status', 'UNKNOWN'))
                statuses[block_status] += 1
            observed['published_block_status_counts_eligible192'] = dict(statuses)
            observed['collection_parent_status_counts_eligible192'] = table.get('terminal_status_counts') or table.get('availability', {}).get('statuses') or {}
            bindings = table.get('bindings', {})
            collection_identity = {k:v for k,v in bindings.items() if k not in ['receipts']}
        numeric_diagnostics = result.get('numeric_diagnostics_fit_only', []) if result else []
        if result and result.get('status') == 'COMPLETE':
            status = 'SCORED_COMPLETE'
            for role, short in [('development_fit','fit'), ('development_feedback','feedback')]:
                if column in result.get('coverage', {}).get(role, {}):
                    observed[short] = result['coverage'][role][column]
            interpretation = '被训练程序采用' if result.get('used_new_columns') else '未被训练程序采用'
            if any(d.get('kind') == 'observed_constant' for d in numeric_diagnostics):
                interpretation = '训练面板中恒定；已记录该负结果'
            if any(d.get('kind') in ['no_observations','no_observation'] for d in numeric_diagnostics):
                interpretation = '训练面板无观测；已记录缺失'
        else:
            status = 'FEATURES_PUBLISHED_SCORING_PENDING' if table_path else 'WAITING_FEATURE_COLLECTION'
            interpretation = '待既有正式结果，未推测效果'
        manifest_path = None
        if kind == 'input_side':
            manifest_path = 'configs/ta100/' + ('core10_manifest_v1.json' if column.startswith('f_core_') and registry_id.startswith('nodes_') else 'graph10_manifest_v1.json' if registry_id in [f'S{i:02d}' for i in range(1,11)] else 'graph_all30_manifest_v1.json' if registry_id.startswith('S') else 'algebra20_manifest_v1.json')
        elif registry_id not in [f'TD{i:02d}' for i in range(1,11)]:
            manifest_path = 'configs/ta100/new_dynamic192_manifest_v1.json'
        if manifest_path:
            read(manifest_path)
        entry = {
            'round_id':proposal['id'], 'block_id':block['block_id'], 'registry_id':registry_id,
            'kind':kind, 'computation_type':computation_type, 'is_native_solver_dynamic':kind=='native_solver_dynamic', 'name':name, 'plain_definition':plain, 'object':object_name,
            'operator':operator, 'conditioning':conditioning, 'formal_definition':definition,
            'formula':source.get('formula') or definition, 'implementation':source.get('implementation') or source.get('algorithm'),
            'columns':columns, 'novelty_key':proposal['mechanism_key'],
            'novelty_scope':'Distinct frozen operational mechanism in this TA exploration; not a claim of an original invention or proven phase predictor.',
            'novelty_relation':source.get('novelty_vs_existing') or source.get('novelty') or source.get('distinction') or source.get('novelty_witness'),
            'canonical_nonalias_witness':source.get('canonical_novelty_witness') or source.get('novelty_witness'),
            'authored_by':source.get('authored_by') or ('parallel_static' if registry_id.startswith('S') else 'parallel_learning' if kind=='native_solver_dynamic' else 'parallel_nodes'),
            'implementation_owner':source.get('implementation_owner') or ('parallel_static' if registry_id.startswith(('S','RA')) else 'parallel_learning' if kind=='native_solver_dynamic' else 'parallel_nodes'),
            'source_inspiration_urls':source_info(registry,source,extra),
            'source_relation':source.get('source_relation') or source.get('source_status') or 'Source-grounded mechanism; exact bounded scalar is a study proposal.',
            'status':status, 'status_interpretation':interpretation, 'observed':observed,
            'numeric_diagnostics_fit_only':numeric_diagnostics,
            'used_new_columns_in_existing_fit_policy':result.get('used_new_columns') if result else None,
            'frozen_identity':{'block_config_path':config_path,'block_config_sha256':INPUT_SHA[config_path], 'registry_path':block['registry_path'],'registry_sha256':block['registry_sha256'],'extractor_source_sha256':block['extractor_source_sha256'],'protocol_path':block['protocol_path'],'protocol_sha256':block['protocol_sha256'],'collection_manifest_path':manifest_path,'collection_manifest_sha256':block.get('collection_manifest_sha256')},
            'published_feature_identity':{'path':table_path,'sha256':INPUT_SHA.get(table_path),'bindings':collection_identity},
            'existing_result_identity':{'path':result_path if result else None,'sha256':INPUT_SHA.get(result_path),'bindings':result.get('bindings') if result else None},
        }
        entries.append(entry)
    entries.sort(key=lambda r:r['round_id'])
    generated = datetime.now(timezone.utc).isoformat()
    state = read('outputs/ta100/STATE.json')
    document = {'schema':'ta100.feature_catalogue.v1','generated_utc':generated,'candidate_count':len(entries),'input_side_candidates':sum(e['kind']=='input_side' for e in entries),'native_solver_dynamic_candidates':sum(e['kind']=='native_solver_dynamic' for e in entries),'catalogue_scope':'Frozen100 proposal catalogue and reporting metadata; not100 original inventions. No new extraction, model fitting, rescoring or gate/test access by this report task.','central_status_snapshot':state,'scored_result_files_available':sum(e['status']=='SCORED_COMPLETE' for e in entries),'dedup_policy':'The transferred8 graph proposals appear only in graph40. Rejected original TD19/TD24 are absent; only TD19v2/TD24v2 are scheduled. Threshold/log/quantile/budget variants do not create extra entries.','required_fit_only_dedup':dedup,'candidates':entries,'information_limitations':{'fit_constant_columns':dedup['constants'],'fit_constant_interpretation':'No variation on this FIT panel; does not prove the mechanism universally useless.','sparse_reason_ancestry_columns':[{'round_id':e['round_id'],'registry_id':e['registry_id'],'observed':e['observed'],'interpretation':'Information insufficient: limited reason-DAG coverage, not evidence of universal uselessness.'} for e in entries if e['registry_id'] in ['TD12','TD15','TD16']]},'inputs_sha256':INPUT_SHA,'no_gate_or_test_data_read':True}
    (REPORT/'FEATURE_CATALOGUE.json').write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    (REPORT/'FIT_FEATURE_DEDUP.json').write_text(json.dumps(dedup,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    md=['# TA100 特征目录','',f"更新：{generated}。共 **100 个冻结机制提案**：70 个输入侧结构/有界辅助计算、30 个原生求解前缀动态描述量。RA16/17包含有界noisy-local-walk辅助轨迹，不能称70项都是纯静态计数。它们不是100项原创发明，也不表示100项均有用。此快照已有 **{document['scored_result_files_available']}/100** 份正式完成评分记录。",'', '本目录只汇总冻结定义、来源、实际列名、既有覆盖和fit诊断。未拟合、重新评分或读取gate/test。新阶段严格禁止使用已消费gate，5355最终测试仍封存。机器目录：[FEATURE_CATALOGUE.json](FEATURE_CATALOGUE.json)；必要FIT去重：[FIT_FEATURE_DEDUP.json](FIT_FEATURE_DEDUP.json)。','', '## 读法与限制','', '- 覆盖写为“fit观测数/180；feedback观测数/60”；原有48资源排除父题仍在评估人口中回退。实际采集名单是144fit+48feedback，共192。null包括零分母、未到checkpoint、资源超限和采集失败，不等于0。','- 动态量只来自共同native-D前缀的合格动作前checkpoint，不使用TA终局计数作特征；它们在TA旧wall标签上的比较是探索信号，不是新硬件端到端部署收益。','- 静态bounded sample、F*与LOCALcube的条件写在条目；样本宽度/同调/曲率不能冒称全图证书。ROOT18的F*固定first512非重言width≤16，保留重复；LOCALcube固定top12 degree变量。','- 表中“采用”只复制既有fit程序是否使用新列，不代表改善已确认。constant/no-observation/within-block别名等既有诊断原样进入机器目录；本目录不改已有结果。', '- 5项在当前fit中恒定，只说明本面板缺乏变异。TD12、TD15、TD16三项原因链特征的fit观测分别为7、10、10，feedback各仅1；应称信息不足，不能据此证明机制无用。','', '## 必要跨块FIT去重','',f"已检查 {dedup['available_columns_checked']}/100 个有发布特征表的列，仅FIT数值且要求**完全相同观测ID支持集**；未使用feedback数值/结果或目标标签。逐值exact组 {len(dedup['exact_value_groups'])} 个，保留ties的正/反单调组 {len(dedup['monotonic_tie_pattern_groups'])} 个，|Pearson r|≥0.995诊断对 {len(dedup['high_pearson_pairs'])} 个。高相关不等于机制重复；若出现alias需语义反例或root处理，不能靠改名计数。",'']
    if not dedup['all_scheduled_columns_checked']:
        md += ['尚待特征表的轮次：'+', '.join(dedup['missing_feature_tables_for_rounds'])+'。完成后的同一检查尚未声称覆盖100项。','']
    md += ['## 冻结定义与观测','']
    for block_number in range(1,11):
        blockid=f'B{block_number:02d}'
        subset=[e for e in entries if e['block_id']==blockid]
        md += [f'## {blockid} · {subset[0]["round_id"]}–{subset[-1]["round_id"]}','']
        identity=subset[0]['frozen_identity']
        md += [f"配置：[{identity['block_config_path']}](../../{identity['block_config_path']})；定义源：[{identity['registry_path']}](../../{identity['registry_path']})。提取器源码SHA：`{identity['extractor_source_sha256']}`。完整protocol/registry/依赖/binary/feature-table SHA均在机器目录逐项保存。",'']
        for e in subset:
            ob=e['observed'];coverage='待采集' if ob['fit'] is None else f"{ob['fit']}/180；{ob['feedback']}/60"
            urls=e['source_inspiration_urls'];links='；'.join(f'[来源{j+1}]({url})' for j,url in enumerate(urls)) or '冻结root/node精确定义；参考链接见registry'
            md += [f"### {e['round_id']} · {e['registry_id']} · {e['name']}",'',str(e['plain_definition']),'',f"- 类型/对象：**{'原生求解前缀动态' if e['kind']=='native_solver_dynamic' else '输入侧结构/有界辅助计算'}**（`{e['computation_type']}`）；{e['object']}。操作：{e['operator']}。",f"- 条件：{e['conditioning']}。",f"- 实际列：`{e['columns'][0]}`；novelty key：`{e['novelty_key']}`。",f"- 精确定义：{e['formal_definition']}",f"- 当前覆盖fit/feedback：**{coverage}**；状态：`{e['status']}`（{e['status_interpretation']}）。",f"- 来源启发：{links}。仅支持机制背景，不声称文献证明该phase特征有效。"]
            if e['numeric_diagnostics_fit_only']:
                md.append('- 既有fit数值诊断：`'+json.dumps(e['numeric_diagnostics_fit_only'],ensure_ascii=False,separators=(',',':'))+'`。')
            if e['canonical_nonalias_witness']:
                md.append('- 非别名见证：'+e['canonical_nonalias_witness'])
            md.append('')
    (REPORT/'FEATURE_CATALOGUE.md').write_text('\n'.join(md))
    print(json.dumps({'candidate_count':len(entries),'scored_records':document['scored_result_files_available'],'fit_dedup_columns':len(vectors),'exact_groups':len(dedup['exact_value_groups']),'monotonic_groups':len(dedup['monotonic_tie_pattern_groups']),'high_correlation_pairs':len(dedup['high_pearson_pairs']),'files':['FEATURE_CATALOGUE.md','FEATURE_CATALOGUE.json','FIT_FEATURE_DEDUP.json']},ensure_ascii=False))


if __name__ == '__main__':
    main()
