"""Missing-instance and right-censoring regressions for pilot analysis."""
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class AnalysisTests(unittest.TestCase):
    def fixture(self,root,missing_parent=False):
        (root/'metadata').mkdir();(root/'results/runs').mkdir(parents=True)
        ids=['a'*32,'b'*32] if missing_parent else ['a'*32]
        with (root/'metadata/pilot_frozen.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['hash','role']);w.writeheader()
            w.writerows({'hash':h,'role':'development_fit'} for h in ids)
        identity={'binary':'synthetic-unit-test'}
        (root/'results/run_identity.json').write_text(json.dumps(identity))
        (root/'results/prepared.json').write_text(json.dumps([{'hash':h,'sha256':'source-'+h} for h in ids]))
        aliases=[]
        for index,h in enumerate(ids):
            (root/'results'/(h+'.features.json')).write_text(json.dumps({'source_sha256':'source-'+h,'features':{'s_binary_fraction':.5},'feature_cpu_s':.01}))
            for action in ['D','Fplus','Fminus']:
                rid=f'{index}-{action}';aliases.append({'hash':h,'action':action,'run_id':rid})
                if index>0 and missing_parent:continue
                resolved=action=='D'
                record={'hash':h,'action':action,'run_id':rid,'identity':identity,'input_sha256':'source-'+h,
                        'status':'SAT' if resolved else 'UNKNOWN','verify':'VERIFIED_MODEL' if resolved else 'NOT_ANSWERED',
                        'resolved':resolved,'cpu_s':59 if resolved else 60,'cutoff_s':60,'verification_cpu_s':0,'contended':False}
                (root/'results/runs'/(rid+'.json')).write_text(json.dumps(record))
        (root/'results/run_aliases.json').write_text(json.dumps(aliases))

    def execute(self,root):
        return subprocess.run([sys.executable,str(Path(__file__).with_name('analyze_pilot.py')),
                               '--root',str(root),'--out',str(root/'analysis')],capture_output=True,text=True)

    def test_whole_missing_parent_cannot_vanish_from_denominator(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root,True);r=self.execute(root)
            self.assertNotEqual(r.returncode,0)
            integrity=json.loads((root/'analysis/integrity.json').read_text())
            self.assertEqual(integrity['planned_parents'],2)
            self.assertEqual(len(integrity['missing']),3)
            self.assertFalse((root/'analysis/summary.json').exists())

    def test_timeout_penalty_does_not_create_a_clear_winner(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root);r=self.execute(root)
            self.assertEqual(r.returncode,0,r.stderr)
            record=json.loads((root/'analysis/cases.jsonl').read_text())
            self.assertEqual(record['nominal_winner'],'D')
            self.assertIsNone(record['clear_winner'])

    def test_proof_extension_is_bound_to_immutable_original_measurement(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            identity={'binary_sha256':'synthetic-solver','checker_sha256':'synthetic-checker'}
            (root/'results/run_identity.json').write_text(json.dumps(identity))
            for path in (root/'results/runs').glob('*.json'):
                r=json.loads(path.read_text());r['identity']=identity
                if r['action']=='D':
                    r.update({'status':'UNSAT','verify':'UNVERIFIED_CERTIFICATION','resolved':False,
                              'conflicts':10,'decisions':20,'propagations':100,'restarts':2,'rephased':0})
                path.write_text(json.dumps(r))
            path=root/'results/runs/0-D.json';original=path.read_bytes();r=json.loads(original)
            extra={'verify':'VERIFIED_LRAT_EXTENSION','checker_verified':True,'original_run_id':r['run_id'],
                   'original_record_sha256':hashlib.sha256(original).hexdigest(),'input_sha256':r['input_sha256'],
                   'binary_sha256':identity['binary_sha256'],'checker_sha256':identity['checker_sha256'],
                   'measurement_changed':False,'verification_cpu_s':65,'checker':{'exit_code':0},
                   'certification':{'exit_code':20,**{k:r[k] for k in ('conflicts','decisions','propagations','restarts','rephased')}}}
            extensions=root/'results/certification_extensions';extensions.mkdir()
            ep=extensions/'0-D.json';ep.write_text(json.dumps(extra))
            result=self.execute(root);self.assertEqual(result.returncode,0,result.stderr)
            case=json.loads((root/'analysis/cases.jsonl').read_text())
            self.assertEqual(case['costs']['D'],59)
            self.assertEqual(path.read_bytes(),original)
            extra['input_sha256']='wrong';ep.write_text(json.dumps(extra))
            self.assertNotEqual(self.execute(root).returncode,0)


if __name__=='__main__':unittest.main()
