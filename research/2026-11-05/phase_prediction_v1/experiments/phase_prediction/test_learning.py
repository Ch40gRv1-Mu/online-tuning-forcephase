"""Policy selection must optimize cost and charge its real observation fee."""
import unittest

from learn_round import train


def case(x,costs,fee):
    return {'features':{'s_binary_fraction':x},'feature_cpu_s':fee,
            'outcomes':{a:[{'resolved':True,'cpu_s':c,'cutoff_s':120}] for a,c in costs.items()}}


class CostObjective(unittest.TestCase):
    def test_more_winner_labels_does_not_mean_lower_runtime_cost(self):
        rows=[case(.5,{'D':1,'Fplus':2,'Fminus':3},.01) for _ in range(23)]
        rows.append(case(.5,{'D':120,'Fplus':1,'Fminus':120},.01))
        # D wins 23/24 instances but F+ has much lower total cost.
        self.assertEqual(train(rows,['s_binary_fraction']),{'action':'Fplus'})

    def test_observation_cost_can_remove_the_entire_benefit_of_a_split(self):
        rows=[case(0,{'D':1,'Fplus':2,'Fminus':3},1.) for _ in range(12)]
        rows += [case(1,{'D':2,'Fplus':1,'Fminus':3},1.) for _ in range(12)]
        self.assertIn('action',train(rows,['s_binary_fraction']))
        for row in rows:row['feature_cpu_s']=.01
        self.assertIn('feature',train(rows,['s_binary_fraction']))


if __name__=='__main__':unittest.main()
