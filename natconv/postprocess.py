"""결과 필드/메시 파싱 및 그림 생성 (ParaView 불필요, matplotlib)."""
import os
import re

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from .geometry import stl_bounds

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


def _read_stl_tris(path):
    tris, cur = [], []
    for line in open(path):
        s = line.strip()
        if s.startswith("vertex"):
            cur.append([float(x) for x in s.split()[1:4]])
            if len(cur) == 3:
                tris.append(cur)
                cur = []
    return np.array(tris)


def _heater_half(case_dir):
    """히터 형상의 x-y 반경(줌 스케일 산정용)."""
    try:
        lo, hi = stl_bounds(os.path.join(case_dir, "constant/triSurface/heater.stl"))
        return max(abs(hi[0]), abs(lo[0]), abs(hi[1]), abs(lo[1]))
    except Exception:
        return 0.01


def _blockmesh_bounds(case_dir):
    t = open(os.path.join(case_dir, "system/blockMeshDict")).read()

    def g(k):
        return float(re.search(rf"\n{k}\s+(-?[\d.eE+]+);", t).group(1))
    return ((g("xMin"), g("yMin"), g("zMin")), (g("xMax"), g("yMax"), g("zMax")))


# ---------- 그림 ----------
def structure_png(case_dir, out_png):
    """구조 모델: 히터 STL + 인클로저 도메인 박스 (3D)."""
    tris = _read_stl_tris(os.path.join(case_dir, "constant/triSurface/heater.stl"))
    tris_p = tris[:, :, [0, 2, 1]]                 # 세로축=데이터 y(연직) → 원통 수평으로 보임
    fig = plt.figure(figsize=(7, 6))
    ax = fig.add_subplot(111, projection="3d")
    ax.add_collection3d(Poly3DCollection(tris_p, facecolor="#f59e0b", edgecolor="none", alpha=0.95))
    try:
        (xm, ym, zm), (xM, yM, zM) = _blockmesh_bounds(case_dir)
        import itertools
        corners = [(a, c, b) for a in (xm, xM) for c in (zm, zM) for b in (ym, yM)]
        for p, q in itertools.combinations(corners, 2):
            if sum(abs(np.array(p) - np.array(q)) > 1e-9) == 1:
                ax.plot(*zip(p, q), color="#9ca3af", lw=0.7, ls="--")
    except Exception:
        pass
    ax.set_xlabel("x (수평, m)"); ax.set_ylabel("z (축, m)"); ax.set_zlabel("y (연직 ↑, m)")
    ax.set_title("구조 모델: 히터 + 25°C 인클로저")
    ax.set_box_aspect((2, 2, 3)); ax.view_init(elev=16, azim=-72)
    fig.tight_layout(); fig.savefig(out_png, dpi=130); plt.close(fig)
    return out_png


def mesh_slice_png(case_dir, out_png, half=None, z0=0.0, tol=1e-6):
    """z=0 평면 메시 단면 (히터 주변 정밀화 + 프리즘 레이어)."""
    if half is None:
        half = 4.0 * _heater_half(case_dir)
    pts = read_points(os.path.join(case_dir, "constant/polyMesh/points"))
    faces = read_faces(os.path.join(case_dir, "constant/polyMesh/faces"))
    polys = [pts[f][:, :2] for f in faces if np.all(np.abs(pts[f][:, 2] - z0) < tol)]
    fig, ax = plt.subplots(figsize=(6.2, 6.2))
    ax.add_collection(PolyCollection(polys, facecolors="none",
                                     edgecolors="#334155", linewidths=0.35))
    ax.set_xlim(-half, half); ax.set_ylim(-half, half); ax.set_aspect("equal")
    ax.set_xlabel("x (m) → 수평"); ax.set_ylabel("y (m) ↑ 연직")
    ax.set_title("메쉬 구조 (z=0 단면)")
    fig.tight_layout(); fig.savefig(out_png, dpi=140); plt.close(fig)
    return out_png


def _load_CT(case_dir, latest_time, slab=0.004):
    C = np.array(read_vector_field(os.path.join(case_dir, latest_time, "C")))
    T = np.array(read_scalar_field(os.path.join(case_dir, latest_time, "T"))) - 273.15
    sel = np.abs(C[:, 2]) < slab
    return C[sel, 0], C[sel, 1], T[sel]


def _temp_contour(x, y, t, xlim, ylim, title, out_png, figsize=(6.6, 6.6)):
    m = (x >= xlim[0]) & (x <= xlim[1]) & (y >= ylim[0]) & (y <= ylim[1])
    fig, ax = plt.subplots(figsize=figsize)
    cf = ax.tricontourf(x[m], y[m], t[m], levels=np.linspace(t[m].min(), t[m].max(), 30),
                        cmap="inferno")
    ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.set_aspect("equal")
    ax.set_xlabel("x (m)"); ax.set_ylabel("y (m) ↑")
    ax.set_title(title)
    cb = plt.colorbar(cf, ax=ax, shrink=0.85); cb.set_label("온도 (°C)")
    fig.tight_layout(); fig.savefig(out_png, dpi=140); plt.close(fig)
    return out_png


def temperature_crosssection_png(case_dir, latest_time, out_png):
    """히터 원형 단면 온도장 (줌, 상단이 뜨거움)."""
    x, y, t = _load_CT(case_dir, latest_time)
    h = 5.0 * _heater_half(case_dir)
    return _temp_contour(x, y, t, (-h, h), (-h, h),
                         "단면 온도장 — 상단이 가장 뜨거움", out_png)


def temperature_field_png(case_dir, latest_time, out_png):
    """주변 공기 온도장 (전체 도메인, 상승 플룸 + 대기)."""
    x, y, t = _load_CT(case_dir, latest_time)
    return _temp_contour(x, y, t, (x.min(), x.max()), (y.min(), y.max()),
                         "주변 온도 프로파일 — 상승 플룸과 대기", out_png, figsize=(6.0, 7.4))


# 하위호환 별칭
temperature_slice_png = temperature_crosssection_png
