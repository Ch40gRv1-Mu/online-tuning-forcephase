import unittest
from learn_round import evaluate

def case(name,times,fee=.1,second_seed_unresolved=False):
    return {'hash':name,'features':{'s_mean_length':3.},'feature_cpu_s':fee,
            'outcomes':{a:[{'seed':0,'cpu_s':v,'resolved':True,'cutoff_s':10.},
                           {'seed':1,'cpu_s':v,'resolved':not second_seed_unresolved,'cutoff_s':10.}]
                        for a,v in times.items()}}

class FeedbackControls(unittest.TestCase):
    def test_reference_tree_pays_observation_fee_and_its_total_deadline(self):
        tree={'feature':'s_mean_length','threshold':4.,'missing':'left',
              'left':{'action':'D'},'right':{'action':'D'}}
        rows=[case('a',{'D':9.95,'Fplus':10.,'Fminus':10.,'Iminus':10.})]
        r=evaluate(rows,{'action':'D'},tree)
        self.assertEqual(r['baseline_par2'],20.)
        self.assertAlmostEqual(r['policy_par2'],9.95)
        self.assertEqual(r['baseline_solved_seed_average_count'],0.)

    def test_seed_replicates_are_averaged_before_parent_comparison(self):
        rows=[case(str(i),{'D':1.,'Fplus':2.,'Fminus':3.,'Iminus':4.},
                   second_seed_unresolved=True) for i in range(2)]
        r=evaluate(rows,{'action':'D'},'Iminus')
        self.assertEqual(r['feedback_parents'],2)
        self.assertEqual(r['policy_solved_seed_average_count'],1.)
        self.assertEqual(r['baseline_solved_seed_average_count'],1.)

    def test_identical_observed_policies_have_zero_paired_reward(self):
        tree={'feature':'s_mean_length','threshold':4.,'missing':'left',
              'left':{'action':'Fplus'},'right':{'action':'D'}}
        r=evaluate([case('a',{'D':1.,'Fplus':2.,'Fminus':3.,'Iminus':4.})],tree,tree)
        self.assertEqual(r['reward'],0.)
        self.assertEqual(r['descriptive_95pct_bootstrap'],[0.,0.])

if __name__=='__main__':unittest.main()
