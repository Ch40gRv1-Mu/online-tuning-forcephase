"""Shared cost-sensitive threshold evaluation with missing-feature fallback."""
from pathlib import Path
import csv, hashlib, json
import numpy as np
from h01_static_rule import CONFIGS, SEED, boot_indices, read, save_csv

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/expanded_parents/results'

def load_data():
    labels=read(SOURCE/'labels.csv')
    labels=[r for r in labels if r['reason'] not in ('unverified','contended','execution_error','missing')]
    assert len(labels)==291
    features={r['id']:r for r in read(SOURCE/'parent_features.csv')}
    costs=np.array([[float(r[c+'_par2']) for c in CONFIGS] for r in labels])
    cpu=np.array([[float(r[c+'_cpu_s']) for c in CONFIGS] for r in labels])
    truth=np.array([CONFIGS.index(r['clear']) if r['clear'] else -1 for r in labels])
    family=np.array([r['family'] for r in labels])
    groups=sorted(set(family),key=lambda s:hashlib.sha256((SEED+':'+s).encode()).hexdigest())
    foldmap={g:j%5 for j,g in enumerate(groups)}
    folds=np.array([foldmap[g] for g in family])
    return labels,features,costs,cpu,truth,family,folds

def fit(X,costs,charge,family,names,available):
    best=float(costs[:,0].sum());rule=None
    for j,name in enumerate(names):
        observed=available & np.isfinite(X[:,j])
        if not observed.any():continue
        for t in np.unique(np.quantile(X[observed,j],np.arange(1,10)/10)):
            pred=np.zeros(len(X),dtype=int);leafs=[]
            for mask in (observed&(X[:,j]<=t),observed&(X[:,j]>t)):
                c=0
                if mask.sum()>=8 and len(set(family[mask]))>=4:
                    sums=costs[mask].sum(axis=0);winner=int(sums.argmin())
                    if winner and sums[winner]<=.95*sums[0]:c=winner
                pred[mask]=c;leafs.append(CONFIGS[c])
            if not pred.any():continue
            score=float(costs[np.arange(len(X)),pred].sum()+charge.sum())
            if score<best-1e-10:
                best=score;rule=dict(feature=name,threshold=float(t),left=leafs[0],right=leafs[1])
    return rule

def predict(rule,X,names,available):
    pred=np.zeros(len(X),dtype=int)
    if rule is not None:
        v=X[:,names.index(rule['feature'])];valid=available&np.isfinite(v)
        pred[valid&(v<=rule['threshold'])]=CONFIGS.index(rule['left'])
        pred[valid&(v>rule['threshold'])]=CONFIGS.index(rule['right'])
    return pred

def evaluate(name,X,names,available,descriptor,data):
    labels,_,costs,cpu,truth,family,folds=data
    pred=np.zeros(len(labels),dtype=int);charge=np.zeros(len(labels));rules=[]
    for k in range(5):
        train,test=folds!=k,folds==k
        assert not(set(family[train])&set(family[test]))
        rule=fit(X[train],costs[train],descriptor[train],family[train],names,available[train])
        pred[test]=predict(rule,X[test],names,available[test])
        if rule is not None:charge[test]=descriptor[test]
        rules.append(dict(path=name,fold=k,rule=rule,train_n=int(train.sum()),test_n=int(test.sum())))
    selected=costs[np.arange(len(labels)),pred]+charge
    actual=cpu[np.arange(len(labels)),pred]+charge
    predictions=[]
    for i,r in enumerate(labels):
        predictions.append(dict(path=name,id=r['id'],family=r['family'],cohort=r['cohort'],fold=int(folds[i]),available=bool(available[i]),truth=r['clear'],prediction=CONFIGS[pred[i]],switched=bool(pred[i]),feature_cpu_s=float(charge[i]),selected_PAR2_plus_feature_s=float(selected[i]),D_PAR2_s=float(costs[i,0]),selected_actual_cpu_plus_feature_s=float(actual[i])))
    metrics=[]
    for cohort in ('combined300','original48','expanded252'):
        use=np.array([cohort=='combined300' or r['cohort']==cohort for r in labels]);ix=np.flatnonzero(use)
        bi=boot_indices(family[ix],np.random.default_rng(20261029));lo,hi=np.percentile([selected[ix[b]].sum()/costs[ix[b],0].sum() for b in bi],[2.5,97.5])
        cl=np.flatnonzero(use&(truth>=0));bc=boot_indices(family[cl],np.random.default_rng(20261029))
        good=pred[cl]==truth[cl];gain=good.astype(float)-(truth[cl]==0).astype(float)
        gci=np.percentile([gain[b].mean() for b in bc],[2.5,97.5]);sw=pred[cl]!=0
        metrics.append(dict(path=name,cohort=cohort,cost_valid_n=len(ix),feature_available_n=int(available[ix].sum()),clear_n=len(cl),switch_n=int(sw.sum()),switch_families=len(set(family[cl[sw]])),switch_coverage=float(sw.mean()),switch_accuracy=float(good[sw].mean()) if sw.any() else None,accuracy=float(good.mean()),D_accuracy=float((truth[cl]==0).mean()),accuracy_gain=float(gain.mean()),accuracy_gain_ci_low=float(gci[0]),accuracy_gain_ci_high=float(gci[1]),cost_ratio=float(selected[ix].sum()/costs[ix,0].sum()),cost_ratio_ci_low=float(lo),cost_ratio_ci_high=float(hi),physical_cpu_ratio=float(actual[ix].sum()/cpu[ix,0].sum()),charged_descriptor_cpu_s=float(charge[ix].sum())))
    candidate=fit(X,costs,descriptor,family,names,available)
    return metrics,predictions,rules,candidate
