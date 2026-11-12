"""R43 finite-population descriptive error costs, never a new predictive policy."""
import json
import os
import resource
import time

import numpy as np

from .common import sha
from .measure_compact_prefetch import atomic
from .predict_relative_cost import SPLITS
from .recover_compact_cpu import OUT as RETRY
from .score_width_budget_recovery import timed_cost
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv

OUT = DATA / 'mechanism_R43_v2_20261111'


def diagnostic(costs, action, overhead):
    d, b = costs[:, 0], costs[:, 1:].min(axis=1)
    c, o = costs[np.arange(len(costs)), action], costs.min(axis=1)
    switched = action != 0
    missed = np.where(switched, 0, d - o)
    entry = np.where(switched, b - o, 0)
    direction = np.where(switched, c - b, 0)
    assert np.allclose(missed + entry + direction, c - o, rtol=0, atol=1e-9)
    loss = np.maximum(c - d, 0)
    both_bad = switched & (c > d) & (b >= d)
    other_good = switched & (c > d) & (b < d)
    assert np.allclose(loss, loss * both_bad + loss * other_good, rtol=0, atol=1e-9)
    baseline, selected = float(d.sum()), timed_cost(c, overhead, 600)
    variants = {'direction_only': np.where(switched, b, d),
                'veto_only': np.minimum(c, d),
                'joint_same_proposals': np.where(switched, o, d)}
    oracles = {}
    for name, values in variants.items():
        paid = timed_cost(values, overhead, 600)
        assert np.all(paid <= selected + 1e-9)
        oracles[name] = {'gain_over_D_pct': float(100 * (baseline - paid.sum()) / baseline),
            'increment_over_policy_population_pp': float(100 * (selected.sum() - paid.sum()) / baseline),
            'solved': int((paid < 1200).sum()), 'fee_refunded': False,
            'existing_D_proposals_kept_D': True}
    clear_loss = switched & (np.minimum(c, 600) - np.minimum(d, 600) > np.maximum(.02, .1 * np.minimum(d, 600)))
    result = {'F_proposals': int(switched.sum()), 'F_positive_changes': int((switched & (c < d)).sum()),
        'F_exact_ties': int((switched & (c == d)).sum()),
        'F_losing_changes': int((switched & (c > d)).sum()),
        'both_F_not_better_on_losing_proposals': int(both_bad.sum()),
        'other_F_better_on_losing_proposals': int(other_good.sum()),
        'clear_losing_F_proposals': int(clear_loss.sum()),
        'gross_saved_PAR2_s': float(np.maximum(d - c, 0).sum()),
        'gross_lost_PAR2_s': float(loss.sum()),
        'gross_lost_where_both_F_not_better_PAR2_s': float(loss[both_bad].sum()),
        'gross_lost_where_other_F_better_PAR2_s': float(loss[other_good].sum()),
        'oracle_regret_PAR2_s': float((c - o).sum()),
        'missed_D_proposal_opportunity_PAR2_s': float(missed.sum()),
        'force_entry_regret_after_correct_direction_PAR2_s': float(entry.sum()),
        'extra_direction_regret_PAR2_s': float(direction.sum()),
        'paid_policy_gain_over_D_pct': float(100 * (baseline - selected.sum()) / baseline),
        'physical_feature_query_fee_logical_sum_CPU_s': float(overhead.sum()),
        'fee_and_budget_PAR2_difference_s': float((selected - c).sum()),
        'restricted_oracles': oracles,
        'partition_identity_max_error': float(np.max(np.abs(missed + entry + direction - c + o)))}
    rows = [{'action': ACTIONS[action[i]], 'raw_selected_PAR2': float(c[i]),
             'paid_selected_PAR2': float(selected[i]), 'missed_regret': float(missed[i]),
             'entry_regret': float(entry[i]), 'direction_regret': float(direction[i]),
             'both_F_not_better_losing_proposal': bool(both_bad[i]),
             'other_F_better_losing_proposal': bool(other_good[i])} for i in range(len(costs))]
    return result, rows, selected


