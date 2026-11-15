"""Document cell checks used by the final verifier, independent of old PASS logs."""
import csv,json,zipfile,xml.etree.ElementTree as ET
import pandas as pd
from verify_results import require,json_load

NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}

def tables(path):
    with zipfile.ZipFile(path) as z:root=ET.fromstring(z.read('word/document.xml'))
    tabs=[[[''.join(t.text or '' for t in cell.findall('.//w:t',NS)) for cell in row.findall('w:tc',NS)] for row in table.findall('w:tr',NS)] for table in root.findall('w:body/w:tbl',NS)]
    return tabs,len(root.findall('.//m:oMath',NS))

def check_documents(root):
    r=root/'revision_jpm_v2';p=r/'paso_07l/evidencia'
    mt,me=tables(p/'MANUSCRITO_JPM_V2.docx');st,se=tables(p/'SUPLEMENTO_TECNICO_JPM_V2.docx')
    require(me==17 and se==8,'DOCUMENT_EQUATIONS','Unexpected equation count')
    frozen=json_load(root/'verification/document_cells.json')
    require(len(frozen['cells'])==144,'DOCUMENT_CONTRACT','Missing frozen document-cell mappings')
    checked=[];seen=set()
    for cell in frozen['cells']:
        table=cell['table'];row=cell['row'];col=cell['column'];key=(table,row,col)
        require(key not in seen,'DOCUMENT_CONTRACT','Duplicate document-cell mapping');seen.add(key)
        table_group=st if table.startswith('S') else mt;index=int(table.lstrip('S'))-1
        actual=table_group[index][row][col]
        require(actual==cell['expected'],'DOCUMENT_VALUE','Document cell differs from frozen verified value',table=table,row=row,column=col,actual=actual,expected=cell['expected'])
        checked.append({**cell,'actual':actual,'basis':'frozen_verified_reference'})
    # Use the regenerated value table that is also checked against reference_inputs.
    values=pd.read_parquet(r/'paso_07d/evidencia/insumos/values.parquet')
    def val(name,c,field='baseline_value'):
        z=values[values.name.eq(name)&values.country_id.eq(c)]
        require(len(z)==1,'DOCUMENT_PARAMETER','Parameter must have one applicable row',name=name,country=c)
        v=z.iloc[0][field];require(pd.notna(v),'DOCUMENT_PARAMETER','Missing document parameter',name=name,country=c)
        return float(v)
    extra=[]
    for row,country in enumerate(['CHL','PER','COL','MEX'],1):
        for col,param in [(1,'LS_labor_share'),(2,'RST')]:
            expected=f'{val(param,country):.6f}';actual=st[0][row][col]
            require(actual==expected,'DOCUMENT_PARAMETER','S1 parameter differs',table='S1',row=row,column=col)
            extra.append({'table':'S1','row':row,'column':col,'expected':expected,'actual':actual,'basis':'regenerated_registry'})
    for row,param in enumerate(['E_auto','E_aug','delta_s','psi_s','zeta_s','lambda_LS'],1):
        for country in ['CHL','PER','COL','MEX']:
            central=f'{val(param,country):.3f}';support=f'{val(param,country,"low_value"):.3f}–{val(param,country,"high_value"):.3f}'
            require(st[1][row][1]==central and st[1][row][2]==support,'DOCUMENT_PARAMETER','S2 parameter differs',table='S2',row=row,country=country)
        extra.extend([{'table':'S2','row':row,'column':1,'expected':central,'actual':st[1][row][1],'basis':'regenerated_registry'},{'table':'S2','row':row,'column':2,'expected':support,'actual':st[1][row][2],'basis':'regenerated_registry'}])
    require(len(extra)==20,'DOCUMENT_CONTRACT','Incorrect supplemental cell count')
    return {'status':'PASS','cells_verified':164,'frozen_reference_cells':144,'regenerated_parameter_cells':20,'main_equations_OMML':me,'supplement_equations_OMML':se,'cells':checked+extra,'scope':'144 document cells checked directly against frozen values from the verified Docker run, with the 77 scientific artifacts verified separately. Twenty parameter cells are calculated from the regenerated registry. The pipeline also retains its original 144 scientific document checks.'}
