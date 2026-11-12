"""Two prespecified readable soft-gain students, original development folds."""

import argparse
import fcntl
from pathlib import Path
import time

import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .interpretable_soft_rules import ALGORITHMS, fit, predict_gains, predict_indices, rules
from .measure_large_linear42 import atomic
from .predict_relative_cost import SPLITS, calibrate, choose, gains
from .score_interpretable_two_percent import evaluate
from .score_static_learnability import fit as teacher_fit
from .score_static_seed_agreement import SEEDS, load_views
from .structural_clusters import ACTIONS, DATA, load, read_csv, write_csv


def main(args):
    began, cpu = time.monotonic(), time.process_time()
    args.out.mkdir(parents=True, exist_ok=False)
    teacher_fits, student_fits, scores = [], [], {}
    with (args.out/'owner.lock').open('w') as lock, threadpool_limits(limits=4):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            keys, _, costs, _, _, _ = load()
            split = read_csv(SPLITS)
            iso_rows = read_csv(DATA/'mechanism_R11_20261111/predictions.csv')
            reference = read_csv(DATA/'mechanism_R27_20261111/predictions.csv')
            assert [r['instance_key'] for r in split] == [r['instance_key'] for r in iso_rows] == [r['instance_key'] for r in reference] == keys
            assert len(keys) == 4719
            x, valid = load_views(keys)[0]['linear42']
            assert valid.all()
            x = x.astype(np.float32)
            inner = np.array([r['inner_validation']=='True' for r in split])
            iso, coarse, fine = [np.array([r[k+'_group'] for r in split]) for k in ('iso','coarse','fine')]
            output = [{'instance_key':key, 'D_PAR2':float(costs[i,0])} for i,key in enumerate(keys)]
            for mode, count in (('iso_diagnostic',5), ('coarse',4), ('fine',5)):
                folds = np.array([int(r['diagnostic_iso_fold']) for r in iso_rows]) if mode=='iso_diagnostic' else np.array([int(r[mode+'_fold']) for r in split])
                groups = fine if mode=='fine' else coarse
                forest = np.array([float(r[mode+'_relative_control_PAR2']) for r in reference])
                action = {a:{v:np.zeros(len(keys),int) for v in ('raw','inner_margin')} for a in ALGORITHMS}
                fidelity = {a:[] for a in ALGORITHMS}
                margins = {a:[] for a in ALGORITHMS}
                teacher_action = np.zeros(len(keys),int)
                for fold in range(count):
                    if time.monotonic()-began>600:
                        raise TimeoutError('Frozen soft-rule comparison exceeded ten minutes')
                    held=folds==fold
                    train=~held & ~inner
                    val=~held & inner
                    assert not (set(iso[held]) & set(iso[train|val]))
                    assert not (set(fine[train]) & set(fine[val]))
                    tick=time.process_time()
                    continuous=[]
                    for seed in SEEDS:
                        tick_fit=time.process_time()
                        teacher=teacher_fit('expressive',x[train],costs[train],seed+fold)
                        continuous.append(gains(teacher,x,'trees_relative'))
                        teacher_fits.append({'mode':mode,'fold':fold,'seed':seed+fold,
                            'train_parents':int(train.sum()),'CPU_s':time.process_time()-tick_fit,
                            'trees':len(teacher.estimators_),
                            'nodes':sum(t.tree_.node_count for t in teacher.estimators_)})
                    soft=np.min(continuous,axis=0)
                    teacher_cut=calibrate(soft[val],costs[val],np.zeros(val.sum()))
                    teacher_action[held]=choose(soft[held],teacher_cut)
                    cache=args.out/'teacher_targets'/f'{mode}_{fold}.npz'
                    cache.parent.mkdir(parents=True,exist_ok=True)
                    np.savez_compressed(cache,keys=np.array(keys),train=train,val=val,held=held,
                        conservative_gain_PAR2_s=soft,seeds=np.array(SEEDS)+fold)
                    atomic(cache.with_suffix('.json'),{'train_mask_sha256_note':'Exact masks and keys saved in bound NPZ; no full-development teacher reused',
                        'cache_sha256':sha(cache),'features_float32_shape':list(x.shape),
                        'source':sha(Path(__file__).with_name('score_static_learnability.py')),
                        'source_driver_sha256':sha(__file__),'split_sha256':sha(SPLITS),
                        'aggregation':'per-direction min3','CPU_s':time.process_time()-tick})
                    for algorithm in ALGORITHMS:
                        tick_student=time.process_time()
                        model=fit(x[train],costs[train],teacher_optional=soft[train],algorithm=algorithm)
                        p=predict_gains(model,x[held])
                        raw=choose(p,0)
                        assert np.array_equal(raw,predict_indices(model,x[held]))
                        cut=calibrate(predict_gains(model,x[val]),costs[val],np.zeros(val.sum()))
                        action[algorithm]['raw'][held]=raw
                        action[algorithm]['inner_margin'][held]=choose(p,cut)
                        exported=rules(model)
                        leafrules=exported['leaf_rules']
                        assert len(leafrules)<=32
                        assert all(len(r['conditions'])<=4 for r in leafrules)
                        atomic(args.out/'fold_policies'/f'{mode}_{algorithm}_{fold}.json',model)
                        atomic(args.out/'rules'/f'{mode}_{algorithm}_{fold}.json',exported)
                        student_fits.append({'mode':mode,'fold':fold,'algorithm':algorithm,
                            'CPU_s':time.process_time()-tick_student,'leaf_rules':len(leafrules),
                            'inner_margin_PAR2_s':cut})
                        margins[algorithm].append({'fold':fold,'margin_PAR2_s':cut})
                        fidelity[algorithm].append({'fold':fold,
                            'mean_abs_teacher_gain_error_PAR2_s':float(np.abs(p-soft[held]).mean()),
                            'raw_teacher_action_agreement':float((raw==choose(soft[held],0)).mean())})
                    atomic(args.out/'progress.json',{'status':'running','mode':mode,'fold':fold,
                        'completed_teacher_fits':len(teacher_fits),'completed_student_fits':len(student_fits)})
                published=np.array([ACTIONS.index(r[mode+'_relative_control_action']) for r in reference])
                assert np.array_equal(teacher_action,published), 'Reconstructed teacher differs from original matched control; preserve failure, do not claim reproduction'
                for algorithm in ALGORITHMS:
                    for variant,a in action[algorithm].items():
                        selected=costs[np.arange(len(keys)),a]
                        score=evaluate(costs[:,0],selected,groups,coarse,mode)
                        score.update(actions={name:int((a==j).sum()) for j,name in enumerate(ACTIONS)},
                            margins=margins[algorithm] if variant=='inner_margin' else None,
                            against_original_forest=evaluate(forest,selected,groups,coarse,mode),
                            teacher_fidelity_diagnostic=fidelity[algorithm])
                        name=f'{mode}_{algorithm}_{variant}'
                        scores[name]=score
                        for i,row in enumerate(output):
                            row[name+'_action']=ACTIONS[a[i]]
                            row[name+'_PAR2']=float(selected[i])
                        print(f'SOFT_RULES {name}: gain={score["gain_pct"]:+.6f}%, solved={score["solved"]}',flush=True)
                write_csv(args.out/'predictions.csv',output)
                atomic(args.out/'summary.json',{'status':'running','scores':scores,'teacher_fits':teacher_fits,'student_fits':student_fits})
            atomic(args.out/'summary.json',{'status':'complete','parents':4719,'scores':scores,
                'teacher_fits':teacher_fits,'student_fits':student_fits,
                'completed_teacher_fits':len(teacher_fits),'completed_student_fits':len(student_fits),
                'user_target_mixed_two_pct':{n:bool(s['gain_pct']>=2 and s['exact_eight_block_95_pct'][0]>0)
                    for n,s in scores.items() if n.startswith('iso_diagnostic_')},
                'teacher_actions_match_original_matched_control':True,
                'CPU_s':time.process_time()-cpu,'wall_s':time.monotonic()-began,
                'source_sha256':sha(__file__),'student_source_sha256':sha(Path(__file__).with_name('interpretable_soft_rules.py')),
                'splits_sha256':sha(SPLITS),'new_solver_calls':0,'new_feature_extractions':0,
                'score_cost_scope':'Free feature/query prediction screen; training teachers charged physically, never queried by deployed student',
                'scope':'Retained4719 Anniversary2022 repeated development; original mixed folds primary, coarse/fine transfer diagnostic, nominal intervals not independent confirmation',
                'capacity':'At most32 leaf conjunctions, <=4 tests per path; either two directional trees or four additive two-output trees',
                'legacy_entropy_warning':'21/26 preserved original reproducible implementation, not interpreted as Shannon diversity'})
        except BaseException as exc:
            atomic(args.out/'failure.json',{'status':'failed','error':repr(exc),
                'completed_teacher_fits':len(teacher_fits),'completed_student_fits':len(student_fits),
                'CPU_s':time.process_time()-cpu,'wall_s':time.monotonic()-began})
            raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=DATA/'interpretable_soft_rules_20261111')
    main(parser.parse_args())