def main():
    wall, cpu = time.monotonic(), time.process_time()
    OUT.mkdir(exist_ok=False)
    atomic(OUT / 'owner.json', {'pid': os.getpid(), 'source_sha256': sha(__file__),
        'new_policy_fits': 0, 'R35_partial_preferences_read': False})
    status = 'running'
    try:
        keys, _, costs, _, _, _ = load()
        splits = read_csv(SPLITS)
        iso_rows = read_csv(DATA / 'mechanism_R11_20261111/predictions.csv')
        original = read_csv(DATA / 'mechanism_R12_20261111/predictions.csv')
        original_summary = json.loads((DATA / 'mechanism_R12_20261111/summary.json').read_text())
        recovered = read_csv(RETRY / 'predictions.csv')
        r42path = DATA / 'mechanism_R42_20261111'
        recent = read_csv(r42path / 'predictions.csv')
        recent_summary = json.loads((r42path / 'summary.json').read_text())
        assert all([r['instance_key'] for r in rows] == keys for rows in (splits, iso_rows, original, recovered, recent))
        fees = np.array([float(r['first_acquisition_CPU_s']) + float(r['second_acquisition_CPU_s']) for r in recovered])
        failed = np.array([r['still_failed_paidD'] == 'True' for r in recovered])
        assert failed.sum() == 25 and len(keys) == 4719
        folds = {'iso_diagnostic': np.array([int(r['diagnostic_iso_fold']) for r in iso_rows]),
                 **{m: np.array([int(r[m + '_fold']) for r in splits]) for m in ('coarse', 'fine')}}
        summary, outputs = {}, [{'instance_key': k} for k in keys]
        for mode, assignment in folds.items():
            name = mode + '_linear42_min3'
            enabled = np.array([original_summary['scores'][name]['cuts'][f]['margin_PAR2_s'] is not None for f in assignment])
            old_fee = np.array([float(r[name + '_decision_CPU_s']) for r in original])
            old_fee[failed & enabled] = 0  # Original serving never queried after failed acquisition.
            variants = [('R12_min3', np.array([ACTIONS.index(r[mode + '_action']) for r in recovered]),
                         fees * enabled + old_fee,
                         np.array([float(r[mode + '_PAR2']) for r in recovered]))]
            for kind in ('odd_prior', 'no_prior'):
                cuts = {r['fold']: r['margin_PAR2_s'] for r in recent_summary['cuts'] if r['mode'] == mode and r['kind'] == kind}
                enabled = np.array([cuts[int(f)] is not None for f in assignment])
                action = np.array([ACTIONS.index(r[mode + '_' + kind + '_action']) for r in recent])
                paid = np.array([float(r[mode + '_' + kind + '_PAR2']) for r in recent])
                variants.append(('R42_' + kind, action, fees * enabled, paid))
            for model, action, overhead, expected in variants:
                assert np.all(action[failed] == 0), 'Acquisition failures must remain paidD'
                result, rows, actual = diagnostic(costs, action, overhead)
                assert np.allclose(actual, expected, rtol=0, atol=1e-8), 'Existing costed policy must reconstruct exactly'
                key = mode + '_' + model
                summary[key] = result
                for i, row in enumerate(rows):
                    outputs[i].update({key + '_' + k: v for k, v in row.items()})
        write_csv(OUT / 'per_parent.csv', outputs)
        status = 'complete'
        atomic(OUT / 'summary.json', {'status': status, 'parents': len(keys),
            'diagnostics': summary, 'new_policy_reward': None, 'new_policy_fits': 0,
            'source_sha256': sha(__file__), 'matrix_sha256': sha(DATA / 'raw_data_20261110/matrix.csv'),
            'source_actions_sha256': {'R12_recovery': sha(RETRY / 'predictions.csv'),
                                     'R42': sha(r42path / 'predictions.csv')},
            'scope': 'Exact finite exposed2022-population diagnostic, not causal attribution, deployment or new policy. Raw regret order first correct direction then allowD; restricted paid oracles preserve fees, D proposals and paidD failures.'})
        for key, value in summary.items():
            print(key, 'lost', round(value['gross_lost_PAR2_s'], 3),
                  'bothFbad', value['both_F_not_better_on_losing_proposals'],
                  'otherFgood', value['other_F_better_on_losing_proposals'], flush=True)
    except BaseException as error:
        status = 'failed'
        atomic(OUT / 'failure.json', {'status': status, 'error': repr(error), 'new_policy_reward': None})
        raise
    finally:
        atomic(OUT / 'resources.json', {'status': status, 'physical_parent_CPU_s': time.process_time() - cpu,
            'physical_child_CPU_s': 0, 'wall_s': time.monotonic() - wall,
            'new_solver_calls': 0, 'new_model_fits': 0})


if __name__ == '__main__':
    main()
