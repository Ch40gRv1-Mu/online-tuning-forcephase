import hashlib,json,tempfile,unittest,threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from resource_recovery import validate_reused,load_plan,proof_capacity_available,wait_for_capacity

class RecoveryBoundary(unittest.TestCase):
    def fixture(self,d):
        root=Path(d);(root/'metadata').mkdir()
        old={'runner_sha256':'old','proof_file_limit_bytes':4*1024**3,'solver_sha256':'same'}
        new={**old,'runner_sha256':'new','proof_file_limit_bytes':8*1024**3}
        r={'hash':'a','seed':0,'action':'D','run_id':'run','identity':old,'status':'UNKNOWN',
           'verify':'NOT_ANSWERED','proof_bytes':100,'cutoff_s':600,'contended':False}
        path=root/'record.json';path.write_text(json.dumps(r))
        bound={'hash':'a','seed':0,'action':'D','run_id':'run','sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        reused=[bound]+[dict(bound,hash=str(i)) for i in range(55)]
        plan={'source_stage':'long600_fit16','target_stage':'recovery','source_identity':old,
              'reused_records':reused,'new_keys':[['new'+str(i),0,'D'] for i in range(8)]}
        pp=root/'metadata/recovery_plan.json';pp.write_text(json.dumps(plan))
        spec={'resource_recovery':True,'stage':'recovery','cutoff_s':600,'seeds':[0],'workers':2,
              'recovery_plan_sha256':hashlib.sha256(pp.read_bytes()).hexdigest()}
        return root,path,r,plan,spec,new

    def test_only_exact_nonbinding_valid_source_is_reused(self):
        with tempfile.TemporaryDirectory() as d:
            root,path,r,plan,spec,new=self.fixture(d)
            self.assertEqual(load_plan(root,spec,new),plan)
            validate_reused(r,path,plan)
            path.write_text(path.read_text()+' ')
            with self.assertRaises(ValueError):validate_reused(r,path,plan)

    def test_solver_or_deadline_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root,path,r,plan,spec,new=self.fixture(d)
            with self.assertRaises(ValueError):load_plan(root,spec,{**new,'solver_sha256':'other'})
            with self.assertRaises(ValueError):load_plan(root,{**spec,'cutoff_s':120},new)

    def test_error_or_binding_old_cap_is_never_reused(self):
        with tempfile.TemporaryDirectory() as d:
            root,path,r,plan,spec,new=self.fixture(d)
            for change in ({'status':'ERROR'},{'proof_bytes':4*1024**3},{'contended':True}):
                changed={**r,**change};path.write_text(json.dumps(changed))
                plan['reused_records'][0]['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
                with self.assertRaises(ValueError):validate_reused(changed,path,plan)

    def test_reserved_bytes_of_live_job_are_not_counted_twice(self):
        gib=1024**3;proof=Mock();proof.stat.return_value=SimpleNamespace(st_blocks=4*gib//512)
        with patch('resource_recovery.shutil.disk_usage',return_value=SimpleNamespace(free=24*gib)):
            self.assertTrue(proof_capacity_available('.',2,8*gib,[proof]))
            self.assertFalse(proof_capacity_available('.',2,8*gib,[]))

    def test_unrelated_disk_pressure_still_blocks_admission(self):
        gib=1024**3;proof=Mock();proof.stat.return_value=SimpleNamespace(st_blocks=16*gib//512)
        with patch('resource_recovery.shutil.disk_usage',return_value=SimpleNamespace(free=11*gib)):
            self.assertFalse(proof_capacity_available('.',2,8*gib,[proof,proof]))

    def test_v2_retains_distinct_cap8_source_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root,path,r,plan,spec,new=self.fixture(d)
            cap8={**plan['source_identity'],'runner_sha256':'v1','proof_file_limit_bytes':8*1024**3}
            plan.update(version=2,target_stage='long600_fit16_recovery_v2',
                        additional_source_stage='long600_fit16_recovery_v1',additional_source_identity=cap8,
                        additional_resources_sha256='resource-bound',additional_log_sha256='log-bound')
            spec['stage']=plan['target_stage'];new['resource_recovery_sha256']='bound-helper'
            pp=root/'metadata/recovery_plan.json';pp.write_text(json.dumps(plan))
            spec['recovery_plan_sha256']=hashlib.sha256(pp.read_bytes()).hexdigest()
            load_plan(root,spec,new)
            r['identity']=cap8;r['proof_bytes']=5*1024**3
            path.write_text(json.dumps(r));plan['reused_records'][0].update(
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source_stage='long600_fit16_recovery_v1')
            validate_reused(r,path,plan)

    def test_admission_wait_releases_lock_so_active_worker_can_finish(self):
        condition=threading.Condition();stop=threading.Event();noticed=threading.Event();space=threading.Event()
        active={Path('existing-proof')};answer=[]
        with patch('resource_recovery.proof_capacity_available',side_effect=lambda *a:space.is_set()):
            worker=threading.Thread(target=lambda:answer.append(wait_for_capacity('.',2,8,active,
                condition,stop,Path('next-proof'),noticed.set)))
            worker.start();self.assertTrue(noticed.wait(1))
            with condition:
                active.clear();space.set();condition.notify_all()
            worker.join(1);self.assertFalse(worker.is_alive())
        self.assertEqual(answer,[True]);self.assertEqual(active,{Path('next-proof')})

if __name__=='__main__':unittest.main()
