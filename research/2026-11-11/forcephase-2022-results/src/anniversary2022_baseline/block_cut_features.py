"""Static cyclic-module separators; no assignment, search or solution flag."""
from collections import deque
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import time

import numpy as np
from scipy.sparse import coo_matrix
from threadpoolctl import threadpool_limits

from .common import sha, write
from .route_phase_2022 import load_formula
from .scc_quotient_features import parse, normalize
from .signed_peeling_features import shuffle_roles, signed_summary
from .structural_clusters import DATA, ROOT, read_csv

OUT = DATA/'mechanism_R37_features_20261111'


def decompose(variable, clause, n, m, cpu_started):
    edges, vertices = len(variable), n+m
    endpoint = n+clause
    eid = np.arange(1, edges+1, dtype=np.int64)
    graph = coo_matrix((np.r_[eid,eid], (np.r_[variable,endpoint],np.r_[endpoint,variable])),
                       shape=(vertices,vertices)).tocsr()
    assert graph.nnz == 2*edges, 'Normalization must remove duplicate incidences'
    degree = np.diff(graph.indptr)
    disc = np.full(vertices,-1,int); low = np.zeros(vertices,int)
    parent = np.full(vertices,-1,int); parentedge = np.full(vertices,-1,int)
    position = graph.indptr[:-1].copy()
    edge_stack, members, sizes, nvars, cyclic = [], [], [], [], []
    tick, operations = 0, 0
    for root in np.flatnonzero(degree):
        if disc[root] >= 0:
            continue
        stack = [int(root)]; disc[root] = low[root] = tick; tick += 1
        while stack:
            u = stack[-1]
            operations += 1
            if operations % 8192 == 0 and time.process_time()-cpu_started > 10:
                raise TimeoutError('R37 input10CPU guard')
            if position[u] < graph.indptr[u+1]:
                at = position[u]; position[u] += 1
                v, edge = int(graph.indices[at]), int(graph.data[at])-1
                if disc[v] < 0:
                    parent[v], parentedge[v] = u, edge
                    edge_stack.append(edge); disc[v] = low[v] = tick; tick += 1
                    stack.append(v)
                elif edge != parentedge[u] and disc[v] < disc[u]:
                    low[u] = min(low[u],disc[v]); edge_stack.append(edge)
            else:
                stack.pop(); p = parent[u]
                if p < 0:
                    assert not edge_stack
                    continue
                low[p] = min(low[p],low[u])
                if low[u] < disc[p]:
                    continue
                block = []
                while True:
                    edge = edge_stack.pop(); block.append(edge)
                    if edge == parentedge[u]:
                        break
                block = np.asarray(block,int)
                vs, cs = np.unique(variable[block]), np.unique(endpoint[block])
                members.append(np.r_[vs,cs]); sizes.append(len(block)); nvars.append(len(vs))
                cyclic.append(len(block) >= len(vs)+len(cs))
    sizes, nvars, cyclic = np.asarray(sizes,int),np.asarray(nvars,int),np.asarray(cyclic,bool)
    assert sizes.sum() == edges
    qual = cyclic & (nvars >= 3)
    b = len(members)
    all_members = np.concatenate(members) if members else np.zeros(0,int)
    membership_count = np.bincount(all_members,minlength=vertices)
    art = membership_count > 1
    art_ids = np.flatnonzero(art)
    art_map = np.full(vertices,-1,int); art_map[art_ids] = np.arange(len(art_ids))
    block_edges, arti_edges = [], []
    inqual = np.zeros(vertices,bool)
    for j, nodes in enumerate(members):
        if qual[j]:
            inqual[nodes] = True
        a = nodes[art[nodes]]
        block_edges.extend([j]*len(a)); arti_edges.extend((b+art_map[a]).tolist())
    total_nodes = b+len(art_ids)
    bt = coo_matrix((np.ones(2*len(block_edges),int),
        (np.r_[block_edges,arti_edges],np.r_[arti_edges,block_edges])),
        shape=(total_nodes,total_nodes)).tocsr()
    weight = np.r_[np.where(qual,nvars,0),np.zeros(len(art_ids),int)]
    tree_parent = np.full(total_nodes,-2,int); component = np.full(total_nodes,-1,int)
    order, roots = [], []
    for root in range(total_nodes):
        if tree_parent[root] != -2:
            continue
        roots.append(root); tree_parent[root] = -1; component[root] = len(roots)-1
        todo = [root]
        while todo:
            u = todo.pop(); order.append(u)
            for v in bt.indices[bt.indptr[u]:bt.indptr[u+1]]:
                if v == tree_parent[u]:
                    continue
                assert tree_parent[v] == -2, 'Block-articulation incidence must be a forest'
                tree_parent[v] = u; component[v] = component[u]; todo.append(int(v))
    assert bt.nnz//2 == total_nodes-len(roots)
    subtree = weight.copy()
    far = np.where(weight > 0,0,-10**9)
    diameter = 0
    for u in reversed(order):
        distances = [0] if weight[u] else []
        for v in bt.indices[bt.indptr[u]:bt.indptr[u+1]]:
            if tree_parent[v] == u and far[v] >= 0:
                distances.append(int(far[v])+1)
        if distances:
            distances.sort(reverse=True); far[u] = distances[0]
            if len(distances) >= 2:
                diameter = max(diameter,distances[0]+distances[1])
        if tree_parent[u] >= 0:
            subtree[tree_parent[u]] += subtree[u]
    totals = np.array([subtree[u] for u in roots])
    connector = np.zeros(vertices,bool); balance = np.zeros(vertices,float)
    for j,u in enumerate(art_ids):
        node = b+j; total = totals[component[node]]
        branches = [int(subtree[v]) if tree_parent[v] == node else int(total-subtree[node])
                    for v in bt.indices[bt.indptr[node]:bt.indptr[node+1]]]
        assert sum(branches) == total
        if sum(mass > 0 for mass in branches) >= 2:
            connector[u] = True; balance[u] = 1-max(branches)/total
    roles = np.where(connector,np.where(balance >= .1,3,2),np.where(inqual,1,0))
    active = degree > 0; av, ac = max(int(active[:n].sum()),1),max(int(active[n:].sum()),1)
    probability = sizes/max(edges,1)
    entropy = float(-(probability*np.log(np.maximum(probability,1e-30))).sum()/np.log(b)) if b > 1 else 0.
    qualified_mass = int(nvars[qual].sum())
    largest = int(nvars[qual].max(initial=0))
    cb = balance[connector]
    excess = sum(int(size-len(nodes)+1) for size,nodes in zip(sizes,members))
    topology = np.array([np.log1p(b),np.log1p(qual.sum()),
        sizes[cyclic].sum()/max(edges,1),sizes[sizes == 1].sum()/max(edges,1),
        largest/av,qualified_mass/max(int(nvars.sum()),1),
        float(inqual[:n].sum())/av,float(inqual[n:].sum())/ac,
        float(art[:n].sum())/av,float(art[n:].sum())/ac,
        float(connector[:n].sum())/av,float(connector[n:].sum())/ac,
        cb.max(initial=0),cb.mean() if len(cb) else 0,np.log1p(diameter),
        (qualified_mass-largest)/max(qualified_mass,1),np.log1p(totals.max(initial=0)),
        excess/max(edges,1),entropy,np.log1p(nvars[qual]).mean() if qual.any() else 0])
    assert topology.shape == (20,) and np.isfinite(topology).all()
    return topology,roles[:n],roles[n:],{
        'blocks':b,'qualifying_cyclic_blocks':int(qual.sum()),'balanced_connector':bool((roles == 3).any()),
        'max_balance':float(cb.max(initial=0)),'qualifying_block_diameter':int(diameter),
        'cyclic_membership_mass':qualified_mass,'edge_partition_check':True,'block_forest_check':True}


