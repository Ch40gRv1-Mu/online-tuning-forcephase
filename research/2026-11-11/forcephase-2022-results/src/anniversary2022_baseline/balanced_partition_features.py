"""R38 balanced full-graph cuts, first-boundary roles and typed rewire control."""
from collections import deque
from concurrent.futures import ProcessPoolExecutor
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import signal
import time

import numpy as np
import pymetis
from scipy.sparse import coo_matrix
from threadpoolctl import threadpool_limits

from .common import sha, write
from .literal_color_features import rewire
from .route_phase_2022 import load_formula
from .scc_quotient_features import parse, normalize
from .signed_peeling_features import signed_summary
from .structural_clusters import DATA, ROOT, read_csv

OUT=DATA/'mechanism_R38_features_20261111'
DTYPE=pymetis.zero_copy_dtype()


def hierarchy(variable,clause,n,m,cpu_started):
    L=len(variable);right=n+clause
    whole=coo_matrix((np.ones(2*L,dtype=DTYPE),
        (np.r_[variable,right],np.r_[right,variable])),shape=(n+m,n+m)).tocsr()
    degree=np.asarray(whole.sum(axis=1)).ravel()
    active=degree>0;ids=np.flatnonzero(active)
    mapping=np.full(n+m,-1,int);mapping[ids]=np.arange(len(ids))
    v,c=mapping[variable],mapping[right]
    graph=whole[ids][:,ids].tocsr();full_degree=degree[ids]
    labels=np.zeros(len(ids),int);roles=np.zeros(len(ids),int)
    vmask,cmask=ids<n,ids>=n
    blocks,cut_curve,topology,checks=[],[],[],0
    boundary=np.zeros(len(ids),bool)
    for level in (1,2,3):
        updated=labels*2
        for group in np.unique(labels):
            members=np.flatnonzero(labels==group)
            if len(members)<8:
                continue
            sub=graph[members][:,members].tocsr()
            if not sub.nnz:
                continue
            options=pymetis.Options(seed=20261138,ncuts=1,niter=10,ufactor=30)
            partition=pymetis.part_graph(2,
                adjacency=pymetis.CSRAdjacency(sub.indptr.astype(DTYPE),sub.indices.astype(DTYPE)),
                eweights=sub.data.astype(DTYPE),recursive=True,options=options)
            parts=np.asarray(partition.vertex_part,int)
            assert parts.shape==(len(members),) and np.array_equal(np.unique(parts),[0,1])
            row=np.repeat(np.arange(len(members)),np.diff(sub.indptr))
            direct=int(sub.data[parts[row]!=parts[sub.indices]].sum())
            assert direct==2*partition.edge_cuts
            checks+=1;updated[members]+=parts
            if time.process_time()-cpu_started>10:
                raise TimeoutError('R38 input10CPU guard')
        assert np.array_equal(updated//2,labels)
        labels=updated
        crossing=labels[v]!=labels[c]
        fraction=float(crossing.mean()) if L else 0.
        assert not cut_curve or fraction>=cut_curve[-1]-1e-14
        cut_curve.append(fraction)
        boundary=np.zeros(len(ids),bool)
        boundary[v[crossing]]=True;boundary[c[crossing]]=True
        roles[(roles==0)&boundary]=level
        counts=np.bincount(labels,minlength=2**level)
        volume=np.bincount(labels,weights=full_degree,minlength=2**level)
        outgoing=np.bincount(labels[v[crossing]],minlength=2**level)+np.bincount(labels[c[crossing]],minlength=2**level)
        occupied=counts>0
        probability=counts[occupied]/max(len(ids),1)
        entropy=float(-(probability*np.log(probability)).sum()/np.log(2**level))
        var_counts=np.bincount(labels[vmask],minlength=2**level)
        topology.extend([fraction,float(np.mean(outgoing[occupied]/np.maximum(volume[occupied],1))) if occupied.any() else 0,
            float(boundary[vmask].mean()) if vmask.any() else 0,
            float(boundary[cmask].mean()) if cmask.any() else 0,
            entropy,float(var_counts.max(initial=0)/max(int(vmask.sum()),1))])
        blocks.append(int(occupied.sum()))
    first=np.where(roles>0,roles,4)
    topology.extend([float(np.dot(first,full_degree)/max(4*full_degree.sum(),1)),
                     float(np.mean(boundary[v]&boundary[c])) if L else 0])
    full_roles=np.zeros(n+m,int);full_roles[ids]=roles
    result=np.asarray(topology,float)
    assert result.shape==(20,) and np.isfinite(result).all()
    return result,full_roles[:n],full_roles[n:],{
        'occupied_regions':blocks,'cut_incidence_fractions':cut_curve,
        'reported_cut_checks':checks,'nested_refinement_check':True,
        'parallel_incidence_weights_preserved':True}


def signed_fields(nodes,clause,widths,n):
    variable=nodes//2;degree=np.bincount(variable,minlength=n)
    active,nonempty=degree>0,widths>0
    positive=(nodes&1)==0
    pd=np.bincount(variable,weights=positive,minlength=n)
    bias=(2*pd-degree)/np.maximum(degree,1)
    weights=np.exp2(-np.minimum(np.maximum(widths[clause]-1,0),60))
    pressure=np.bincount(variable,weights=weights*(2*positive.astype(float)-1),minlength=n)
    pressure/=np.maximum(np.bincount(variable,weights=weights,minlength=n),1e-30)
    pure=(pd==degree).astype(float)-(pd==0)
    vf=np.array([bias,np.abs(bias),pressure,np.abs(pressure),pure])[:,active]
    pos=np.bincount(clause,weights=positive,minlength=len(widths))
    cf=np.array([pos/np.maximum(widths,1),np.abs(2*pos/np.maximum(widths,1)-1),
        pos==widths,pos==0,pos<=1,widths-pos<=1])[:,nonempty].astype(float)
    return vf,cf,degree,active,nonempty


def extract(raw,cpu_started):
    nodes,clause,m,n=parse(raw);nodes,clause,widths,_=normalize(nodes,clause,m)
    m=len(widths);common_done=time.process_time()
    topo,vr,cr,receipt=hierarchy(nodes//2,clause,n,m,cpu_started)
    vf,cf,degree,active,nonempty=signed_fields(nodes,clause,widths,n)
    actual=signed_summary(vf,cf,vr[active],cr[nonempty],degree[active])
    actual_done=time.process_time()
    shuffled=rewire(nodes,clause,widths)
    nt,nv,nc,nrec=hierarchy(shuffled//2,clause,n,m,cpu_started)
    nf,ncf,nd,na,nn=signed_fields(shuffled,clause,widths,n)
    assert np.array_equal(degree,nd) and np.array_equal(active,na) and np.array_equal(nonempty,nn)
    assert np.allclose(vf,nf,atol=1e-12,rtol=1e-12) and np.array_equal(cf,ncf)
    control=signed_summary(nf,ncf,nv[active],nc[nonempty],nd[active])
    assert actual.shape==control.shape==(48,) and np.isfinite(np.r_[actual,control]).all()
    receipt.update(common_CPU_s=common_done-cpu_started,actual_extra_CPU_s=actual_done-common_done,
        null_extra_CPU_s=time.process_time()-actual_done,
        distinct_typed_null=bool(np.linalg.norm(np.r_[topo-nt,actual-control])>1e-6),
        null_cut_incidence_fractions=nrec['cut_incidence_fractions'],
        null_reported_cut_checks=nrec['reported_cut_checks'],first_order_fields_preserved=True)
    return topo,actual,np.r_[nt,control],receipt


def semantic_checks():
    path=[[i,i+1] for i in range(8)]
    variable=np.array([v for c in path for v in c]);clause=np.repeat(np.arange(len(path)),2)
    a=hierarchy(variable,clause,9,8,time.process_time())
    assert a[3]['reported_cut_checks']>0
    # A weighted multigraph control must preserve every parallel incidence.
    v=np.r_[variable,variable[:4]];c=np.r_[clause,clause[:4]]
    b=hierarchy(v,c,9,8,time.process_time())
    assert b[3]['reported_cut_checks']>0 and b[3]['parallel_incidence_weights_preserved']
    v=np.array([0,1,0,1,2,3,2,3,4,5,4,5,6,7,6,7]);c=np.repeat(np.arange(8),2)
    d=hierarchy(v,c,8,8,time.process_time())
    assert d[3]['nested_refinement_check'] and np.isfinite(d[0]).all()
    return {'path_actual_cut_count':True,'parallel_edge_weights':True,
            'disconnected_graph':True,'hierarchy_not_independent_partitions':True,
            'no_optimality_or_relabel_invariance_claim':True,'solver_calls':0}


def collect_one(job):
    key,path,expected = job
    cpu,wall = time.process_time(),time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('R38 input30wall guard')))
    signal.alarm(30)
    try:
        raw = load_formula(Path(path))
        assert hashlib.sha256(raw).hexdigest() == expected
        topology,actual,control,receipt = extract(raw,cpu)
        receipt.update(instance_key=key,raw_sha256=expected,physical_CPU_s=time.process_time()-cpu,
                       wall_s=time.monotonic()-wall)
        if receipt['physical_CPU_s'] > 10:
            raise TimeoutError('R38 input10CPU guard')
        return key,topology,actual,control,receipt
    finally:
        signal.alarm(0)


def main():
    wall,cpu = time.monotonic(),time.process_time()
    initial = resource.getrusage(resource.RUSAGE_CHILDREN)
    OUT.mkdir(exist_ok=False)
    completed,status = 0,'running'
    write(OUT/'owner.json',{'pid':os.getpid(),'source_sha256':sha(__file__),
          'started_UTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'remote_R35_untouched':True})
    try:
        assert importlib.metadata.version('pymetis') == '2025.2.2'
        checks = semantic_checks()
        original = DATA/'mechanism_R21_features_20261111/features.npz'
        with np.load(original) as z:
            keys,base = z['keys'].tolist(),z['topology63'][:,:43].copy()
            eligible = z['eligible'].copy()
        assert len(keys)==4719 and eligible.sum()==2325 and np.array_equal(base[:,42],eligible.astype(float))
        identity={r['instance_key']:r['raw_sha256'] for r in map(json.loads,
                  (DATA/'cnf_graph_cnn_20261110/feature_receipts.jsonl').read_text().splitlines())}
        panel=ROOT/'work/astra_structure_panel_20261110'
        fallback={r['instance_key']:panel/'cnf'/(r['case']+'.cnf') for r in read_csv(panel/'association_only.csv')}
        jobs=[]
        for key,e in zip(keys,eligible):
            if not e:
                continue
            path=ROOT/'work/signed_boundary_20261110/cnf_cache'/(key+'.cnf.gz')
            if not path.is_file():
                path=fallback[key]
            assert path.is_file() and key in identity
            jobs.append((key,str(path),identity[key]))
        index={k:i for i,k in enumerate(keys)}
        topo=np.zeros((len(keys),20));actual=np.zeros((len(keys),48));control=np.zeros((len(keys),68))
        informative=np.zeros(len(keys),bool);fees=np.zeros(len(keys))
        with ProcessPoolExecutor(max_workers=4) as pool,(OUT/'feature_receipts.jsonl').open('x') as stream:
            todo=iter(jobs);pending=deque(pool.submit(collect_one,next(todo)) for _ in range(4))
            while pending:
                key,t,a,r,rec=pending.popleft().result(timeout=max(1,900-(time.monotonic()-wall)))
                i=index[key];topo[i],actual[i],control[i]=t,a,r
                informative[i]=rec['distinct_typed_null'];fees[i]=rec['physical_CPU_s']
                stream.write(json.dumps(rec)+'\n');completed+=1
                if completed%200==0:
                    stream.flush();write(OUT/'progress.json',{'completed':completed,'expected':2325,
                        'wall_s':time.monotonic()-wall,'informative_completed':int(informative.sum())})
                    print(f'R38 collected {completed}/2325 balanced cut hierarchies',flush=True)
                if time.monotonic()-wall>900 or fees.sum()>7200-40:
                    raise TimeoutError('R38 collection planning ceiling')
                job=next(todo,None)
                if job is not None:
                    pending.append(pool.submit(collect_one,job))
        np.savez_compressed(OUT/'features.npz',keys=np.array(keys),eligible=eligible,informative=informative,
            topology63=np.c_[base,topo],signed111=np.c_[base,topo,actual],rewired111=np.c_[base,control],
            measured_feature_CPU_s=fees)
        status='complete'
        write(OUT/'summary.json',{'status':status,'parents':len(keys),'eligible':completed,
            'distinct_typed_null_parents':int(informative.sum()),'new_solver_calls':0,'new_native_calls':0,
            'semantic_checks':checks,'source_sha256':sha(__file__),'base_cache_sha256':sha(original),
            'features_sha256':sha(OUT/'features.npz'),'fee_scope':'Actual physical collection; predictive screen optimistic zero feature/query fees'})
    except BaseException as error:
        write(OUT/'failure.json',{'status':'failed','error':repr(error),'completed':completed,'reward':None})
        raise
    finally:
        usage=resource.getrusage(resource.RUSAGE_CHILDREN)
        write(OUT/'resources.json',{'status':status,'physical_parent_CPU_s':time.process_time()-cpu,
              'physical_child_CPU_s':usage.ru_utime+usage.ru_stime-initial.ru_utime-initial.ru_stime,
              'wall_s':time.monotonic()-wall,'completed':completed,'new_solver_calls':0})


if __name__=='__main__':
    with threadpool_limits(limits=1):
        main()
