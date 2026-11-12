"""Metered pinned-source build for R33, after existing native timing terminates."""
import argparse
from pathlib import Path
import resource
import subprocess
import tarfile
import time

from .common import sha
from .measure_large_linear42 import atomic
from .structural_clusters import ROOT


def main(wrapper_only=False,profile='v2'):
    wall,cpu=time.monotonic(),time.process_time()
    usage=resource.getrusage(resource.RUSAGE_CHILDREN);initial=usage.ru_utime+usage.ru_stime
    work=ROOT/'work/preprocess_structure_20261111';work.mkdir(exist_ok=True)
    receipt=work/(f'build_{profile}_receipt.json' if wrapper_only else 'build_receipt.json')
    assert not receipt.exists(),'Preserve existing build receipt'
    archive=ROOT/'work/phase_prediction_20261104/project/vendor/cadical-src.tar.gz'
    prefix='cadical-c60730422e758ef1cebe7aeddf2dda31c996bf04'
    source=work/prefix
    commands=[];matched=False
    try:
        if not source.exists():
            with tarfile.open(archive) as bundle:
                assert all(n==prefix or n.startswith(prefix+'/') for n in bundle.getnames())
                bundle.extractall(work,filter='data')
        for name in ('decide.cpp','internal.cpp','options.hpp'):
            assert sha(source/'src'/name)==sha(ROOT/'work/default_D_source_20261111'/name)
        matched=True
        binary=work/(f'preprocess_structure_{profile}' if wrapper_only else 'preprocess_structure')
        stages=[] if wrapper_only else [(['./configure','-q'],source),(['make','-j4','libcadical.a'],source/'build')]
        stages.append((['c++','-std=c++11','-O3','-DNDEBUG','-I',str(source/'src'),
                  str(ROOT/'src/anniversary2022_baseline/preprocess_structure.cpp'),
                  str(source/'build/libcadical.a'),'-o',str(binary)],work))
        with (work/(f'build_{profile}.log' if wrapper_only else 'build.log')).open('w') as log:
            for command,cwd in stages:
                commands.append(command)
                subprocess.run(command,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        status='complete'
    except BaseException as exc:
        status='failed';error=repr(exc)
        raise
    finally:
        usage=resource.getrusage(resource.RUSAGE_CHILDREN)
        rec={'status':status,'commands':commands,'source_archive_sha256':sha(archive),
            'pinned_source_commit':'c60730422e758ef1cebe7aeddf2dda31c996bf04',
            'source_matches_previous_pinned_decide_internal_options':matched,
            'physical_parent_CPU_s':time.process_time()-cpu,'physical_child_CPU_s':usage.ru_utime+usage.ru_stime-initial,
            'wall_s':time.monotonic()-wall,'driver_source_sha256':sha(__file__),
            'wrapper_source_sha256':sha(ROOT/'src/anniversary2022_baseline/preprocess_structure.cpp')}
        if status=='failed':rec['error']=error
        else:rec.update(native_binary_sha256=sha(binary),pinned_library_reused=wrapper_only,
            pinned_library_sha256=sha(source/'build/libcadical.a'),native_binary=str(binary))
        atomic(receipt,rec)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wrapper-only',action='store_true')
    parser.add_argument('--profile',choices=('v2','v3','v4'),default='v2')
    args=parser.parse_args();main(args.wrapper_only,args.profile)
