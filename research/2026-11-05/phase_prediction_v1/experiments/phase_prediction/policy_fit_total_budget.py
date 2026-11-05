"""Cost-sensitive shallow trees under the frozen h+t <= T deployment contract."""
import math,statistics
from analyze_matrix import deployed_cost
import policy

ACTIONS=['D','Fplus','Fminus']

def train(rows,features,depth=2,min_leaf=12):
    if not rows or not set(features)<=policy.STATIC or depth not in (1,2,3) or min_leaf<8:
        raise ValueError('unsupported proposal capacity or feature')
    def cost(r,a,observed):
        fee=r['feature_cpu_s'] if observed else 0.
        return statistics.mean(deployed_cost(x,fee) for x in r['outcomes'][a])
    def leaf(rr,observed):
        a=min(ACTIONS,key=lambda a:(sum(cost(r,a,observed) for r in rr),a))
        return {'action':a}
    def loss(rr,node,observed):
        return sum(cost(r,policy.decide(node,r['features']),observed) for r in rr)
    def grow(rr,level,already_observed):
        best=leaf(rr,already_observed);best_loss=loss(rr,best,already_observed);initial=best_loss
        if level>=depth or len(rr)<2*min_leaf:return best
        split=None
        for name in sorted(features):
            values=sorted({r['features'].get(name) for r in rr if r['features'].get(name) is not None})
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):
                raise ValueError('non-numeric training feature')
            if len(values)<2:continue
            for threshold in sorted({values[(len(values)-1)*q//8] for q in range(1,8)}):
                for missing in ('left','right'):
                    left=[];right=[]
                    for r in rr:
                        v=r['features'].get(name)
                        go_left=missing=='left' if v is None else v<=threshold
                        (left if go_left else right).append(r)
                    if min(len(left),len(right))<min_leaf:continue
                    node={'feature':name,'threshold':threshold,'missing':missing,
                          'left':leaf(left,True),'right':leaf(right,True)}
                    measured=loss(rr,node,True)
                    if measured<best_loss and measured<initial*.99:
                        best_loss=measured;best=node;split=(left,right)
        if split:
            best['left']=grow(split[0],level+1,True)
            best['right']=grow(split[1],level+1,True)
        return best
    tree=grow(rows,0,False);policy.validate(tree,max_depth=depth)
    # A learned constant does not execute the extractor; a nonconstant tree
    # charges each parent's full extractor exactly once, even below another split.
    constant=leaf(rows,False)
    if loss(rows,constant,False)<=loss(rows,tree,'feature' in tree):return constant
    return tree
