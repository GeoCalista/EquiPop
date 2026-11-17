"""cookbook_14 - one town on foot and by car (Book ch. 9 and 13).

Gridby's network codes every road, the railway, the river and each
crossing twice: a friction for walkers and one for drivers. The same
motorway that fences the east end off on foot is the fastest way in by
car, and job access shows it.
"""
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from equipop.datasets import load
from equipop.decay import Decay
from equipop.fca import fca

g = load("gridby")
net = g["network"]
dec = Decay(model="negexp", half_life_m=10)     # read in ROUNDS
flat = np.zeros(60 * 40)                        # no hill in this lesson
acc = {}
for mode in ("walk", "drive"):
    d, _ = fca(g["workers"], g["workplaces"], "Working_sum", "Jobs",
               decay=dec, reach="effort", altitude=flat,
               fr=g[f"friction_{mode}"])
    acc[mode] = d

STYLE = {  # kind -> (colour, width, dash)
    "river": ("#4a7fb0", 3.0, "-"), "motorway": ("#333333", 3.0, "-"),
    "railway": ("#333333", 1.6, (0, (3, 2))),
    "main road": ("#9a9a9a", 1.6, "-"), "link road": ("#9a9a9a", 2.2, "-"),
}
MARK = {"footbridge": ("walkers only", "o"), "rail footbridge": ("walkers only", "o"),
        "underpass": ("walkers only", "o"), "link bridge": ("drivers only", "s"),
        "road bridge": ("both", "D"), "junction": ("both", "D"),
        "level crossing": ("both", "D")}

fig, ax = plt.subplots(1, 3, figsize=(15, 3.9))
for r in net.itertuples():
    if r.kind in STYLE:
        c, lw, ls = STYLE[r.kind]
        ax[0].plot([r.x0 / 1000, r.x1 / 1000], [r.y0 / 1000, r.y1 / 1000],
                   color=c, lw=lw, ls=ls, solid_capstyle="butt")
seen = set()
for r in net.itertuples():
    if r.kind in MARK:
        lab, m = MARK[r.kind]
        ax[0].scatter((r.x0 + r.x1) / 2000, (r.y0 + r.y1) / 2000, marker=m,
                      s=46, facecolor="white", edgecolor="black", zorder=3,
                      label=None if lab in seen else f"crossing: {lab}")
        seen.add(lab)
ax[0].set_title("the network: river, railway, motorway, roads", fontsize=10)
ax[0].legend(loc="lower right", fontsize=7, frameon=False)
vmax = max(acc["walk"].A.max(), acc["drive"].A.max())


for a, mode, title in ((ax[1], "walk", "job access on foot (A)"),
                       (ax[2], "drive", "job access by car (A)")):
    d = acc[mode]
    s = a.scatter(d.x / 1000, d.y / 1000, c=d.A, s=5, cmap="cividis",
                  vmin=0, vmax=vmax)
    a.set_title(title, fontsize=10)
    plt.colorbar(s, ax=a, shrink=.85)
for a in ax:
    a.set_xlim(0, 6); a.set_ylim(0, 4)
    a.set_aspect("equal"); a.set_xlabel("km")
    a.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig("docs/book/figs/ch09_walk_drive.png", dpi=140)
for mode, d in acc.items():
    print(f"{mode:5s}: mean A west of the river {d[d.x < 3000].A.mean():.3f}, "
          f"east of the motorway {d[d.x > 4600].A.mean():.3f}")
print("ch09 walk/drive figure saved")
