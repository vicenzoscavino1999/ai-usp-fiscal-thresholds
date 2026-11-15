"""Publication metadata must preserve the actual verification outcome."""
from pathlib import Path
import copy, json, pytest
import verify_package as v

def test_release_source_with_adverse_findings_is_valid():
    root=Path(v.__file__).resolve().parent
    result=v.check_release_status(root)
    assert result['version']=='2.0.0' and not result['external_publication_evaluated']

@pytest.mark.parametrize('case',['publication','baseline_failure','relabelled_science','altered_source'])
def test_invalid_release_claim_rejected(monkeypatch,case):
    root=Path(v.__file__).resolve().parent
    original=v.read
    def changed(path):
        data=copy.deepcopy(original(path))
        if path.name=='RELEASE_STATUS.json':
            if case=='publication':data['published']=True
            if case=='relabelled_science':data['scientific_outcomes']['D_LOW_EXPOSURE']='PASS'
        if path.name=='BASELINE_VERIFICATION.json' and case=='baseline_failure':
            data['comparisons'][0]['status']='FAIL'
        if path.name=='SCIENTIFIC_BASELINE.json' and case=='altered_source':
            data['protected_files'][next(iter(data['protected_files']))]='0'*64
        return data
    monkeypatch.setattr(v,'read',changed)
    with pytest.raises(v.PackageError):v.check_release_status(root)
