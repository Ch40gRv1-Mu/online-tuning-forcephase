"""Verify published bytes and reproduce saved R54 arithmetic; no training/solving."""
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'outputs/anniversary2022_baseline'


def rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    checked = 0
    for line in (ROOT / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = ROOT / name
        assert path.is_relative_to(ROOT) and path.is_file(), name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == expected, name
        checked += 1
    matrix = rows(BASE / 'raw_data_20261110/matrix.csv')
    original = {r['instance_key']: r for r in matrix}
    assert len(original) == len(matrix) == 4719
    predictions = rows(BASE / 'mechanism_R54_paid_classifier_20261111/predictions.csv')
    assert {r['instance_key'] for r in predictions} == original.keys()
    summary = json.loads((BASE / 'mechanism_R54_paid_classifier_20261111/summary.json').read_text())
    d = {key: float(row['D_par2']) for key, row in original.items()}
    result = {}
    for variant in ('mean3', 'min3'):
        paid = {r['instance_key']: float(r[variant + '_PAR2']) for r in predictions}
        gain = 100 * math.fsum(d[k] - paid[k] for k in d) / math.fsum(d.values())
        solved = sum(v < 1200 for v in paid.values())
        rescued = sum(d[k] == 1200 and paid[k] < 1200 for k in d)
        lost = sum(d[k] < 1200 and paid[k] == 1200 for k in d)
        expected = summary['scores'][variant]
        assert abs(gain - expected['gain_pct']) < 1e-10
        assert (solved, rescued, lost) == (expected['solved'], expected['newly_solved'], expected['lost_solves'])
        result[variant] = {'PAR2_gain_pct': gain, 'solved': solved, 'rescued': rescued, 'lost': lost}
    policy_dir = BASE / 'mechanism_R55_classifier_serving_20261111'
    policy = json.loads((policy_dir / 'policy.json').read_text())
    assert hashlib.sha256((policy_dir / policy['model_file']).read_bytes()).hexdigest() == policy['model_sha256']
    print(json.dumps({'verified_files': checked, 'population': len(original),
        'D_solved': sum(v < 1200 for v in d.values()), 'reproduced_R54': result,
        'candidate_model_SHA_matches': True, 'new_solver_calls': 0, 'new_fits': 0}, indent=2))


if __name__ == '__main__':
    main()
