# Phase 2A — 히터 + 증발기 형상·메시 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 냉장고 증발기(직관 12개 + 두께0 baffle 핀)와 U자 hairpin 히터를 별개 구조체로 생성하고, snappyHexMesh로 checkMesh를 통과하는 케이스 메시를 만든다. + GUI 증발기 입력·시각화.

**Architecture:** 순수 Python 코어(geometry/params, pytest)로 3개 STL(tubes/fins/heater) 생성 → case_builder가 배경메시 + snappy(튜브·히터 wall, 핀 baffle) → GUI 증발기 탭. 히터와 증발기는 완전 분리된 solid/patch.

**Tech Stack:** Python 3.9+, numpy, OpenFOAM v2606(`openfoam -c`), streamlit, pytest.

## Global Constraints

- 좌표: **x=폭(튜브·히터 축)**, **y=높이(연직, 중력 −y)**, **z=깊이**. 원점=튜브 다발 중심.
- 증발기: Ø8 직관 12개(2열 z=±15 × 6단 y 피치30), U밴드 없음, x축 600mm.
- 핀: 각 단 중심에 30(y)×60(z), x방향 8mm 간격, 두께 0 baffle. 증발기에만.
- 히터: Ø6.5, 2열(z=±15) + 오른쪽(+x) U밴드 = hairpin, 다리 600×2 + U밴드(R15), **총길이 ≈1247mm**. 증발기 최하단서 30mm 아래. 증발기와 절대 미연결.
- 코어는 SI(m) 사용. GUI만 mm 입력(÷1000). 작업 디렉토리 `/Users/wooya/claude/openfoam/natconv-studio`.
- 커밋 메시지 한국어. 각 태스크 끝 커밋. 기존 34 테스트 깨지지 않게.

---

### Task 1: Evaporator 파라미터 데이터클래스

**Files:**
- Modify: `natconv/params.py`
- Test: `tests/test_evaporator_params.py`

**Interfaces:**
- Produces: `Evaporator` 데이터클래스(필드는 Step3), `Evaporator.validate() -> list[str]`.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_evaporator_params.py`:
```python
from natconv.params import Evaporator


def test_default_valid():
    assert Evaporator().validate() == []


def test_tube_count():
    e = Evaporator()
    assert e.n_rows * e.n_cols == 12


def test_bad_counts_reported():
    e = Evaporator(n_rows=0)
    assert any("n_rows" in m for m in e.validate())


