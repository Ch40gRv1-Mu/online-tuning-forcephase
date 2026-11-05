"""Budget/threshold selection happens strictly within each training-family fold."""
import hashlib,json
import numpy as np
from simple_selection import fit,predict,CONFIGS,boot_indices

def fit_options(options,costs,family):
    best=float(costs[:,0].sum());chosen=None
    for option in options:
        rule=fit(option['X'],costs,option['charge'],family,option['names'],option['available'])
        if rule is None:continue
        pred=predict(rule,option['X'],option['names'],option['available'])
        score=float(costs[np.arange(len(costs)),pred].sum()+option['charge'].sum())
        if score<best-1e-10:best=score;chosen=dict(budget=option['budget'],rule=rule)
    return chosen

def evaluate_options(name,options,data):
    labels,_,costs,cpu,truth,family,folds=data
    pred=np.zeros(len(labels),dtype=int);charge=np.zeros(len(labels));budgets=np.zeros(len(labels));available=np.zeros(len(labels),dtype=bool);rules=[]
    for k in range(5):
        train,test=folds!=k,folds==k
        assert not(set(family[train])&set(family[test]))
        train_options=[dict(o,X=o['X'][train],charge=o['charge'][train],available=o['available'][train]) for o in options]
        chosen=fit_options(train_options,costs[train],family[train])
        if chosen is not None:
            o=next(o for o in options if o['budget']==chosen['budget'])
            pred[test]=predict(chosen['rule'],o['X'][test],o['names'],o['available'][test])
            charge[test]=o['charge'][test];budgets[test]=o['budget'];available[test]=o['available'][test]
        rules.append(dict(path=name,fold=k,chosen=chosen,train_n=int(train.sum()),test_n=int(test.sum())))
    selected=costs[np.arange(len(labels)),pred]+charge;actual=cpu[np.arange(len(labels)),pred]+charge
    predictions=[]
    for i,r in enumerate(labels):
        predictions.append(dict(path=name,id=r['id'],family=r['family'],cohort=r['cohort'],fold=int(folds[i]),budget=float(budgets[i]),available=bool(available[i]),truth=r['clear'],prediction=CONFIGS[pred[i]],switched=bool(pred[i]),feature_cpu_s=float(charge[i]),selected_PAR2_plus_feature_s=float(selected[i]),D_PAR2_s=float(costs[i,0]),selected_actual_cpu_plus_feature_s=float(actual[i])))
    metrics=[]
    for cohort in ('combined300','original48','expanded252'):
        use=np.array([cohort=='combined300' or r['cohort']==cohort for r in labels]);ix=np.flatnonzero(use)
        bi=boot_indices(family[ix],np.random.default_rng(20261029));lo,hi=np.percentile([selected[ix[b]].sum()/costs[ix[b],0].sum() for b in bi],[2.5,97.5])
        cl=np.flatnonzero(use&(truth>=0));bc=boot_indices(family[cl],np.random.default_rng(20261029))
        good=pred[cl]==truth[cl];gain=good.astype(float)-(truth[cl]==0).astype(float);gci=np.percentile([gain[b].mean() for b in bc],[2.5,97.5]);sw=pred[cl]!=0
        metrics.append(dict(path=name,cohort=cohort,cost_valid_n=len(ix),feature_available_n=int(available[ix].sum()),clear_n=len(cl),switch_n=int(sw.sum()),switch_families=len(set(family[cl[sw]])),switch_coverage=float(sw.mean()),switch_accuracy=float(good[sw].mean()) if sw.any() else None,accuracy=float(good.mean()),D_accuracy=float((truth[cl]==0).mean()),accuracy_gain=float(gain.mean()),accuracy_gain_ci_low=float(gci[0]),accuracy_gain_ci_high=float(gci[1]),cost_ratio=float(selected[ix].sum()/costs[ix,0].sum()),cost_ratio_ci_low=float(lo),cost_ratio_ci_high=float(hi),physical_cpu_ratio=float(actual[ix].sum()/cpu[ix,0].sum()),charged_descriptor_cpu_s=float(charge[ix].sum())))
    return metrics,predictions,rules,fit_options(options,costs,family)
