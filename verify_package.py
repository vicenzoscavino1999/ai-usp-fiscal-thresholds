"""Check documentary integration and source notices; this does not run simulations."""
from pathlib import Path
import argparse, csv, hashlib, json, math, zipfile, xml.etree.ElementTree as ET

NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
class PackageError(Exception):pass
def require(ok,message):
    if not ok:raise PackageError(message)
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def local(root,name):
    require(isinstance(name,str) and '\\' not in name and ':' not in name,'Nonportable path: '+str(name))
    path=(root/name).resolve();require(path.is_relative_to(root.resolve()),'Path escapes package: '+name);return path
def xml_doc(path):
    with zipfile.ZipFile(path) as z:body=z.read('word/document.xml')
    return body,ET.fromstring(body)
def check_document_map(root):
    docs=read(root/'extensions/config/DOCUMENT_MAP.json');require(len(docs)==2 and {d['tag'] for d in docs}=={'main','supp'},'Two document tags required')
    by_path={}
    for d in docs:
        p=local(root,d['packaged']);require(sha(p)==d['sha256'],'Current Word hash differs: '+d['tag'])
        body,xml=xml_doc(p);require(hashlib.sha256(body).hexdigest()==d['body_xml_sha256'],'Word body differs')
        pars=xml.findall('w:body/w:p',NS);tabs=xml.findall('w:body/w:tbl',NS)
        require((len(pars),len(tabs),len(xml.findall('.//m:oMath',NS)))==(d['paragraphs'],d['tables'],d['equations']),'Document structure differs')
        text=[''.join(t.text or '' for t in p.findall('.//w:t',NS)) for p in pars]
        ext=read(root/f'extensions/scope/evidencia/{d["tag"]}_contenido_vigente.json')
        require(ext['source']==d['packaged'] and ext['sha256']==d['sha256'],'Stale text-extraction identity')
        require([p['text'] for p in ext['paragraphs']]==text,'Text extraction differs from current Word')
        tabtext=[{'table_index':i,'rows':[[''.join(t.text or '' for t in c.findall('.//w:t',NS)) for c in row.findall('w:tc',NS)] for row in tb.findall('w:tr',NS)]} for i,tb in enumerate(tabs)]
        require(ext['tables']==tabtext,'Table extraction differs')
        by_path[d['packaged']]={'sha256':d['sha256'],'paragraphs':text,'math_counts':[len(p.findall('.//m:oMath',NS)) for p in pars]}
    return by_path
def check_claims(root,by_path):
    with (root/'extensions/config/MAPA_AFIRMACIONES_Y_EVIDENCIA.csv').open(encoding='utf-8-sig',newline='') as f:claims=list(csv.DictReader(f))
    require(len(claims)==23 and len({r['claim_id'] for r in claims})==23,'Claim inventory differs')
    links=read(root/'extensions/config/PACKAGE_LINKS.json')['links'];lookup={e['path']:e['kind'] for e in links}
    require(len(lookup)==len(links),'Duplicate active link')
    active={n for r in claims for k in ['artifacts','validation'] for n in r[k].split(';')}
    require(set(lookup)==active,'Active-link inventory differs')
    for r in claims:
        require(r['document'] in by_path,'Claim points to a noncurrent Word')
        doc=by_path[r['document']];require(r['document_sha256']==doc['sha256'],'Stale claim hash')
        ix=[int(i) for i in r['paragraph_indices'].split(';')]
        require(bool(ix) and all(0<=i<len(doc['paragraphs']) and (doc['paragraphs'][i].strip() or doc['math_counts'][i]) for i in ix),'Invalid or empty claim paragraph')
        for k in ['artifacts','validation']:
            for n in r[k].split(';'):
                p=local(root,n);kind=lookup[n]
                require(kind in {'packaged_source','generated_by_reproduction','generated_by_package_verifier'},'Unknown link kind')
                if kind=='packaged_source':require(p.is_file(),'Missing claim source: '+n)
        if r['claim_id']=='M_MICRO':require(r['current_status']=='RAW_SURVEY_RECONSTRUCTION_VERIFIED_MODULE_INTEGRATED','Survey scope overstated')
    return len(claims),len(links)
def check_surveys(root,by_path):
    specs=[('PER','gmimicro_cost_comparison_baseline-official-v3.csv',-7.734),('CHL','gmimicro_chl_cost_comparison_baseline-official-v3.csv',.387)]
    out=[]
    for country,name,rounded in specs:
        with (root/'survey_comparators/aggregates'/name).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        selected=[r for r in rows if r['primary_variant'].lower()=='true' and r['policy_variant_z']=='pip_ppp_8_30_line' and r['micro_gmi_version'].startswith('GMI_ideal_')]
        require(len(selected)==1,'Expected one primary income comparator: '+country);r=selected[0]
        require(r['country_id']==country and r['welfare_concept']==('income' if country=='PER' else 'primary_total_corrected_income') and float(r['theta_target'])==float(r['chi_gmi'])==1,'Survey comparator definition differs')
        value=(float(r['cost_micro_lcu'])/float(r['cost_official_aggregate_lcu'])-1)*100
        require(math.isclose(value,float(r['difference_percent_vs_official']),rel_tol=0,abs_tol=1e-10),'Survey aggregate arithmetic differs')
        require(round(value,3)==rounded,'Survey comparison differs from manuscript')
        out.append({'country':country,'difference_percent':value,'rounded':rounded,'scope':'PRESERVED_AGGREGATES_ONLY','microdata_reexecuted':False})
    main=next(d for p,d in by_path.items() if p.endswith('/MANUSCRITO_JPM_V2.docx'))
    require('7.734' in main['paragraphs'][67] and '0.387' in main['paragraphs'][67],'Survey numbers missing from mapped paragraph')
    return out
