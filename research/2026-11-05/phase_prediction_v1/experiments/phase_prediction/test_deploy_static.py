"""The feature fee must change the actual deployed deadline and policy score."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import deploy_static as deploy
import policy
import deployment_consistency

class DeploymentBudget(unittest.TestCase):
    def test_forbidden_metadata_never_enters_policy_input(self):
        with self.assertRaises(ValueError):deploy.validated_features({'s_mean_length':3.,'family':'hidden'})
        with self.assertRaises(ValueError):deploy.validated_features({'s_mean_length':float('nan')})
        self.assertEqual(deploy.validated_features({'s_mean_length':3.}),{'s_mean_length':3.})

    def setup_files(self,root,tree,role='development_fit'):
        cnf=root/'input.cnf';cnf.write_text('p cnf 1 1\n1 0\n')
        tools={}
        for name in ('solver','checker','extractor'):
            f=root/name;f.write_text(name);tools[name]=str(f);tools[name+'_sha256']=hashlib.sha256(f.read_bytes()).hexdigest()
        spec={**tools,'policy_sha256':policy.validate(tree),'total_cpu_budget_s':10.,'cpu':0,'seed':0}
        parent={'path':str(cnf),'sha256':hashlib.sha256(cnf.read_bytes()).hexdigest(),'header_variables':1,'role':role}
        return spec,parent

    def test_verified_answer_crossing_total_deadline_is_not_solved(self):
        tree={'feature':'s_mean_length','threshold':4.,'missing':'left','left':{'action':'Fplus'},'right':{'action':'D'}}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec,parent=self.setup_files(root,tree)
            def child(cmd,log,cutoff,cpu,**kw):
                if str(cmd[0])==spec['extractor']:
                    text=json.dumps({'s_mean_length':3.});Path(log).write_text(text)
                    return {'cpu_s':.5,'exit_code':0},text
                text='v 1 0\n';Path(log).write_text(text)
                return {'cpu_s':9.6,'wall_s':9.6,'exit_code':10,'watchdog_killed':False,'command':list(map(str,cmd))},text
            with patch.object(deploy.common,'child',side_effect=child):
                r=deploy.run_one(spec,parent,tree,root/'deployment')
            self.assertEqual(r['action'],'Fplus');self.assertEqual(r['verify'],'VERIFIED_MODEL')
            self.assertFalse(r['resolved']);self.assertEqual(r['par2'],20.)
            self.assertEqual(r['par2'],r['offline_replay_cost_from_actual_observation'])
            self.assertEqual(deployment_consistency.check(root/'deployment')['par2'],20.)

    def test_constant_policy_does_not_pay_for_or_execute_graph_features(self):
        tree={'action':'D'}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec,parent=self.setup_files(root,tree);calls=[]
            def child(cmd,log,cutoff,cpu,**kw):
                calls.append(str(cmd[0]));Path(log).write_text('v 1 0\n')
                return {'cpu_s':1.,'wall_s':1.,'exit_code':10,'watchdog_killed':False,'command':list(map(str,cmd))},'v 1 0\n'
            with patch.object(deploy.common,'child',side_effect=child):r=deploy.run_one(spec,parent,tree,root/'deployment')
            self.assertEqual(calls,[spec['solver']]);self.assertTrue(r['resolved']);self.assertLess(r['par2'],1.05)
            self.assertTrue(deployment_consistency.check(root/'deployment')['resolved'])

    def test_record_action_and_raw_log_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);tree={'action':'D'};spec,parent=self.setup_files(root,tree)
            def child(cmd,log,cutoff,cpu,**kw):
                Path(log).write_text('v 1 0\n')
                return {'cpu_s':1.,'wall_s':1.,'exit_code':10,'watchdog_killed':False,'command':list(map(str,cmd))},'v 1 0\n'
            with patch.object(deploy.common,'child',side_effect=child):r=deploy.run_one(spec,parent,tree,root/'deployment')
            path=root/'deployment/record.json';r['action']='Fminus';path.write_text(json.dumps(r))
            with self.assertRaises(ValueError):deployment_consistency.check(root/'deployment')
            r['action']='D';path.write_text(json.dumps(r));(root/'deployment/logs/solver.log').write_text('changed')
            with self.assertRaises(ValueError):deployment_consistency.check(root/'deployment')

    def test_gate_and_test_are_rejected_before_creating_outputs(self):
        for role in ('development_gate','test'):
            with self.subTest(role=role),tempfile.TemporaryDirectory() as d:
                root=Path(d);tree={'action':'D'};spec,parent=self.setup_files(root,tree,role)
                with self.assertRaises(ValueError):deploy.run_one(spec,parent,tree,root/'deployment')
                self.assertFalse((root/'deployment').exists())

    def test_invalid_answer_is_not_a_timeout_training_label(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);tree={'action':'D'};spec,parent=self.setup_files(root,tree)
            with patch.object(deploy.common,'child',return_value=({'cpu_s':1.,'wall_s':1.,'exit_code':10,'watchdog_killed':False},'v -1 0\n')):
                r=deploy.run_one(spec,parent,tree,root/'deployment')
            self.assertEqual(r['verify'],'INVALID_MODEL')
            self.assertFalse(r['performance_valid']);self.assertFalse(r['training_eligible'])

    def test_binary_checker_requires_exit20_and_s_verified(self):
        for exit_code,marker,expected in [(0,'s VERIFIED\n',False),(20,'not verified\n',False),(20,'s VERIFIED\n',True)]:
            with self.subTest(exit_code=exit_code,marker=marker),tempfile.TemporaryDirectory() as d:
                root=Path(d);tree={'action':'D'};spec,parent=self.setup_files(root,tree)
                def child(cmd,log,cutoff,cpu,**kw):
                    is_check=str(cmd[0])==spec['checker'];text=marker if is_check else 's UNSATISFIABLE\n'
                    Path(log).write_text(text)
                    return {'cpu_s':1.,'wall_s':1.,'exit_code':exit_code if is_check else 20,
                            'watchdog_killed':False,'command':list(map(str,cmd))},text
                with patch.object(deploy.common,'child',side_effect=child):r=deploy.run_one(spec,parent,tree,root/'deployment')
                self.assertEqual(r['performance_valid'],expected)
                if expected:self.assertTrue(deployment_consistency.check(root/'deployment')['resolved'])
                else:
                    with self.assertRaises(ValueError):deployment_consistency.check(root/'deployment')

    def test_observation_exhaustion_is_scored_without_launching_solver(self):
        tree={'feature':'s_mean_length','threshold':4.,'missing':'left',
              'left':{'action':'Fplus'},'right':{'action':'D'}}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec,parent=self.setup_files(root,tree);spec['total_cpu_budget_s']=.25;calls=[]
            def child(cmd,log,cutoff,cpu,**kw):
                calls.append(str(cmd[0]));self.assertEqual(str(cmd[0]),spec['extractor'])
                text=json.dumps({'s_mean_length':3.});Path(log).write_text(text)
                return {'cpu_s':.5,'exit_code':0},text
            with patch.object(deploy.common,'child',side_effect=child):r=deploy.run_one(spec,parent,tree,root/'deployment')
            self.assertEqual(calls,[spec['extractor']]);self.assertIsNone(r['solver'])
            self.assertEqual(deployment_consistency.check(root/'deployment')['par2'],.5)

    def test_frozen8gib_cap_is_used_and_validated_or_unknown_proof_is_released(self):
        for code,answer in [(10,'v 1 0\n'),(0,'s UNKNOWN\n'),(-25,'resource failure\n')]:
            with self.subTest(code=code),tempfile.TemporaryDirectory() as d:
                root=Path(d);tree={'action':'D'};spec,parent=self.setup_files(root,tree)
                spec['proof_file_limit_bytes']=8*1024**3
                def child(cmd,log,cutoff,cpu,**kw):
                    self.assertEqual(kw['file_limit_bytes'],8*1024**3)
                    Path(cmd[-1]).write_bytes(b'proof-bytes');Path(log).write_text(answer)
                    return {'cpu_s':1.,'wall_s':1.,'exit_code':code,'watchdog_killed':False,
                            'command':list(map(str,cmd))},answer
                with patch.object(deploy.common,'child',side_effect=child):r=deploy.run_one(spec,parent,tree,root/'deployment')
                self.assertEqual(r['identity']['proof_file_limit_bytes'],8*1024**3)
                self.assertEqual((root/'deployment/logs/solver.lrat').exists(),code==-25)
                self.assertEqual(r['performance_valid'],code!=-25)

    def test_fractional_cpu_deadline_keeps_native_wall_cap_and_scores_timer_expiry(self):
        tree={'feature':'s_mean_length','threshold':4.,'missing':'left',
              'left':{'action':'Fplus'},'right':{'action':'D'}}
        for code in (10,-27):
            with self.subTest(code=code),tempfile.TemporaryDirectory() as d:
                root=Path(d);spec,parent=self.setup_files(root,tree)
                wrapper=root/'cpu-helper';wrapper.write_text('qualified-helper')
                digest=hashlib.sha256(wrapper.read_bytes()).hexdigest()
                gate=root/'cpu-gate.json';gate.write_text(json.dumps({'status':'PASS','wrapper_sha256':digest,
                    'solver_sha256':spec['solver_sha256'],'checker_sha256':spec['checker_sha256']}))
                spec.update(cpu_budget_executor=str(wrapper),cpu_budget_executor_sha256=digest,
                    cpu_budget_qualification_path=str(gate),cpu_budget_qualification_sha256=hashlib.sha256(gate.read_bytes()).hexdigest())
                def child(cmd,log,cutoff,cpu,**kw):
                    if str(cmd[0])==spec['extractor']:
                        text=json.dumps({'s_mean_length':3.});Path(log).write_text(text)
                        return {'cpu_s':1.2,'exit_code':0},text
                    self.assertEqual(str(cmd[0]),str(wrapper));self.assertLess(float(cmd[1]),8.8)
                    self.assertEqual(cmd[cmd.index('-t')+1],'10');self.assertEqual(cutoff,10)
                    text='v 1 0\n' if code==10 else '';Path(log).write_text(text)
                    return {'cpu_s':8.9,'wall_s':8.9,'exit_code':code,'watchdog_killed':False,
                            'command':list(map(str,cmd))},text
                with patch.object(deploy.common,'child',side_effect=child):r=deploy.run_one(spec,parent,tree,root/'deployment')
                self.assertEqual(r['cpu_budget_expired'],code==-27)
                self.assertEqual(r['status'],'TIMEOUT' if code==-27 else 'SAT')
                self.assertTrue(r['performance_valid']);self.assertFalse(r['resolved'])
                self.assertEqual(deployment_consistency.check(root/'deployment')['par2'],20.)

if __name__=='__main__':unittest.main()
