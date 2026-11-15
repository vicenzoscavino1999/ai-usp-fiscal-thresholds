from pathlib import Path
import sys,shutil
B=Path(__file__).resolve().parent;R=B/'revision_jpm_v2';T=R/'paso_07d/costos_transicion_03';I=R/'paso_07e/evidencia/scripts/inputs'
for name in ['FRONTERAS_ANUALES_480.csv','INVERSAS_RECALCULADAS.csv','HORIZONTES_RECALCULADOS.csv','FRONTERAS_TRANSICION.csv']:shutil.copy2(T/'resultados'/name,I/name)
shutil.copy2(T/'evidencia/CONTEXTOS_80.json',R/'paso_07g/evidencia/CONTEXTOS_80.json')
print('Fresh results transferred to document comparators and revised diagnostics.')
