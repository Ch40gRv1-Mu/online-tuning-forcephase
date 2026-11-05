"""Scientific boundary regressions: prefix mismatch, late data and test input."""
import copy
import unittest

import online_gate
import run_matrix
from analyze_matrix import deployed_cost


class OnlineBoundaries(unittest.TestCase):
    def streams(self):
        result={}
        for action,name in online_gate.ACTION_NAMES.items():
            result[action]=[
                {'type':'checkpoint','crossed':[1000,1000],'conflicts':1234,'decisions':5000,
                 'time':1.,'action':'NATIVE','digest':'same','f':{'c_glue_mean':8.,'r_time':1.}},
                {'type':'switch','action':name,'conflicts':1234,'requested':1000},
                {'type':'final'}]
        return result

    def test_wall_clock_difference_is_not_a_state_difference(self):
        s=self.streams();s['Fplus'][0]['f']['r_time']=1.2
        self.assertTrue(online_gate.check_prefix(s)['reached'])

    def test_wrong_state_or_pre_action_glue_is_rejected(self):
        for field in ('digest','feature'):
            s=self.streams()
            if field=='digest':s['Fminus'][0]['digest']='different'
            else:s['Fminus'][0]['f']['c_glue_mean']=9.
            with self.assertRaises(ValueError):online_gate.check_prefix(s)

    def test_observation_after_action_is_rejected(self):
        s=self.streams();s['Fplus'][0],s['Fplus'][1]=s['Fplus'][1],s['Fplus'][0]
        with self.assertRaises(ValueError):online_gate.check_prefix(s)

    def test_partial_reachability_cannot_be_a_counterfactual_label(self):
        s=self.streams();s['Fminus']=[{'type':'final'}]
        with self.assertRaises(ValueError):online_gate.check_prefix(s)

    def test_formal_runner_cannot_ingest_gate_or_test_data(self):
        spec={'mode':'online','actions':['D','Fplus','Fminus'],'seeds':[0],
              'cutoff_s':120,'verification':'timed_LRAT_independent_check','workers':4,
              'solver_upper_cpu_hours':1.6,'max_total_cpu_hours':2.5}
        for role in ('sealed_confirmation','development_gate','development_feedback'):
            with self.assertRaises(ValueError):
                run_matrix.validate_spec(copy.deepcopy(spec),[{'hash':'a'*32,'role':role}])

    def test_feature_cost_can_turn_an_answer_into_an_end_to_end_timeout(self):
        outcome={'resolved':True,'cpu_s':119.,'cutoff_s':120}
        self.assertEqual(deployed_cost(outcome,.5),119.5)
        self.assertEqual(deployed_cost(outcome,2.),240)
        self.assertEqual(deployed_cost({**outcome,'resolved':False},.5),240)
        with self.assertRaises(ValueError):deployed_cost(outcome,float('nan'))


if __name__=='__main__':unittest.main()
