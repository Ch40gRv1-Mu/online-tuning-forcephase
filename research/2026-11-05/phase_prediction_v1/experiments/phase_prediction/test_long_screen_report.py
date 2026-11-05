import unittest
from summarize_long_screen import describe

def case(name,costs,resolved=False):
    return {'hash':name,'role':'development_fit','costs':costs,
            'outcomes':{a:[{'cutoff_s':600,'resolved':resolved}] for a in costs}}

class LongScreen(unittest.TestCase):
    def test_all_censoring_is_not_a_winner_label(self):
        r=describe([case('a',{a:1200. for a in ['D','Fplus','Fminus','Iminus']})])
        self.assertEqual(r['all_four_actions_censored_parents'],1)
        self.assertEqual(r['oracle_vs_best_static']['relative_improvement'],0)
        self.assertEqual(r['oracle_vs_best_static']['descriptive_paired_parent_95pct'],[0.,0.])

    def test_iminus_is_not_silently_added_to_the_learned_oracle(self):
        r=describe([case('a',{'D':100.,'Fplus':80.,'Fminus':90.,'Iminus':40.},True)])
        self.assertEqual(r['mean_par2_s']['three_action_oracle'],80.)
        self.assertEqual(r['oracle_vs_best_static']['relative_improvement'],-1.)

    def test_duplicate_parent_and_protected_role_are_rejected(self):
        c=case('a',{a:1200. for a in ['D','Fplus','Fminus','Iminus']})
        with self.assertRaises(ValueError):describe([c,c])
        c['role']='development_gate'
        with self.assertRaises(ValueError):describe([c])

if __name__=='__main__':unittest.main()