def extract(raw,cpu_started):
    nodes,clause,m,n = parse(raw)
    nodes,clause,widths,_ = normalize(nodes,clause,m)
    variable, m = nodes//2,len(widths)
    topology,vr,cr,receipt = decompose(variable,clause,n,m,cpu_started)
    degree = np.bincount(variable,minlength=n)
    active,nonempty = degree > 0,widths > 0
    positive = (nodes & 1) == 0
    pd = np.bincount(variable,weights=positive,minlength=n)
    bias = (2*pd-degree)/np.maximum(degree,1)
    w = np.exp2(-np.minimum(np.maximum(widths[clause]-1,0),60))
    pressure = np.bincount(variable,weights=w*(2*positive.astype(float)-1),minlength=n)
    pressure /= np.maximum(np.bincount(variable,weights=w,minlength=n),1e-30)
    pure = (pd == degree).astype(float)-(pd == 0)
    vf = np.array([bias,np.abs(bias),pressure,np.abs(pressure),pure])[:,active]
    pos = np.bincount(clause,weights=positive,minlength=m)
    cf = np.array([pos/np.maximum(widths,1),np.abs(2*pos/np.maximum(widths,1)-1),
                   pos == widths,pos == 0,pos <= 1,widths-pos <= 1])[:,nonempty].astype(float)
    vr,cr = vr[active],cr[nonempty]
    actual = signed_summary(vf,cf,vr,cr,degree[active])
    rng = np.random.default_rng(20261137)
    rvr,rcr = shuffle_roles(vr,degree[active],rng),shuffle_roles(cr,widths[nonempty],rng)
    control = signed_summary(vf,cf,rvr,rcr,degree[active])
    assert actual.shape == control.shape == (48,) and np.isfinite(np.r_[actual,control]).all()
    return topology,actual,control,receipt