def test_fin_thinner_than_pitch():
    e = Evaporator(fin_thickness=0.02, fin_pitch_x=0.008)   # m
    assert e.validate() == []
    e2 = Evaporator(fin_thickness=0.02, fin_pitch_x=0.01)
    e2.fin_pitch_x = 0.01; e2.fin_thickness = 0.02
    assert any("fin" in m for m in e2.validate())
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_evaporator_params.py -q`
Expected: FAIL (ImportError: Evaporator)

- [ ] **Step 3: 구현** — `natconv/params.py` 상단 `from dataclasses import dataclass` 아래에 추가:

```python
@dataclass
class Evaporator:
    # 튜브 (SI 단위 m)
    D_t: float = 0.008
    n_rows: int = 6            # 단 (y)
    n_cols: int = 2            # 열 (z)
    pitch_y: float = 0.030     # 단 피치
    pitch_z: float = 0.030     # 열 피치
    tube_len: float = 0.600    # x축 길이
    # 핀
    fin_h: float = 0.030       # 높이 y
    fin_z: float = 0.060       # 깊이 z (두 열 모두 덮음)
    fin_pitch_x: float = 0.008
    fin_thickness: float = 0.00015
    # 히터 (2열 U자 hairpin)
    heater_gap: float = 0.030          # 최하단 튜브에서 히터까지
    heater_leg_len: float = 0.600
    heater_col_pitch: float = 0.030    # 2열 간격

    def validate(self):
        e = []
        if self.n_rows < 1 or self.n_cols < 1:
            e.append(f"n_rows/n_cols must be >=1: {self.n_rows},{self.n_cols}")
        for name in ("D_t", "pitch_y", "pitch_z", "tube_len", "fin_h", "fin_z",
                     "fin_pitch_x", "heater_leg_len"):
            if getattr(self, name) <= 0:
                e.append(f"{name} must be > 0")
        if self.fin_thickness >= self.fin_pitch_x:
            e.append("fin_thickness must be < fin_pitch_x")
        return e
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_evaporator_params.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add natconv/params.py tests/test_evaporator_params.py
git commit -m "params: Evaporator 데이터클래스와 검증"
```

---

### Task 2: 튜브 다발 STL (x축 직관 12개)

**Files:**
- Modify: `natconv/geometry.py`
- Test: `tests/test_evaporator_geometry.py`

**Interfaces:**
- Consumes: 없음.
- Produces: `_cyl_x(f, x0, x1, yc, zc, r, n=40)`(열린 파일에 x축 원통 facet 기록);
  `rows_y(n_rows, pitch)->list`, `cols_z(n_cols, pitch)->list`(중심 정렬 좌표);
  `write_tube_bank_stl(path, D_t, ys, zs, x0, x1)`(solid=tubes).

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_evaporator_geometry.py`:
```python
import math
from natconv.geometry import (write_tube_bank_stl, stl_area, rows_y, cols_z)


def test_row_col_centers():
    assert rows_y(6, 0.03) == [-0.075, -0.045, -0.015, 0.015, 0.045, 0.075]
    assert cols_z(2, 0.03) == [-0.015, 0.015]


def test_tube_bank_area(tmp_path):
    p = str(tmp_path / "tubes.stl")
    ys = rows_y(6, 0.03); zs = cols_z(2, 0.03)
    write_tube_bank_stl(p, 0.008, ys, zs, -0.3, 0.3)
    lateral = 12 * math.pi * 0.008 * 0.6
    caps = 12 * 2 * math.pi * 0.004**2
    assert abs(stl_area(p) - (lateral + caps)) / (lateral + caps) < 0.03
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_evaporator_geometry.py -q`
Expected: FAIL (ImportError: rows_y)

- [ ] **Step 3: 구현** — `natconv/geometry.py` 끝에 추가 (`_facet`, `stl_area`는 기존 재사용):

```python
def rows_y(n, pitch):
    return [-pitch * (n - 1) / 2 + pitch * i for i in range(n)]


def cols_z(n, pitch):
    return [-pitch * (n - 1) / 2 + pitch * j for j in range(n)]


def _cyl_x(f, x0, x1, yc, zc, r, n=40):
    """x축 원통(중심 yc,zc)을 열린 STL 파일 f에 기록 (측면+양끝 캡)."""
    pts = [(yc + r * math.cos(2 * math.pi * i / n), zc + r * math.sin(2 * math.pi * i / n))
           for i in range(n)]
    for i in range(n):
        y0, z0 = pts[i]
        y1, z1 = pts[(i + 1) % n]
        _facet(f, (x0, y0, z0), (x1, y1, z1), (x1, y0, z0))
        _facet(f, (x0, y0, z0), (x0, y1, z1), (x1, y1, z1))
        _facet(f, (x0, yc, zc), (x0, y1, z1), (x0, y0, z0))
        _facet(f, (x1, yc, zc), (x1, y0, z0), (x1, y1, z1))


def write_tube_bank_stl(path, D_t, ys, zs, x0, x1):
    with open(path, "w") as f:
        f.write("solid tubes\n")
        for yc in ys:
            for zc in zs:
                _cyl_x(f, x0, x1, yc, zc, D_t / 2)
        f.write("endsolid tubes\n")
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_evaporator_geometry.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add natconv/geometry.py tests/test_evaporator_geometry.py
git commit -m "geometry: x축 튜브 다발 STL (2열x6단)"
```

---

### Task 3: 핀 STL (각 단 30×60, 두께0)

**Files:**
- Modify: `natconv/geometry.py`
- Test: `tests/test_evaporator_geometry.py` (append)

