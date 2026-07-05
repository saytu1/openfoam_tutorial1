"""결과 필드/메시 파싱 및 그림 생성 (ParaView 불필요, matplotlib)."""
import os
import re

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import PolyCollection

# 한글 폰트 (macOS)
for _cand in ["/System/Library/Fonts/Supplemental/AppleGothic.ttf",
              "/System/Library/Fonts/AppleSDGothicNeo.ttc"]:
    if os.path.exists(_cand):
        try:
            font_manager.fontManager.addfont(_cand)
            matplotlib.rcParams["font.family"] = font_manager.FontProperties(fname=_cand).get_name()
            break
        except Exception:
            pass
matplotlib.rcParams["axes.unicode_minus"] = False


# ---------- OpenFOAM ASCII 파서 ----------
def read_scalar_field(path):
    txt = open(path).read()
    m = re.search(r"nonuniform List<scalar>\s*\n(\d+)\s*\n\(", txt)
    n = int(m.group(1))
    body = txt[m.end():]
    return [float(x) for x in body[:body.index(")")].split()][:n]


def read_vector_field(path):
    txt = open(path).read()
    m = re.search(r"nonuniform List<vector>\s*\n(\d+)\s*\n\(", txt)
    n = int(m.group(1))
    body = txt[m.end():]
    vals = re.findall(r"\(\s*([-\d.eE+ ]+?)\s*\)", body)
    return [[float(x) for x in v.split()] for v in vals[:n]]


def read_points(path):
    txt = open(path).read()
    m = re.search(r"^\s*(\d+)\s*\n\(", txt, re.M)
    n = int(m.group(1))
    body = txt[m.end():]
    vals = re.findall(r"\(([^)]+)\)", body)
    return np.array([[float(x) for x in v.split()] for v in vals[:n]])


def read_faces(path):
    txt = open(path).read()
    m = re.search(r"^\s*(\d+)\s*\n\(", txt, re.M)
    n = int(m.group(1))
    body = txt[m.end():]
    faces = []
    for fm in re.finditer(r"(\d+)\(([^)]+)\)", body):
        faces.append([int(i) for i in fm.group(2).split()])
        if len(faces) >= n:
            break
    return faces


# ---------- 그림 ----------
def mesh_slice_png(case_dir, out_png, half=0.02, z0=0.0, tol=1e-6):
    """z=0 평면 위의 메시 face를 그려 단면 메시(정밀화+레이어)를 보여준다."""
    pts = read_points(os.path.join(case_dir, "constant/polyMesh/points"))
    faces = read_faces(os.path.join(case_dir, "constant/polyMesh/faces"))
    polys = [pts[f][:, :2] for f in faces if np.all(np.abs(pts[f][:, 2] - z0) < tol)]
    fig, ax = plt.subplots(figsize=(6.2, 6.2))
    ax.add_collection(PolyCollection(polys, facecolors="none",
                                     edgecolors="#334155", linewidths=0.35))
    ax.set_xlim(-half, half); ax.set_ylim(-half, half); ax.set_aspect("equal")
    ax.set_xlabel("x (m) → 수평"); ax.set_ylabel("y (m) ↑ 연직")
    ax.set_title("단면 메시 (z=0) — 형상 주변 정밀화 + 프리즘 레이어")
    fig.tight_layout(); fig.savefig(out_png, dpi=140); plt.close(fig)
    return out_png


def temperature_slice_png(case_dir, latest_time, out_png,
                          xlim=(-0.03, 0.03), ylim=(-0.03, 0.03), slab=0.004):
    """셀중심 C + 온도 T (z≈0 슬랩)로 단면 온도장(상단이 뜨거움)을 그린다.
    사전에 writeCellCentres 로 {time}/C 가 있어야 한다."""
    C = np.array(read_vector_field(os.path.join(case_dir, latest_time, "C")))
    T = np.array(read_scalar_field(os.path.join(case_dir, latest_time, "T"))) - 273.15
    sel = np.abs(C[:, 2]) < slab
    x, y, t = C[sel, 0], C[sel, 1], T[sel]
    m = (x >= xlim[0]) & (x <= xlim[1]) & (y >= ylim[0]) & (y <= ylim[1])
    fig, ax = plt.subplots(figsize=(6.6, 6.6))
    cf = ax.tricontourf(x[m], y[m], t[m], levels=np.linspace(t.min(), t.max(), 30),
                        cmap="inferno")
    ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.set_aspect("equal")
    ax.set_xlabel("x (m)"); ax.set_ylabel("y (m) ↑")
    ax.set_title("단면 온도장 — 상단이 가장 뜨거움")
    cb = plt.colorbar(cf, ax=ax, shrink=0.85); cb.set_label("온도 (°C)")
    fig.tight_layout(); fig.savefig(out_png, dpi=140); plt.close(fig)
    return out_png
