import csv, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch, Rectangle

SRC = "reports/paper_tables/table4_vgross_baseline.csv"
OUTBASE = sys.argv[1] if len(sys.argv) > 1 else "figures/headline_feasibility"
rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
def val(c,p,s,r="r0"):
    for x in rows:
        if x["country_id"]==c and x["policy_variant_id"]==p and x["scenario_id"]==s and x["regime_id"]==r:
            return float(x["v_gross"])
    return np.nan
countries=[("CHL","Chile"),("PER","Peru"),("COL","Colombia"),("MEX","Mexico")]
policies=[("GMI:GMI_ideal_aggregate","GMI (ideal targeting)"),
          ("GMI:GMI_loaded_aggregate","GMI (loaded targeting)"),
          ("PEN","Universal social pension"),("MUT","Minimum universal transfer"),
          ("PBI","Partial basic income"),("UBI","Full UBI benchmark")]
scenarios=[("low","Conservative"),("mid","Moderate"),("high","High frontier\ninput"),("stress","Disruptive\nstress")]
bounds=[-1e3, 0, 0.5, 1.0, 1.10, 1e3]
colors=["#08306b","#3573b9","#a6cee3","#fdd0a2","#cb181d"]
cmap=ListedColormap(colors); norm=BoundaryNorm(bounds,cmap.N)
labels=[r"$V<0$ (negative effective fiscal space)",r"$0\leq V<0.5$",r"$0.5\leq V<1$",
        r"$1\leq V<1.10$ (marginal crossing)",r"$V\geq1.10$ (crosses with 10% buffer)"]
fig,axes=plt.subplots(2,2,figsize=(11.4,8.4))
def fmt(v): return f"{0.0 if abs(v)<0.005 else v:.2f}"
for idx,(cc,cn) in enumerate(countries):
    ax=axes[idx//2][idx%2]
    M=np.array([[val(cc,pc,sc) for sc,_ in scenarios] for pc,_ in policies])
    ax.imshow(M,aspect="auto",cmap=cmap,norm=norm)
    ax.set_title(cn,fontsize=12,fontweight="bold",pad=4)
    ax.set_xticks(range(4)); ax.set_yticks(range(6))
    ax.set_xticklabels([s[1] for s in scenarios],fontsize=8) if idx>=2 else ax.set_xticklabels([])
    ax.set_yticklabels([p[1] for p in policies],fontsize=8.5) if idx%2==0 else ax.set_yticklabels([])
    ax.tick_params(length=0)
    for i in range(6):
        for j in range(4):
            v=M[i,j]; cross=v>=1.0; b=np.digitize(v,bounds)-1
            ax.text(j,i,fmt(v),ha="center",va="center",fontsize=7.4,
                    color="white" if b in (0,4) else "black",
                    fontweight="bold" if cross else "normal")
            if cross: ax.add_patch(Rectangle((j-0.5,i-0.5),1,1,fill=False,edgecolor="black",lw=2.0))
handles=[Patch(facecolor=colors[k],edgecolor="0.4",label=labels[k]) for k in range(5)]
handles.append(Patch(facecolor="white",edgecolor="black",lw=2.0,label=r"Black outline: structural crossing ($V\geq1$)"))
fig.legend(handles=handles,loc="lower center",ncol=3,fontsize=8.5,frameon=False,bbox_to_anchor=(0.5,-0.01))
plt.tight_layout(rect=[0,0.07,1,1])
for ext in ("pdf","png"):
    fig.savefig(f"{OUTBASE}.{ext}",dpi=200,bbox_inches="tight")
    print("saved", f"{OUTBASE}.{ext}")