def semantic_checks():
    def fixture(n,clauses):
        raw=(f'p cnf {n} {len(clauses)}\n'+'\n'.join(' '.join(map(str,c))+' 0' for c in clauses)+'\n').encode()
        return extract(raw,time.process_time())
    a=fixture(3,[[1,2],[2,3]])[3]
    assert a['qualifying_cyclic_blocks']==0 and not a['balanced_connector']
    a=fixture(3,[[1,2],[2,3],[3,1]])[3]
    assert a['qualifying_cyclic_blocks']==1 and not a['balanced_connector']
    figure=[[1,2],[2,3],[3,1],[3,4],[4,5],[5,3]]
    a=fixture(5,figure)
    assert a[3]['qualifying_cyclic_blocks']==2 and a[3]['balanced_connector']
    assert a[3]['max_balance']==.5 and a[3]['qualifying_block_diameter']==2
    bridge=[[1,2],[2,3],[3,1],[4,5],[5,6],[6,4],[3,4]]
    b=fixture(6,bridge)
    assert b[3]['qualifying_cyclic_blocks']==2 and b[3]['qualifying_block_diameter']==6
    permutation={1:5,2:1,3:4,4:2,5:3}
    moved=[[permutation[v] for v in c] for c in figure[::-1]]
    c=fixture(5,moved)
    assert np.allclose(a[0],c[0]) and np.allclose(a[1],c[1])
    return {'path':True,'single_cycle':True,'two_cycles_hinge':True,'bridge_chain':True,
            'variable_and_clause_reordering':True,'solver_calls':0}


def collect_one(job):
    key,path,expected = job
    cpu,wall = time.process_time(),time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('R37 input30wall guard')))
    signal.alarm(30)
    try:
        raw = load_formula(Path(path))
        assert hashlib.sha256(raw).hexdigest() == expected
        topology,actual,control,receipt = extract(raw,cpu)
        receipt.update(instance_key=key,raw_sha256=expected,physical_CPU_s=time.process_time()-cpu,
                       wall_s=time.monotonic()-wall)
        if receipt['physical_CPU_s'] > 10:
            raise TimeoutError('R37 input10CPU guard')
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
        topo=np.zeros((len(keys),20));actual=np.zeros((len(keys),48));control=np.zeros_like(actual)
        informative=np.zeros(len(keys),bool);fees=np.zeros(len(keys))
        with ProcessPoolExecutor(max_workers=4) as pool,(OUT/'feature_receipts.jsonl').open('x') as stream:
            todo=iter(jobs);pending=deque(pool.submit(collect_one,next(todo)) for _ in range(4))
            while pending:
                key,t,a,r,rec=pending.popleft().result(timeout=max(1,900-(time.monotonic()-wall)))
                i=index[key];topo[i],actual[i],control[i]=t,a,r
                informative[i]=rec['balanced_connector'];fees[i]=rec['physical_CPU_s']
                stream.write(json.dumps(rec)+'\n');completed+=1
                if completed%200==0:
                    stream.flush();write(OUT/'progress.json',{'completed':completed,'expected':2325,
                        'wall_s':time.monotonic()-wall,'informative_completed':int(informative.sum())})
                    print(f'R37 collected {completed}/2325 block-cut forests',flush=True)
                if time.monotonic()-wall>900 or fees.sum()>7200-40:
                    raise TimeoutError('R37 collection planning ceiling')
                job=next(todo,None)
                if job is not None:
                    pending.append(pool.submit(collect_one,job))
        np.savez_compressed(OUT/'features.npz',keys=np.array(keys),eligible=eligible,informative=informative,
            topology63=np.c_[base,topo],signed111=np.c_[base,topo,actual],random111=np.c_[base,topo,control],
            measured_feature_CPU_s=fees)
        status='complete'
        write(OUT/'summary.json',{'status':status,'parents':len(keys),'eligible':completed,
            'balanced_connector_parents':int(informative.sum()),'new_solver_calls':0,'new_native_calls':0,
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
