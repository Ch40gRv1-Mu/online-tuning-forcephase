"""R45 zero-parameter extension of originalD only, preserving originalF."""
import json
import os
import time

import numpy as np

from .common import sha
from .measure_compact_prefetch import atomic
from .predict_relative_cost import SPLITS
from .recover_compact_cpu import OUT as RETRY
from .score_interpretable_two_percent import evaluate
from .score_width_budget_recovery import timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv

OUT = DATA / 'mechanism_R45_20261111'
NEW = DATA / 'mechanism_R44_20261111'


def extend(base, proposal, eligible, native_ok, profile_ok, new_enabled):
    reached = (base == 0) & eligible & native_ok & new_enabled
    action = base.copy()
    action[reached & profile_ok] = proposal[reached & profile_ok]
    action[~native_ok] = 0
    assert np.array_equal(action[base != 0], base[base != 0])
    assert np.all(~((action != 0) & (base == 0)) | (reached & profile_ok))
    return action, reached


def main():
    cpu, wall = time.process_time(), time.monotonic()
    OUT.mkdir(exist_ok=False)
    atomic(OUT / 'owner.json', {'pid': os.getpid(), 'source_sha256': sha(__file__),
        'new_model_fits': 0, 'new_feature_acquisitions': 0, 'R35_partial_preferences_read': False})
    status = 'running'
    try:
        keys, _, costs, _, _, _ = load()
        splits = read_csv(SPLITS)
        iso_rows = read_csv(DATA / 'mechanism_R11_20261111/predictions.csv')
        original = read_csv(DATA / 'mechanism_R12_20261111/predictions.csv')
        old_summary = json.loads((DATA / 'mechanism_R12_20261111/summary.json').read_text())
        recovery = read_csv(RETRY / 'predictions.csv')
        new_rows = read_csv(NEW / 'predictions.csv')
        new_summary = json.loads((NEW / 'summary.json').read_text())
        assert all([r['instance_key'] for r in table] == keys for table in
                   (splits, iso_rows, original, recovery, new_rows))
        assert new_summary['splits_sha256'] == sha(SPLITS)
        with np.load(NEW / 'features.npz') as z:
            assert z['keys'].tolist() == keys
            eligible, profile_ok = z['eligible'], z['valid']
            profile_fee = {k: z[k + '_fee'].copy() for k in ('joint', 'decoupled', 'marginal')}
        assert eligible.sum() == 2325
        native_fee = np.array([float(r['first_acquisition_CPU_s']) + float(r['second_acquisition_CPU_s']) for r in recovery])
        failed = np.array([r['still_failed_paidD'] == 'True' for r in recovery])
        assert failed.sum() == 25
        coarse, fine = [np.array([r[k + '_group'] for r in splits]) for k in ('coarse', 'fine')]
        folds = {'iso_diagnostic': np.array([int(r['diagnostic_iso_fold']) for r in iso_rows]),
                 **{m: np.array([int(r[m + '_fold']) for r in splits]) for m in ('coarse', 'fine')}}
        scores, paired, stages = {}, {}, {}
        output = [{'instance_key': k} for k in keys]
        for mode, assignment in folds.items():
            group = fine if mode == 'fine' else coarse
            name = mode + '_linear42_min3'
            old_enabled = np.array([old_summary['scores'][name]['cuts'][f]['margin_PAR2_s'] is not None for f in assignment])
            old = np.array([ACTIONS.index(r[mode + '_action']) for r in recovery])
            old_query = np.array([float(r[name + '_decision_CPU_s']) for r in original])
            old_query[failed & old_enabled] = 0
            baseline = timed_cost(costs[np.arange(len(keys)), old], native_fee * old_enabled + old_query, 600)
            expected = np.array([float(r[mode + '_PAR2']) for r in recovery])
            assert np.allclose(baseline, expected, rtol=0, atol=1e-8)
            scores[mode + '_baseline'] = evaluate(costs[:, 0], baseline, group, coarse, mode)
            paid_by_kind = {'baseline': baseline}
            for kind in ('joint', 'decoupled', 'marginal'):
                cut = {r['fold']: r['margin_PAR2_s'] for r in new_summary['fit_records'] if r['mode'] == mode and r['kind'] == kind}
                enabled = np.array([cut[int(f)] is not None for f in assignment])
                proposal = np.array([ACTIONS.index(r[mode + '_' + kind + '_action']) for r in new_rows])
                action, reached = extend(old, proposal, eligible, ~failed, profile_ok, enabled)
                fees = native_fee * (old_enabled | enabled) + old_query + profile_fee[kind] * reached
                paid = timed_cost(costs[np.arange(len(keys)), action], fees, 600)
                assert np.allclose(paid[old != 0], baseline[old != 0], rtol=0, atol=1e-8)
                assert np.all(action[failed] == 0)
                s = evaluate(costs[:, 0], paid, group, coarse, mode)
                s['actions'] = {a: int((action == j).sum()) for j, a in enumerate(ACTIONS)}
                s['new_query_unmeasured_optimistic_zero'] = True
                scores[mode + '_' + kind], paid_by_kind[kind] = s, paid
                added = (old == 0) & (action != 0)
                stages[mode + '_' + kind] = {'original_F_proposals_unchanged': int((old != 0).sum()),
                    'new_F_proposals': int(added.sum()), 'new_profile_calls_including_final_D': int(reached.sum()),
                    'native_calls': int((old_enabled | enabled).sum()),
                    'profile_fee_logical_CPU_s': float((profile_fee[kind] * reached).sum()),
                    'native_fee_logical_CPU_s': float((native_fee * (old_enabled | enabled)).sum()),
                    'old_query_logical_CPU_s': float(old_query.sum()),
                    'additional_F_raw_benefit_PAR2_s': float(np.maximum(costs[:, 0] - costs[np.arange(len(keys)), action], 0)[added].sum()),
                    'additional_F_raw_loss_PAR2_s': float(np.maximum(costs[np.arange(len(keys)), action] - costs[:, 0], 0)[added].sum()),
                    'added_F_rescues_vs_D': int((added & (costs[:, 0] >= 1200) & (paid < 1200)).sum()),
                    'added_F_losses_vs_D': int((added & (costs[:, 0] < 1200) & (paid >= 1200)).sum())}
                for i, row in enumerate(output):
                    row[mode + '_' + kind + '_action'] = ACTIONS[action[i]]
                    row[mode + '_' + kind + '_PAR2'] = float(paid[i])
                print(f"R45 {mode}_{kind}: gain={s['gain_pct']:+.6f}%, solved={s['solved']}, addedF={added.sum()}", flush=True)
            for candidate, controls in [('joint', ('baseline', 'decoupled', 'marginal')),
                                        ('marginal', ('baseline',))]:
                for control in controls:
                    paired[mode + '_' + candidate + '_over_' + control] = evaluate(
                        paid_by_kind[control], paid_by_kind[candidate], group, coarse, mode)
        promotion = {}
        for candidate in ('joint', 'marginal'):
            passed = True
            for mode in ('coarse', 'fine'):
                s = scores[mode + '_' + candidate]
                ci = s.get('exact_eight_block_95_pct', s['block_interval_95_pct'])
                passed &= s['gain_pct'] >= 2 and ci[0] > 0
                for control in (('baseline', 'decoupled', 'marginal') if candidate == 'joint' else ('baseline',)):
                    s = paired[mode + '_' + candidate + '_over_' + control]
                    ci = s.get('exact_eight_block_95_pct', s['block_interval_95_pct'])
                    passed &= s['gain_pct'] > 0 and ci[0] >= 0
            promotion[candidate] = bool(passed)
        write_csv(OUT / 'predictions.csv', output)
        status = 'complete'
        atomic(OUT / 'operator.json', {'operator': 'keep_original_F_else_add_if_count_qualified',
            'base': 'R12linear42min3', 'extension_primary': 'R44joint99',
            'extension_null': 'R44decoupled99', 'extension_secondary': 'R44marginal99',
            'preserve_old_F': True, 'new_F_only_old_D_and_count_eligible': True,
            'scope': 'Executable action combiner in source, not complete exported trained models or serving deployment'})
        atomic(OUT / 'summary.json', {'status': status, 'parents': len(keys), 'scores': scores,
            'paired_comparisons': paired, 'stages': stages, 'promotion': promotion,
            'new_model_fits': 0, 'new_feature_acquisitions': 0, 'new_solver_calls': 0,
            'source_sha256': sha(__file__), 'old_actions_sha256': sha(RETRY / 'predictions.csv'),
            'new_actions_sha256': sha(NEW / 'predictions.csv'),
            'scope': 'Repeated2022 development, same held folds. Original query paid, new query0 optimistic; conditional composed replay, no independent or deployment claim.'})
    except BaseException as error:
        status = 'failed'
        atomic(OUT / 'failure.json', {'status': status, 'error': repr(error), 'reward': None})
        raise
    finally:
        atomic(OUT / 'resources.json', {'status': status, 'physical_parent_CPU_s': time.process_time() - cpu,
            'physical_child_CPU_s': 0, 'wall_s': time.monotonic() - wall, 'new_solver_calls': 0, 'new_model_fits': 0})


if __name__ == '__main__':
    main()
