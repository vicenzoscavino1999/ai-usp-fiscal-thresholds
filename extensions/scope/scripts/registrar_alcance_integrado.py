"""Rebuild the explicit post-revision record from frozen decisions and current evidence."""
from pathlib import Path
import json,csv,hashlib
ROOT=Path(__file__).resolve().parents[3];C=ROOT/'extensions/config';O=ROOT/'extensions/scope/resultados'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
facts=read(O/'VERIFICACION_DERIVACIONES.json')['summary']
assert facts['status']=='PASS' and facts['source_policy_cells']==480 and facts['policy_variant_summaries']==24
assert facts['H1_named_order_pairs']==160 and facts['H1_named_order_holds']==100 and facts['H1_commitment_monotonicity_pairs']==1200
assert facts['H4_gained_crossings']==4 and facts['H4_lost_crossings']==0
assert facts['H3_max_abs_revenue_change']<1e-12 and facts['H3_max_abs_q_change']<1e-12 and not facts['H3_fiscal_counterfactual_identified']
history=read(C/'HISTORICAL_SOURCES.json')
for r in history:assert hashlib.sha256((ROOT/r['packaged']).read_bytes()).hexdigest()==r['sha256']
legacyfile=next(ROOT/r['packaged'] for r in history if r['original'].endswith('/hypothesis_adjudication.csv'))
legacy={r['hypothesis_id']:r for r in csv.DictReader(legacyfile.open(encoding='utf-8-sig'))}
rows=[]
for hid,verdict,status,evidence,files,reason in read(C/'HYPOTHESIS_DECISIONS.json')['definitions']:
 rows.append(dict(hypothesis_id=hid,legacy_statement=legacy[hid]['statement'],legacy_verdict=legacy[hid]['verdict'],v2_verdict=verdict,assessment_status=status,confirmatory_status='POST_REVISION_CONDITIONAL_ASSESSMENT_NOT_NEW_PREREGISTRATION',evidence_summary=evidence,evidence_files=files,amendment_reason=reason))
assert [r['hypothesis_id'] for r in rows]==['H1','H2','H3','H4','H5']
assert rows[-1]['v2_verdict'] is None and rows[-1]['assessment_status']=='RETIRED_LEGACY_CLASSIFICATION_RULE' and rows[-1]['amendment_reason']
for r in rows:
 for n in r['evidence_files'].split(';'):assert (O/n).is_file(),n
with (O/'ADJUDICACION_H1_H5_V2.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
diag=read(ROOT/'extensions/convergence/resultados/ANALISIS_CONTROL_EXPOSICION.json')
assert diag['zero_crossing_expectation_status']=='FAIL_RETAINED'
findings={'execution_status':'PASS','hypotheses':{r['hypothesis_id']:r['v2_verdict'] for r in rows},'H5_status':rows[-1]['assessment_status'],'D_LOW_EXPOSURE':'FAIL_RETAINED','low_exposure_threshold':diag['minimum_exposure_B2_numeric'],'low_exposure_test':diag['tested_exposure'],'interpretation':'Conditional scenario evaluation; successful reproduction does not imply all diagnostic expectations hold.','legacy_plan_complete':False,'v2_release_ready':False}
(O/'SCIENTIFIC_FINDINGS.json').write_text(json.dumps(findings,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(findings,ensure_ascii=False))
