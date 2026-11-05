"""Versioned numeric feature join; reuse the frozen total-budget learning engine."""
import argparse
import json
import sys
from pathlib import Path
import learn_round
import policy
import run_pilot as common
from professor_depth_rules import GEOMETRY, GATES


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--original-analysis', type=Path, required=True)
    p.add_argument('--original-imported', type=Path, required=True)
    p.add_argument('--features', type=Path, required=True)
    p.add_argument('--derived-analysis', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--memory', type=Path, required=True)
    a = p.parse_args()
    original_pool = set(policy.STATIC)
    new_pool = original_pool | set(GEOMETRY) | set(GATES)
    if len(original_pool) != 34 or len(new_pool) != 43:
        raise ValueError('unversioned feature pool')
    integrity = json.loads((a.original_analysis/'integrity.json').read_text())
    if not integrity['complete_and_valid']:
        raise ValueError('not a complete valid runtime matrix')
    summary = json.loads((a.original_analysis/'summary.json').read_text())
    original_cases = a.original_analysis/'cases.jsonl'
    cases = [json.loads(x) for x in original_cases.read_text().splitlines() if x]
    prepared = {r['hash']: r for r in json.loads((a.original_imported/'results/prepared.json').read_text())}
    completion = json.loads((a.features/'results/completion.json').read_text())
    identity = json.loads((a.features/'results/identity.json').read_text())
    if completion['parents'] != 192 or completion['valid'] != 192:
        raise ValueError('not the complete depth feature stage')
    receipt_hashes = {}
    for case in cases:
        path = a.features/'results'/(case['hash']+'.json')
        rec = json.loads(path.read_text())
        if rec['status'] != 'VALID' or rec['role'] != case['role'] or rec['identity'] != identity:
            raise ValueError('changed feature/role identity')
        if rec['input_sha256'] != prepared[case['hash']]['sha256']:
            raise ValueError('runtime and features use different input bytes')
        features = {k: v for k, v in rec['features'].items() if k != 'feature_wall_s'}
        if set(features) != new_pool or any(features[k] != case['features'][k] for k in original_pool):
            raise ValueError('unversioned features or changed original34 values')
        case['features'] = features
        case['feature_cpu_s'] = rec['feature_cpu_s']
        receipt_hashes[case['hash']] = common.sha(path)
    derived_identity = {**summary['identity'], 'feature_contract': 'depth43_v1',
                        'original_runtime_extractor_sha256': summary['identity']['extractor_sha256'],
                        'extractor_sha256': identity['binary_sha256'],
                        'extractor_memory_bytes': 1536*1024**2,
                        'feature_stage_identity': identity,
                        'original_analysis_cases_sha256': common.sha(original_cases),
                        'feature_join_and_whitelist_source_sha256': common.sha(Path(__file__)),
                        'numeric_feature_allowlist': sorted(new_pool)}
    metadata = {'feature_identity': derived_identity, 'per_parent_receipt_sha256': receipt_hashes,
                'new_solver_runs': 0, 'reused_runtime_measurements': 320,
                'cost_note': 'Replace original feature fee with combined extractor actual CPU; do not add both.'}
    if a.derived_analysis.exists():
        if json.loads((a.derived_analysis/'feature_join.json').read_text()) != metadata:
            raise ValueError('refuse changed derived analysis')
        expected = ''.join(json.dumps(x, sort_keys=True)+'\n' for x in cases)
        if (a.derived_analysis/'cases.jsonl').read_text() != expected:
            raise ValueError('changed derived cases')
    else:
        a.derived_analysis.mkdir(parents=True)
        (a.derived_analysis/'cases.jsonl').write_text(''.join(json.dumps(x, sort_keys=True)+'\n' for x in cases))
        common.write(a.derived_analysis/'integrity.json', {**integrity, 'derived_feature_join_complete': True})
        common.write(a.derived_analysis/'summary.json', {**summary, 'identity': derived_identity,
                     'interpretation': 'Original validated T60 outcomes, versioned depth43 features and measured costs; old summary roles remain static-only diagnostics.'})
        common.write(a.derived_analysis/'feature_join.json', metadata)
    # Default arguments refer to this same set object. Expansion is confined to
    # this process; old source/files and round2 receipts remain unchanged.
    policy.STATIC.update(set(GEOMETRY)|set(GATES))
    sys.argv = [str(Path(learn_round.__file__)), '--analysis', str(a.derived_analysis),
                '--plan', str(a.plan), '--out', str(a.out), '--memory', str(a.memory)]
    learn_round.main()


if __name__ == '__main__':
    main()
