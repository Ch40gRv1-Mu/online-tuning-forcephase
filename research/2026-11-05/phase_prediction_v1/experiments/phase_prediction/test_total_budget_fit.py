"""A real objective regression: raw solver loss can discard the useful tree."""
import unittest
from learn_round import train

def case(x,values,fee):
    return {'features':{'s_binary_fraction':x},'feature_cpu_s':fee,
            'outcomes':{a:[{'resolved':v<=10,'cpu_s':v,'cutoff_s':10}] for a,v in values.items()}}

class FullBudgetObjective(unittest.TestCase):
    def test_leaf_actions_are_selected_after_observation_fee_and_deadline(self):
        rows=[case(0,{'D':9.8,'Fplus':1.,'Fminus':20.},.3) for _ in range(12)]
        rows += [case(0,{'D':1.,'Fplus':9.9,'Fminus':20.},.05) for _ in range(12)]
        rows += [case(1,{'D':1.,'Fplus':9.,'Fminus':.1},.05) for _ in range(24)]
        tree=train(rows,['s_binary_fraction'],depth=1,min_leaf=12)
        self.assertIn('feature',tree)
        self.assertEqual(tree['left'],{'action':'Fplus'})
        self.assertEqual(tree['right'],{'action':'Fminus'})

    def test_constant_policy_avoids_irrelevant_observation_cost(self):
        rows=[case(0,{'D':1.,'Fplus':2.,'Fminus':3.},9.) for _ in range(24)]
        self.assertEqual(train(rows,['s_binary_fraction']),{'action':'D'})

    def test_metadata_feature_is_rejected_before_fit(self):
        with self.assertRaises(ValueError):train([case(0,{'D':1.,'Fplus':2.,'Fminus':3.},0.)],['family'])

if __name__=='__main__':unittest.main()