**Interfaces:**
- Consumes: `_facet`, `rows_y`.
- Produces: `write_fins_stl(path, ys, fin_h, fin_z, pitch_x, x0, x1)`(solid=fins);
  `n_fins(x0, x1, pitch) -> int`.

- [ ] **Step 1: 실패 테스트 작성** (append to `tests/test_evaporator_geometry.py`)

```python
from natconv.geometry import write_fins_stl, n_fins, stl_bounds


def test_fin_count():
    assert n_fins(-0.3, 0.3, 0.008) == 76   # 600/8 + 1


def test_fins_area(tmp_path):
    p = str(tmp_path / "fins.stl")
    ys = rows_y(6, 0.03)
    write_fins_stl(p, ys, 0.030, 0.060, 0.008, -0.3, 0.3)
    # 각 x위치마다 6단 × (30×60) 사각형, 76개 x위치
    expected = 76 * 6 * (0.030 * 0.060)
    assert abs(stl_area(p) - expected) / expected < 0.01


def test_fins_span_depth(tmp_path):
    p = str(tmp_path / "fins.stl")
    write_fins_stl(p, rows_y(6, 0.03), 0.030, 0.060, 0.008, -0.3, 0.3)
    lo, hi = stl_bounds(p)
    assert abs(hi[2] - 0.030) < 1e-9 and abs(lo[2] + 0.030) < 1e-9  # z ±30mm
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_evaporator_geometry.py -q`
Expected: FAIL (ImportError: write_fins_stl)

- [ ] **Step 3: 구현** — `natconv/geometry.py` 끝에 추가:

```python
def n_fins(x0, x1, pitch):
    return int(round((x1 - x0) / pitch)) + 1


def write_fins_stl(path, ys, fin_h, fin_z, pitch_x, x0, x1):
    """각 단(y) 중심에 fin_h(y)×fin_z(z) 사각 핀을 x방향 pitch_x 간격으로. 두께 0."""
    hz = fin_z / 2.0
    xs = [x0 + pitch_x * k for k in range(n_fins(x0, x1, pitch_x))]
    with open(path, "w") as f:
        f.write("solid fins\n")
        for xf in xs:
            for yc in ys:
                y0, y1 = yc - fin_h / 2, yc + fin_h / 2
                a = (xf, y0, -hz); b = (xf, y1, -hz)
                c = (xf, y1, hz); d = (xf, y0, hz)
                _facet(f, a, b, c)
                _facet(f, a, c, d)
        f.write("endsolid fins\n")
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_evaporator_geometry.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add natconv/geometry.py tests/test_evaporator_geometry.py
git commit -m "geometry: 각 단 30x60 핀 STL (두께0)"
```

---

### Task 4: 히터 U자 hairpin STL (2열 + U밴드)

**Files:**
- Modify: `natconv/geometry.py`
- Test: `tests/test_evaporator_geometry.py` (append)

**Interfaces:**
- Consumes: `_facet`, `_cyl_x`.
- Produces: `write_heater_hairpin_stl(path, D_h, x0, x1, z_pitch, yc)`(solid=heater);
  `heater_total_length(x0, x1, z_pitch) -> float`.

- [ ] **Step 1: 실패 테스트 작성** (append)

```python
import math
from natconv.geometry import write_heater_hairpin_stl, heater_total_length, stl_area


def test_heater_length():
    L = heater_total_length(-0.3, 0.3, 0.030)   # 다리 0.6*2 + πR, R=0.015
    assert abs(L - (2 * 0.6 + math.pi * 0.015)) < 1e-9
    assert abs(L - 1.24712) < 1e-3               # ≈1247mm


def test_heater_area(tmp_path):
    p = str(tmp_path / "heater.stl")
    write_heater_hairpin_stl(p, 0.0065, -0.3, 0.3, 0.030, -0.11225)
    L = heater_total_length(-0.3, 0.3, 0.030)
    lateral = math.pi * 0.0065 * L
    assert abs(stl_area(p) - lateral) / lateral < 0.10   # 캡 없음(U로 이어짐) 대략
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_evaporator_geometry.py -q`
Expected: FAIL (ImportError)