def check_release_status(root):
    status=read(root/'RELEASE_STATUS.json')
    require(status['version']=='2.0.0' and status['distribution_stage']=='PREPARED_FOR_ARCHIVE','Unknown release source state')
    require(status['v2_release_ready'] is True and status['published'] is False,'Source archive must record preparation, not assert external publication')
    require(status['version_doi']=='10.5281/zenodo.24257720','Version DOI differs')
    baseline=read(root/'release/BASELINE_VERIFICATION.json')
    require(baseline['status']=='PASS' and baseline['commit']==status['scientific_baseline']['commit'],'Unverified scientific baseline')
    require({r['environment'] for r in baseline['comparisons']}=={'local','github_actions'},'Both baseline environments required')
    for r in baseline['comparisons']:
        require(r['status']=='PASS' and (r['core'],r['extensions'],r['survey_tables'],r['document_cells'],r['stages'])==(77,88,4,164,39) and r['figure_pixel_exact'],'Incomplete baseline reproduction')
        require(r['tests']=={'tests':151,'failures':0,'errors':0,'skipped':0},'Baseline test record differs')
    require(status['scientific_outcomes']==baseline['scientific_outcomes_preserved'],'Scientific findings relabelled during publication')
    protected=read(root/'release/SCIENTIFIC_BASELINE.json')
    require(protected['baseline_manifest_sha256']==baseline['source_manifest_sha256'],'Baseline identity differs')
    require(bool(protected['protected_files']),'No protected scientific files')
    for name,digest in protected['protected_files'].items():
        require(sha(local(root,name))==digest,'Scientific baseline changed: '+name)
    require(status['editorial_final']['micro_comparison_status']=='RAW_SURVEY_RECONSTRUCTION_VERIFIED_MODULE_INTEGRATED','Survey reconstruction scope changed')
    require(status['requirements']['PUBLIC_PROVENANCE']=='SOURCE_NOTICES_INTEGRATED','Notice integration status differs')
    require(status['requirements']['EDITORIAL_FINAL']=='CURRENT_DOCUMENTS_INTEGRATED','Document integration status differs')
    return {'distribution_stage':status['distribution_stage'],'version':status['version'],'version_doi':status['version_doi'],'protected_scientific_files':len(protected['protected_files']),'external_publication_evaluated':False}

def verify(root,source_only=False):
    root=root.resolve();manifest=read(root/'SOURCE_MANIFEST.json');sources=manifest['files']
    require(bool(sources),'Empty source manifest')
    for n,h in sources.items():
        p=local(root,n);require(p.is_file() and sha(p)==h,'Source missing or changed: '+n)
    if source_only:
        actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
        require(actual==set(sources)|{'SOURCE_MANIFEST.json'},'Extra or missing source payload')
    rights=read(root/'provenance_public/FILE_RIGHTS.json');records=rights['files'];expected=set(sources)|{'SOURCE_MANIFEST.json'}
    require(len(records)==len(expected) and {r['path'] for r in records}==expected,'Rights inventory does not cover current candidate')
    catalog=read(root/'provenance_public/SOURCE_CATALOG.json')
    require(bool(catalog.get('sources')),'Missing source catalogue')
    for r in records:
        p=local(root,r['path']);require(bool(r['rights_scope']) and bool(r['release_action']) and bool(r['source_ids']),'Incomplete source notice')
        require(set(r['source_ids'])<=set(catalog['sources']),'Unknown source identifier')
        if r['path'] in {'SOURCE_MANIFEST.json','provenance_public/FILE_RIGHTS.json'}:require(r['sha256'] is None and r.get('hash_policy'),'Recursive inventory hash must be explicitly scoped')
        else:require(r['sha256']==sources[r['path']]==sha(p),'Stale rights inventory hash: '+r['path'])
    for n in ['LICENSE','LICENSE-DATA','THIRD_PARTY_NOTICES.md','DATA_AVAILABILITY.md','revision_jpm_v2/paso_07d/conciliacion_fiscal_02/fuentes/BFJZ_LICENSE.txt']:
        require(n in sources,'Missing mandatory notice: '+n)
    require('provenance_public/FILE_RIGHTS.json' in (root/'LICENSE-DATA').read_text(encoding='utf-8'),'Data licence points to old inventory')
    by_path=check_document_map(root);claims,links=check_claims(root,by_path);surveys=check_surveys(root,by_path)
    release=check_release_status(root)
    return {'status':'PASS','scope':'Static package and document checks. A complete-run result additionally requires the core and the raw-survey reconstruction.','source_files_verified':len(sources),'rights_files_covered':len(records),'documents_verified':2,'claims_verified':claims,'links_verified':links,'survey_aggregate_comparisons':surveys,'clean_reproduction_of_this_candidate':False,'v2_release_ready':False,'release_source':release}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);ap.add_argument('--report',type=Path);ap.add_argument('--source-only',action='store_true');a=ap.parse_args()
    try:result=verify(a.root,a.source_only)
    except Exception as exc:result={'status':'FAIL','error':str(exc),'v2_release_ready':False}
    p=a.report or a.root/'run_logs/PACKAGE_CHECK.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False));return int(result['status']!='PASS')
if __name__=='__main__':raise SystemExit(main())
