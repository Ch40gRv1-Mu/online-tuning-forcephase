"""Frozen H05: dynamic stump or cheap byte-size gate followed by a dynamic stump."""
import numpy as np
from simple_selection import fit,predict,CONFIGS,boot_indices

def subset(o,mask):
    return dict(o,**{k:o[k][mask] for k in ('X','charge','available','bytes','gatefee')})

def apply(chosen,o):
    n=len(o['X']);pred=np.zeros(n,dtype=int);charge=np.zeros(n);gate=np.ones(n,dtype=bool)
    if chosen is None:return pred,charge,np.zeros(n,dtype=bool)
    if chosen['model']=='B':
        t=chosen['gate']['byte_threshold']
        gate=o['bytes']<=t if chosen['gate']['direction']=='le' else o['bytes']>t
        charge+=o['gatefee']
    pred[gate]=predict(chosen['rule'],o['X'][gate],o['names'],o['available'][gate])
    charge[gate]+=o['charge'][gate]
    return pred,charge,gate&o['available']

def train(options,costs,family):
    best=float(costs[:,0].sum());chosen=None
    # A precedes B, then budget and the fixed feature/threshold order resolve exact ties.
    for model in ('A','B'):
        for o in options:
            gates=[None] if model=='A' else [dict(byte_threshold=float(t),direction=d) for t in np.unique(np.quantile(o['bytes'],[.25,.5,.75])) for d in ('le','gt')]
            for gate in gates:
                mask=np.ones(len(costs),dtype=bool) if gate is None else (o['bytes']<=gate['byte_threshold'] if gate['direction']=='le' else o['bytes']>gate['byte_threshold'])
                if not mask.any():continue
                rule=fit(o['X'][mask],costs[mask],o['charge'][mask],family[mask],o['names'],o['available'][mask])
                if rule is None:continue
                candidate=dict(model=model,budget=o['budget'],gate=gate,rule=rule)
                pred,charge,_=apply(candidate,o)
                score=float(costs[np.arange(len(costs)),pred].sum()+charge.sum())
                if score<best-1e-10:best=score;chosen=candidate
    return chosen

def evaluate(name,options,data):
    labels,_,costs,cpu,truth,family,folds=data
    pred=np.zeros(len(labels),dtype=int);charge=np.zeros(len(labels));budgets=np.zeros(len(labels));available=np.zeros(len(labels),dtype=bool);rules=[];models=np.full(len(labels),'D',dtype=object)
    for k in range(5):
        tr,te=folds!=k,folds==k
        assert not(set(family[tr])&set(family[te]))
        chosen=train([subset(o,tr) for o in options],costs[tr],family[tr])
        if chosen is not None:
            o=next(o for o in options if o['budget']==chosen['budget'])
            pred[te],charge[te],available[te]=apply(chosen,subset(o,te));budgets[te]=o['budget'];models[te]=chosen['model']
        rules.append(dict(path=name,fold=k,chosen=chosen,train_n=int(tr.sum()),test_n=int(te.sum())))
    selected=costs[np.arange(len(labels)),pred]+charge;actual=cpu[np.arange(len(labels)),pred]+charge
    predictions=[]
    for i,r in enumerate(labels):
        predictions.append(dict(path=name,id=r['id'],family=r['family'],cohort=r['cohort'],fold=int(folds[i]),model=models[i],budget=float(budgets[i]),available=bool(available[i]),truth=r['clear'],prediction=CONFIGS[pred[i]],switched=bool(pred[i]),feature_cpu_s=float(charge[i]),selected_PAR2_plus_feature_s=float(selected[i]),D_PAR2_s=float(costs[i,0]),selected_actual_cpu_plus_feature_s=float(actual[i])))
    metrics=[];classes=[]
    for cohort in ('combined300','original48','expanded252'):
        use=np.array([cohort=='combined300' or r['cohort']==cohort for r in labels]);ix=np.flatnonzero(use)
        bi=boot_indices(family[ix],np.random.default_rng(20261029));lo,hi=np.percentile([selected[ix[b]].sum()/costs[ix[b],0].sum() for b in bi],[2.5,97.5])
        cl=np.flatnonzero(use&(truth>=0));bc=boot_indices(family[cl],np.random.default_rng(20261029))
        good=pred[cl]==truth[cl];gain=good.astype(float)-(truth[cl]==0).astype(float);gci=np.percentile([gain[b].mean() for b in bc],[2.5,97.5]);sw=pred[cl]!=0
        metrics.append(dict(path=name,cohort=cohort,cost_valid_n=len(ix),feature_available_n=int(available[ix].sum()),clear_n=len(cl),switch_n=int(sw.sum()),switch_families=len(set(family[cl[sw]])),switch_coverage=float(sw.mean()),switch_accuracy=float(good[sw].mean()) if sw.any() else None,accuracy=float(good.mean()),D_accuracy=float((truth[cl]==0).mean()),accuracy_gain=float(gain.mean()),accuracy_gain_ci_low=float(gci[0]),accuracy_gain_ci_high=float(gci[1]),cost_ratio=float(selected[ix].sum()/costs[ix,0].sum()),cost_ratio_ci_low=float(lo),cost_ratio_ci_high=float(hi),physical_cpu_ratio=float(actual[ix].sum()/cpu[ix,0].sum()),charged_descriptor_cpu_s=float(charge[ix].sum())))
        for c,config in enumerate(CONFIGS):
            hits=pred[cl]==c
            classes.append(dict(path=name,cohort=cohort,config=config,predicted=int(hits.sum()),correct=int((good&hits).sum()),precision=float(good[hits].mean()) if hits.any() else None,coverage=float(hits.mean()),families=len(set(family[cl[hits]]))))
    return metrics,predictions,rules,classes,train(options,costs,family)