- [ ] **Step 3: 구현** — `natconv/geometry.py` 끝에 추가:

```python
def heater_total_length(x0, x1, z_pitch):
    R = z_pitch / 2.0
    return 2.0 * (x1 - x0) + math.pi * R


def _ubend_x(f, xc, yc, R, r, n=40, m=24):
    """x-z 평면 반원(중심 xc,yc, 반경 R, z=-R→+R, +x로 볼록) 중심선을 따라 반경 r 튜브 스윕."""
    phis = [(-math.pi / 2) + math.pi * k / m for k in range(m + 1)]
    rings = []
    for phi in phis:
        cx, cz = xc + R * math.cos(phi), R * math.sin(phi)
        u = (math.cos(phi), 0.0, math.sin(phi))   # 접선에 수직(면내)
        ring = []
        for i in range(n):
            th = 2 * math.pi * i / n
            ring.append((cx + r * math.cos(th) * u[0],
                         yc + r * math.sin(th),
                         cz + r * math.cos(th) * u[2]))
        rings.append(ring)
    for k in range(m):
        for i in range(n):
            a = rings[k][i]; b = rings[k][(i + 1) % n]
            c = rings[k + 1][(i + 1) % n]; d = rings[k + 1][i]
            _facet(f, a, b, c)
            _facet(f, a, c, d)


def write_heater_hairpin_stl(path, D_h, x0, x1, z_pitch, yc):
    """2열(z=±z_pitch/2) 직관 다리 + 오른쪽(x1) U밴드로 이은 hairpin."""
    r = D_h / 2.0
    zc = z_pitch / 2.0
    with open(path, "w") as f:
        f.write("solid heater\n")
        _cyl_x(f, x0, x1, yc, -zc, r)     # 다리 1
        _cyl_x(f, x0, x1, yc, +zc, r)     # 다리 2
        _ubend_x(f, x1, yc, zc, r)        # 오른쪽 U밴드(z=-zc→+zc)
        f.write("endsolid heater\n")
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_evaporator_geometry.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add natconv/geometry.py tests/test_evaporator_geometry.py
git commit -m "geometry: 히터 U자 hairpin STL (2열+U밴드, 총길이 1247mm)"
```

---

### Task 5: case_builder — Phase 2A 케이스(3 STL + snappy baffle)

**Files:**
- Create: `natconv/evaporator_case.py`
- Modify: `natconv/templates/snappyHexMeshDict_evap.tmpl` (Create)
- Test: `tests/test_evaporator_case.py`

**Interfaces:**
- Consumes: `Evaporator`(T1), `write_tube_bank_stl`/`write_fins_stl`/`write_heater_hairpin_stl`(T2-4),
  `rows_y`/`cols_z`/`heater_total_length`.
- Produces: `build_evaporator_geometry(evap, out_dir) -> dict`(생성된 STL 경로·좌표 반환);
  `build_phase2a_case(evap, env, out_dir) -> str`(blockMesh+snappy dict 포함 케이스 폴더).

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_evaporator_case.py`:
```python
import os, math
from natconv.params import Evaporator
from natconv.evaporator_case import build_evaporator_geometry
from natconv.geometry import stl_area


def test_geometry_writes_three_stls(tmp_path):
    info = build_evaporator_geometry(Evaporator(), str(tmp_path / "c"))
    base = str(tmp_path / "c" / "constant" / "triSurface")
    for name in ("tubes.stl", "fins.stl", "heater.stl"):
        assert os.path.exists(os.path.join(base, name)), name


def test_heater_below_tubes(tmp_path):
    info = build_evaporator_geometry(Evaporator(), str(tmp_path / "c"))
    # 히터 y중심이 최하단 튜브(-0.075)보다 아래
    assert info["heater_yc"] < -0.075


