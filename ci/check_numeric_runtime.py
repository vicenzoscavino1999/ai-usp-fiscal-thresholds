"""Check the pinned NumPy dispatch route before the offline reproduction."""
from pathlib import Path
import argparse,json,os,platform
import numpy as np
from numpy._core import _multiarray_umath as runtime

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    disabled=os.environ.get('NPY_DISABLE_CPU_FEATURES','').replace(',',' ').split()
    if 'X86_V4' not in disabled or runtime.__cpu_features__.get('X86_V4',False):
        raise RuntimeError('The reproducible NumPy route requires X86_V4 disabled before import.')
    if np.__version__!='2.5.1' or 'X86_V4' not in runtime.__cpu_dispatch__:
        raise RuntimeError('Unexpected NumPy version or dispatch build; use the pinned Docker image.')
    report={'status':'PASS','numpy':np.__version__,'architecture':platform.machine(),
            'NPY_DISABLE_CPU_FEATURES':os.environ['NPY_DISABLE_CPU_FEATURES'],
            'cpu_features':runtime.__cpu_features__,'dispatch_build':runtime.__cpu_dispatch__,
            'purpose':'Same transcendental calculation route as the frozen references; numeric tolerances and exact hashes unchanged.'}
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
