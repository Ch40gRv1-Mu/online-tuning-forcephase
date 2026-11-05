"""Prevent partial trajectories or duplicate parents from masquerading as feedback."""
import copy,unittest
from learn_round import validate_development_panel

def panel():
    return [{'hash':'parent1','role':'development_fit','features':{'s_mean_length':3.},
             'feature_cpu_s':.1,'outcomes':{a:[{'seed':s,'cutoff_s':600,'status':'UNKNOWN',
               'verify':'NOT_ANSWERED','resolved':False,'cpu_s':599.} for s in [0,1]]
               for a in ['D','Fplus','Fminus','Iminus']}}]

class PanelContract(unittest.TestCase):
    def test_seed0_screen_is_not_a_two_seed_development_panel(self):
        rows=panel()
        self.assertEqual(validate_development_panel(rows,{})['independent_parents'],1)
        for outcomes in rows[0]['outcomes'].values():outcomes.pop()
        with self.assertRaises(ValueError):validate_development_panel(rows,{})

    def test_duplicate_trajectories_and_parents_do_not_inflate_n(self):
        rows=panel()
        with self.assertRaises(ValueError):validate_development_panel(rows+copy.deepcopy(rows),{})
        rows[0]['outcomes']['D'][1]['seed']=0
        with self.assertRaises(ValueError):validate_development_panel(rows,{})

    def test_protected_role_or_answer_failure_blocks_reward(self):
        rows=panel();rows[0]['role']='development_gate'
        with self.assertRaises(ValueError):validate_development_panel(rows,{})
        rows=panel();rows[0]['outcomes']['Fplus'][0]['status']='ERROR'
        with self.assertRaises(ValueError):validate_development_panel(rows,{})

    def test_cutoff_and_feature_boundaries_are_enforced(self):
        rows=panel()
        with self.assertRaises(ValueError):validate_development_panel(rows,{'cutoff_s':120})
        rows[0]['features']['family']=1
        with self.assertRaises(ValueError):validate_development_panel(rows,{})

if __name__=='__main__':unittest.main()