def test_heater_length_in_info(tmp_path):
    info = build_evaporator_geometry(Evaporator(), str(tmp_path / "c"))
    assert abs(info["heater_length"] - 1.24712) < 1e-3
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_evaporator_case.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 구현** — `natconv/evaporator_case.py`:

```python
import os
from .geometry import (rows_y, cols_z, write_tube_bank_stl, write_fins_stl,
                       write_heater_hairpin_stl, heater_total_length)


def build_evaporator_geometry(evap, out_dir):
    """3개 STL(tubes/fins/heater)을 out_dir/constant/triSurface 에 생성. 좌표 정보 반환."""
    tri = os.path.join(out_dir, "constant", "triSurface")
    os.makedirs(tri, exist_ok=True)
    ys = rows_y(evap.n_rows, evap.pitch_y)
    zs = cols_z(evap.n_cols, evap.pitch_z)
    x0, x1 = -evap.tube_len / 2, evap.tube_len / 2
    heater_yc = min(ys) - evap.D_t / 2 - evap.heater_gap - 0.0065 / 2

    write_tube_bank_stl(os.path.join(tri, "tubes.stl"), evap.D_t, ys, zs, x0, x1)
    write_fins_stl(os.path.join(tri, "fins.stl"), ys, evap.fin_h, evap.fin_z,
                   evap.fin_pitch_x, x0, x1)
    hx0, hx1 = -evap.heater_leg_len / 2, evap.heater_leg_len / 2
    write_heater_hairpin_stl(os.path.join(tri, "heater.stl"), 0.0065, hx0, hx1,
                             evap.heater_col_pitch, heater_yc)
    return {"ys": ys, "zs": zs, "x0": x0, "x1": x1, "heater_yc": heater_yc,
            "heater_length": heater_total_length(hx0, hx1, evap.heater_col_pitch)}
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_evaporator_case.py -q`
Expected: 3 passed

- [ ] **Step 5: snappy baffle 템플릿 작성** — `natconv/templates/snappyHexMeshDict_evap.tmpl`:
  `$FOAM_TUTORIALS/heatTransfer/buoyantSimpleFoam/circuitBoardCooling/system/snappyHexMeshDict`
  를 참조해, `geometry`에 tubes/fins/heater triSurfaceMesh 3개, `refinementSurfaces`에
  tubes·heater는 `{ level (2 3); patchInfo{ type wall; } }`, **fins는
  `{ level (2 2); faceZone finsZone; faceType baffle; cellZone none; }`** 로 baffle 지정.
  `castellatedMeshControls.features`·`meshQualityControls`(errorReduction 포함)는 Phase1 템플릿과 동일.
  토큰 `__LOC_IN_MESH__` 등은 case 빌드 시 치환.

- [ ] **Step 6: Commit**

```bash
git add natconv/evaporator_case.py natconv/templates/snappyHexMeshDict_evap.tmpl tests/test_evaporator_case.py
git commit -m "evaporator_case: 3 STL 생성 + snappy baffle 핀 템플릿"
```

---

### Task 6: GUI 증발기 입력 탭 + 다중 STL 시각화

**Files:**
- Modify: `app/streamlit_app.py`, `natconv/postprocess.py`
- (단위테스트 없음 — AppTest 스모크 + 수동)

**Interfaces:**
- Consumes: `Evaporator`, `build_evaporator_geometry`, 기존 시각화 탭.
- Produces: 사이드바 "🧊 증발기" 섹션(Evaporator mm 입력 + "증발기 포함" 체크박스);
  `postprocess.structure_multi_png(case_dir, out_png)`(tubes/fins/heater STL 함께 렌더).

- [ ] **Step 1: postprocess 다중 STL 렌더 추가** — `natconv/postprocess.py`에 `structure_multi_png`:
  `constant/triSurface`의 `tubes.stl`(회색)·`fins.stl`(연파랑)·`heater.stl`(주황)을 각각
  `_read_stri_tris`로 읽어 하나의 3D(연직 y 매핑 `[0,2,1]`)로 그린다. 파일 없으면 건너뜀.

