"""Verify the core and all extensions; distinguish execution from scientific outcomes."""
from pathlib import Path
import argparse,json
from verify_results import verify as verify_core
from verify_extensions import verify as verify_extensions
from verify_package import verify as verify_package

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);parser.add_argument('--report',type=Path)
    args=parser.parse_args();root=args.root.resolve();logs=root/'run_logs';logs.mkdir(exist_ok=True)
    core=verify_core(root,logs/'COMPARISON.json');ext=verify_extensions(root)
    try:package=verify_package(root)
    except Exception as exc:package={'status':'FAIL','error':str(exc)}
    (logs/'PACKAGE_CHECK.json').write_text(json.dumps(package,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # verify_core returns the full report; its fixed-seed scope remains unchanged.
    result={'status':'PASS' if core['status']==ext['status']==package['status']=='PASS' else 'FAIL','core_files_passed':core['files_passed'],'extension_files_passed':ext['files_passed'],'files_failed':core['files_failed']+ext['files_failed']+int(package['status']!='PASS'),'documentary_cells':(core.get('documentary_checks') or {}).get('cells_verified'),'figure_pixel_exact':core['figure_pixel_exact'],'scientific_outcomes':(ext.get('semantic') or {}).get('scientific_outcomes'),'scope':'Integrated fixed-input reproduction and registered numerical convergence; scientific outcomes reported separately.','legacy_plan_complete':False,'v2_release_ready':False,'core':core,'extensions':ext,'package':package}
    result['requirements']={'CORE':core['status'],'B_INDEPENDENT':ext['status'],'B_MATCHED_HISTORY':ext['status'],'B_BRIDGE':ext['status'],'B_STRESS':ext['status'],'H_RECORD':ext['status'],'B_INTEGRATION':result['status'],'PUBLIC_PROVENANCE':'NOTICES_INTEGRATED_IN_LOCAL_CANDIDATE' if package['status']=='PASS' else 'FAIL','EDITORIAL_FINAL':'CURRENT_DOCUMENTS_INTEGRATED' if package['status']=='PASS' else 'FAIL','RELEASE':'COMPLETE_PASS_REQUIRES_VERIFY_COMPLETE_AND_SURVEYS'}
    dest=args.report or logs/'COMPARISON_FULL.json';dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['core','extensions']},ensure_ascii=False,indent=2))
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
