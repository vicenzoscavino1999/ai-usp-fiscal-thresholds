"""Reject stale document identities, claim links and survey arithmetic."""
from pathlib import Path
import csv,json,shutil
import pytest
import verify_package as v

@pytest.fixture
def small(tmp_path):
    source=Path(v.__file__).resolve().parent
    for rel in ['extensions/config','extensions/scope/evidencia','revision_jpm_v2/paso_07l/evidencia','survey_comparators']:
        shutil.copytree(source/rel,tmp_path/rel)
    # Copy the only additional packaged claim artifact; generated links remain declarative.
    p=tmp_path/'extensions/SCIENTIFIC_SCOPE.md';shutil.copy2(source/'extensions/SCIENTIFIC_SCOPE.md',p)
    return tmp_path

def test_current_documents_claims_and_comparators(small):
    docs=v.check_document_map(small)
    assert v.check_claims(small,docs)[0]==23
    assert len(v.check_surveys(small,docs))==2

def test_changed_word_rejected(small):
    p=small/'revision_jpm_v2/paso_07l/evidencia/SUPLEMENTO_TECNICO_JPM_V2.docx';p.write_bytes(p.read_bytes()+b'stale')
    with pytest.raises(v.PackageError,match='Word hash'):v.check_document_map(small)

def test_stale_full_text_rejected(small):
    p=small/'extensions/scope/evidencia/supp_contenido_vigente.json';d=v.read(p);d['paragraphs'][3]['text']='Previous version';p.write_text(json.dumps(d),encoding='utf-8')
    with pytest.raises(v.PackageError,match='Text extraction'):v.check_document_map(small)

def test_stale_claim_identity_rejected(small):
    docs=v.check_document_map(small);p=small/'extensions/config/MAPA_AFIRMACIONES_Y_EVIDENCIA.csv'
    rows=list(csv.DictReader(p.open(encoding='utf-8-sig')));rows[0]['document_sha256']='0'*64
    with p.open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with pytest.raises(v.PackageError,match='Stale claim'):v.check_claims(small,docs)

def test_missing_claim_source_rejected(small):
    docs=v.check_document_map(small);(small/'extensions/SCIENTIFIC_SCOPE.md').unlink()
    with pytest.raises(v.PackageError,match='Missing claim source'):v.check_claims(small,docs)

def test_altered_survey_arithmetic_rejected(small):
    docs=v.check_document_map(small);p=small/'survey_comparators/aggregates/gmimicro_cost_comparison_baseline-official-v3.csv'
    rows=list(csv.DictReader(p.open(encoding='utf-8-sig')))
    for r in rows:
        if r['primary_variant'].lower()=='true' and r['policy_variant_z']=='pip_ppp_8_30_line':r['cost_micro_lcu']=str(float(r['cost_micro_lcu'])*1.1)
    with p.open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with pytest.raises(v.PackageError,match='arithmetic'):v.check_surveys(small,docs)