- [ ] **Step 2: GUI 증발기 섹션** — 사이드바에 체크박스 `증발기 포함` + Evaporator 필드(mm,
  tooltip). 체크 시 `build_evaporator_geometry`로 STL 생성 후 시각화 탭이 `structure_multi_png` 사용.
  (2A는 형상·메시까지 — 솔버 실행 버튼은 그대로 두되 결합 해석은 2B에서.)

- [ ] **Step 3: AppTest 스모크**

Run: `.venv/bin/python -c "from streamlit.testing.v1 import AppTest; at=AppTest.from_file('app/streamlit_app.py',default_timeout=60).run(); assert not at.exception, at.exception; print('OK')"`
Expected: OK (예외 없음)

- [ ] **Step 4: Commit**

```bash
git add app/streamlit_app.py natconv/postprocess.py
git commit -m "app: 증발기 입력 탭 + 다중 STL(튜브/핀/히터) 시각화"
```

---

### Task 7: 통합 검증 — 실제 메시 생성

**Files:** (코드 변경 없음, 검증)

- [ ] **Step 1: Phase 2A 케이스 빌드 & 메시**

Python으로 `build_evaporator_geometry(Evaporator(), 'cases/p2a')` → 3 STL 생성.
그다음 blockMesh(배경 박스: 증발기+히터 바운딩박스 × enclosure_factor) →
surfaceFeatureExtract → snappyHexMesh(snappyHexMeshDict_evap 기반) → createBaffles(fins) → checkMesh.
(배경 박스·loc-in-mesh 치환은 Task 5 case 빌드 로직에 포함하거나 수동 dict로.)

- [ ] **Step 2: 검증**

Run: `openfoam -c 'cd cases/p2a && checkMesh' 2>&1 | grep -iE "patches|Mesh OK|Failed"`
Expected: `tubes`·`fins`(baffle)·`heater` patch 존재, checkMesh 심각한 실패 없음.
튜브 patch 면적 ≈ 12·πD·0.6 (±5%), 히터 patch 존재.

- [ ] **Step 3: 전체 테스트 통과**

Run: `.venv/bin/pytest -q`
Expected: 전체 통과 (기존 34 + 신규).

- [ ] **Step 4: REQUIREMENTS·README 갱신 & Commit**

`REQUIREMENTS.md`에 Phase 2A 진척(형상·메시) 반영.
```bash
git add REQUIREMENTS.md
git commit -m "통합 검증: Phase 2A 메시 생성(튜브·핀baffle·히터 patch) 및 문서"
```

---

## Self-Review

**Spec coverage:**
- 증발기 12직관(T2) ✓ · 30×60 핀 baffle(T3, T5 baffle) ✓ · 히터 hairpin 1247mm(T4) ✓
- 히터/증발기 분리(T4·T5 별도 solid/patch) ✓ · Evaporator params(T1) ✓
- 메시 snappy baffle(T5) ✓ · GUI 증발기 탭·시각화(T6) ✓ · checkMesh 통합(T7) ✓
- 성공기준 1~6 → T7(checkMesh·patch·면적), T2-4(개수·면적·길이) 매핑 ✓

**Placeholder scan:** T5 snappy 템플릿·T6 GUI·T7 배경박스는 뼈대+참조 튜토리얼 지정(구현자가
조립). 그 외 T1-4는 실제 코드·테스트 완비. OpenFOAM dict 세부는 설치 튜토리얼을 접지진실로.

**Type consistency:** `rows_y`/`cols_z`(T2) ↔ `build_evaporator_geometry`(T5) 사용 일치.
`heater_total_length`(T4) ↔ info["heater_length"](T5) 일치. `Evaporator` 필드(T1) ↔ T5 접근 일치.
`_cyl_x`(T2) ↔ 히터 다리(T4) 재사용 일치.

**Gap:** 배경 박스·loc-in-mesh 자동화는 T5/T7에 걸쳐 있음 — T7 Step1에서 명시적으로 처리하도록 표기함.
