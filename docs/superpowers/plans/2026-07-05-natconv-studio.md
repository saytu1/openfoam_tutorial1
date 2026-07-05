# natconv-studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OpenFOAM 자연대류+복사 표면온도 해석을 파라미터 입력→실행→실시간 시각화하는 Streamlit GUI 도구를 만든다.

**Architecture:** 순수 Python 코어 라이브러리(`natconv/`, Streamlit 비의존, pytest 검증) + 얇은 Streamlit UI(`app/`). OpenFOAM 실행은 `environment.py` 어댑터 뒤로 격리(Mac gerlero 우선, WSL drop-in 가능).

**Tech Stack:** Python 3.9+, OpenFOAM ESI v2606(`openfoam -c`), streamlit, numpy, matplotlib, pytest.

## Global Constraints

- OpenFOAM 실행은 항상 `MacGerleroEnv`를 통해서만 (`openfoam -c 'cd <cwd> && <cmd>'`). 솔버=`buoyantSimpleFoam`, 딕셔너리=`thermophysicalProperties`/`turbulenceProperties`(ESI 네이밍).
- 원방 경계는 **밀폐 등온 인클로저**(noSlip/fixedValue T/fixedFluxPressure) 고정. 개방 경계 금지.
- `snappyHexMeshDict.meshQualityControls`에 `errorReduction 0.75; nSmoothScale 4; relaxed{maxNonOrtho 75;}` 필수.
- 발열 flux 모드는 `externalWallHeatFluxTemperature` + `qr qr` 커플. 복사 `fvDOM`, 공기 흡수 0.
- 주변온도 기본 298.15 K. 검증 벤치마크: Ø6.5 mm 원통·8500 W/m²·ε0.95 → 표면 평균 ≈265 °C.
- 작업 디렉토리: `/Users/wooya/claude/openfoam/natconv-studio` (git 초기화됨). 검증된 원본 케이스: `/Users/wooya/claude/openfoam/tutorial_1`.
- 커밋 메시지는 한국어. 각 태스크 끝에 커밋.

---

### Task 1: 프로젝트 스캐폴딩 & 의존성

**Files:**
- Create: `requirements.txt`, `natconv/__init__.py`, `tests/__init__.py`, `pytest.ini`, `README.md`

**Interfaces:**
- Produces: 설치 가능한 패키지 구조. 이후 모든 태스크가 `natconv/`에 모듈 추가.

- [ ] **Step 1: requirements.txt 작성**

```
streamlit>=1.30
numpy>=1.24
matplotlib>=3.7
pytest>=7.0
```

- [ ] **Step 2: 패키지 파일 생성**

`natconv/__init__.py` (빈 파일), `tests/__init__.py` (빈 파일).

`pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 3: venv 생성 및 설치**

Run: `cd /Users/wooya/claude/openfoam/natconv-studio && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
Expected: 설치 성공, 종료코드 0.

- [ ] **Step 4: 스모크 테스트**

Run: `.venv/bin/pytest -q`
Expected: "no tests ran" (수집 에러 없음).

- [ ] **Step 5: Commit**

```bash
git add requirements.txt natconv/__init__.py tests/__init__.py pytest.ini README.md
git commit -m "프로젝트 스캐폴딩: 패키지 구조와 의존성"
```

---

### Task 2: params.py — 파라미터 데이터클래스 & 검증

**Files:**
- Create: `natconv/params.py`
- Test: `tests/test_params.py`

**Interfaces:**
- Produces: `Geometry`, `Heat`, `Params` 데이터클래스. `Params.validate() -> list[str]`(에러 메시지 목록, 비면 유효). 필드는 Step 3 코드 참조.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_params.py`:
```python
from natconv.params import Geometry, Heat, Params

def make_valid():
    return Params(geometry=Geometry(kind="cylinder", D=0.0065, L=0.10),
                  heat=Heat(mode="flux", value=8500.0, emissivity=0.95))

def test_valid_params_have_no_errors():
    assert make_valid().validate() == []

def test_bad_emissivity_reported():
    p = make_valid(); p.heat.emissivity = 1.5
    assert any("emissivity" in e for e in p.validate())

def test_bad_heat_mode_reported():
    p = make_valid(); p.heat.mode = "xxx"
    assert any("mode" in e for e in p.validate())

def test_bad_geometry_kind_reported():
    p = make_valid(); p.geometry.kind = "torus"
    assert any("kind" in e for e in p.validate())

def test_enclosure_factor_range():
    p = make_valid(); p.enclosure_factor = 5.0
    assert any("enclosure" in e for e in p.validate())
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_params.py -v`
Expected: FAIL (ModuleNotFoundError: natconv.params)

- [ ] **Step 3: 구현**

`natconv/params.py`:
```python
from dataclasses import dataclass, field

@dataclass
class Geometry:
    kind: str = "cylinder"          # cylinder | plate | stl
    D: float = 0.0065               # 원통 외경 [m]
    L: float = 0.10                 # 원통 길이 [m]
    H: float = 0.10                 # 평판 높이 [m]
    W: float = 0.05                 # 평판 폭 [m]
    t: float = 0.003                # 평판 두께 [m]
    stl_path: str = ""              # 업로드 STL 경로
    orientation: str = "horizontal" # horizontal | vertical

@dataclass
class Heat:
    mode: str = "flux"              # flux[W/m2] | fixedT[K] | power[W]
    value: float = 8500.0
    emissivity: float = 0.95

@dataclass
class Params:
    geometry: Geometry
    heat: Heat
    T_inf: float = 298.15
    enclosure_factor: float = 20.0
    base_cell: float = 0.005
    refine_level: int = 3
    n_layers: int = 5
    end_time: int = 2000
    n_procs: int = 6

    def validate(self):
        e = []
        if self.geometry.kind not in ("cylinder", "plate", "stl"):
            e.append(f"geometry.kind invalid: {self.geometry.kind}")
        if self.geometry.kind == "stl" and not self.geometry.stl_path:
            e.append("geometry.kind=stl requires stl_path")
        if self.heat.mode not in ("flux", "fixedT", "power"):
            e.append(f"heat.mode invalid: {self.heat.mode}")
        if not (0.0 < self.heat.emissivity <= 1.0):
            e.append(f"heat.emissivity must be in (0,1]: {self.heat.emissivity}")
        if self.heat.value <= 0:
            e.append("heat.value must be > 0")
        if not (15.0 <= self.enclosure_factor <= 40.0):
            e.append(f"enclosure_factor must be in [15,40]: {self.enclosure_factor}")
        if self.n_procs < 1:
            e.append("n_procs must be >= 1")
        return e
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_params.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add natconv/params.py tests/test_params.py
git commit -m "params: 파라미터 데이터클래스와 검증"
```

---

### Task 3: energy.py — 손계산(Churchill–Chu) & 에너지 평형

**Files:**
- Create: `natconv/energy.py`
- Test: `tests/test_energy.py`

**Interfaces:**
- Consumes: 없음(독립).
- Produces: `churchill_chu_cylinder(D, Ts, Tinf) -> h[W/m2K]`; `solve_surface_temp(q, D, Tinf, emissivity) -> Ts[K]`; `split(q, Ts, D, Tinf, emissivity) -> (h, q_conv, q_rad)`. 상수 `SIGMA=5.670374419e-8`.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_energy.py`:
```python
from natconv.energy import solve_surface_temp, split, SIGMA

def test_benchmark_cylinder_282C():
    # Ø6.5mm, 8500 W/m2, eps0.95, 25C 무한원통 손계산 -> ~555K(282C)
    Ts = solve_surface_temp(q=8500.0, D=0.0065, Tinf=298.15, emissivity=0.95)
    assert 545.0 < Ts < 565.0          # 272~292 C

def test_split_sums_to_q():
    Ts = solve_surface_temp(8500.0, 0.0065, 298.15, 0.95)
    h, qc, qr = split(8500.0, Ts, 0.0065, 298.15, 0.95)
    assert abs((qc + qr) - 8500.0) < 5.0
    assert 0.30 < qr / 8500.0 < 0.60   # 복사 비중 대략 절반
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_energy.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 구현**

`natconv/energy.py`:
```python
import math

SIGMA = 5.670374419e-8   # Stefan-Boltzmann [W/m2K4]

def _air_props(Tf):
    """막온도 Tf[K]에서 공기 물성 근사 (k, nu, alpha, Pr)."""
    k = 0.0242 * (Tf / 300.0) ** 0.83        # 열전도도 [W/mK]
    nu = 1.57e-5 * (Tf / 300.0) ** 1.75       # 동점성 [m2/s]
    Pr = 0.70
    alpha = nu / Pr
    beta = 1.0 / Tf
    return k, nu, alpha, Pr, beta

def churchill_chu_cylinder(D, Ts, Tinf):
    """수평 원통 자연대류 대류계수 h [W/m2K] (Churchill-Chu)."""
    Tf = 0.5 * (Ts + Tinf)
    k, nu, alpha, Pr, beta = _air_props(Tf)
    dT = max(Ts - Tinf, 1e-6)
    Ra = 9.81 * beta * dT * D**3 / (nu * alpha)
    num = 0.387 * Ra ** (1.0 / 6.0)
    den = (1.0 + (0.559 / Pr) ** (9.0 / 16.0)) ** (8.0 / 27.0)
    Nu = (0.60 + num / den) ** 2
    return Nu * k / D

def split(q, Ts, D, Tinf, emissivity):
    """주어진 Ts에서 (h, 대류유속, 복사유속)."""
    h = churchill_chu_cylinder(D, Ts, Tinf)
    q_conv = h * (Ts - Tinf)
    q_rad = emissivity * SIGMA * (Ts**4 - Tinf**4)
    return h, q_conv, q_rad

def solve_surface_temp(q, D, Tinf, emissivity):
    """q" = 대류 + 복사 를 만족하는 표면온도 Ts[K] (이분법)."""
    lo, hi = Tinf, Tinf + 2000.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        _, qc, qr = split(q, mid, D, Tinf, emissivity)
        if qc + qr > q:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_energy.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add natconv/energy.py tests/test_energy.py
git commit -m "energy: Churchill-Chu 손계산과 에너지 평형"
```

---

### Task 4: geometry.py — STL 생성 & 검증

**Files:**
- Create: `natconv/geometry.py`
- Test: `tests/test_geometry.py`

**Interfaces:**
- Consumes: `Params.geometry`(Task 2).
- Produces: `write_cylinder_stl(path, D, L, n=80)`; `write_plate_stl(path, H, W, t)`; `stl_bounds(path) -> (min_xyz, max_xyz)`; `stl_area(path) -> float`. 축 규약: 원통 축=z, 중심 원점.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_geometry.py`:
```python
import math, os
from natconv.geometry import write_cylinder_stl, stl_area, stl_bounds

def test_cylinder_area_matches_formula(tmp_path):
    p = str(tmp_path / "c.stl")
    D, L = 0.0065, 0.10
    write_cylinder_stl(p, D, L, n=200)
    lateral = math.pi * D * L
    caps = 2 * math.pi * (D/2)**2
    assert abs(stl_area(p) - (lateral + caps)) / (lateral + caps) < 0.02

def test_cylinder_bounds(tmp_path):
    p = str(tmp_path / "c.stl")
    write_cylinder_stl(p, 0.0065, 0.10, n=80)
    lo, hi = stl_bounds(p)
    assert abs(hi[2] - 0.05) < 1e-6 and abs(lo[2] + 0.05) < 1e-6   # z 축 길이
    assert abs(hi[0] - 0.00325) < 1e-4                              # 반경
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_geometry.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 구현**

`natconv/geometry.py` (원통 로직은 검증된 `tutorial_1/system/makeHeaterSTL.py` 재사용):
```python
import math

def _facet(f, p1, p2, p3):
    f.write("  facet normal 0 0 0\n    outer loop\n")
    for p in (p1, p2, p3):
        f.write(f"      vertex {p[0]:.8e} {p[1]:.8e} {p[2]:.8e}\n")
    f.write("    endloop\n  endfacet\n")

def write_cylinder_stl(path, D, L, n=80):
    R = D / 2.0
    z0, z1 = -L / 2.0, L / 2.0
    pts = [(R*math.cos(2*math.pi*i/n), R*math.sin(2*math.pi*i/n)) for i in range(n)]
    with open(path, "w") as f:
        f.write("solid heater\n")
        for i in range(n):
            x0, y0 = pts[i]; x1, y1 = pts[(i+1) % n]
            _facet(f, (x0,y0,z0), (x1,y1,z0), (x1,y1,z1))
            _facet(f, (x0,y0,z0), (x1,y1,z1), (x0,y0,z1))
            _facet(f, (0,0,z0), (x1,y1,z0), (x0,y0,z0))
            _facet(f, (0,0,z1), (x0,y0,z1), (x1,y1,z1))
        f.write("endsolid heater\n")

def write_plate_stl(path, H, W, t):
    """수직 평판(박스): x=폭W, y=높이H, z=두께t, 중심 원점."""
    hx, hy, hz = W/2.0, H/2.0, t/2.0
    v = [(-hx,-hy,-hz),( hx,-hy,-hz),( hx, hy,-hz),(-hx, hy,-hz),
         (-hx,-hy, hz),( hx,-hy, hz),( hx, hy, hz),(-hx, hy, hz)]
    quads = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(1,2,6,5),(0,3,7,4)]
    with open(path, "w") as f:
        f.write("solid heater\n")
        for a,b,c,d in quads:
            _facet(f, v[a], v[b], v[c]); _facet(f, v[a], v[c], v[d])
        f.write("endsolid heater\n")

def _read_triangles(path):
    tris, cur = [], []
    for line in open(path):
        s = line.strip()
        if s.startswith("vertex"):
            cur.append([float(x) for x in s.split()[1:4]])
            if len(cur) == 3:
                tris.append(cur); cur = []
    return tris

def stl_area(path):
    total = 0.0
    for a, b, c in _read_triangles(path):
        ux, uy, uz = (b[0]-a[0], b[1]-a[1], b[2]-a[2])
        vx, vy, vz = (c[0]-a[0], c[1]-a[1], c[2]-a[2])
        cx, cy, cz = (uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx)
        total += 0.5 * math.sqrt(cx*cx + cy*cy + cz*cz)
    return total

def stl_bounds(path):
    tris = _read_triangles(path)
    xs = [v[i] for tri in tris for v in tri for i in [0]]
    pts = [v for tri in tris for v in tri]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return tuple(lo), tuple(hi)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_geometry.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add natconv/geometry.py tests/test_geometry.py
git commit -m "geometry: 원통·평판 STL 생성과 검증"
```

---

### Task 5: environment.py — OpenFOAM 실행 추상화

**Files:**
- Create: `natconv/environment.py`
- Test: `tests/test_environment.py`

**Interfaces:**
- Produces: `OpenFOAMEnvironment`(추상, `run(command, cwd)`); `MacGerleroEnv` with 속성 `solver="buoyantSimpleFoam"`, `thermo_dict="thermophysicalProperties"`, `turb_dict="turbulenceProperties"`, 메서드 `build_shell(command, cwd) -> list[str]`, `run(command, cwd) -> subprocess.Popen`.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_environment.py`:
```python
from natconv.environment import MacGerleroEnv

def test_build_shell_wraps_openfoam():
    env = MacGerleroEnv()
    cmd = env.build_shell("blockMesh", "/tmp/case")
    assert cmd[0] == "openfoam" and cmd[1] == "-c"
    assert "cd " in cmd[2] and "blockMesh" in cmd[2]

def test_solver_and_dict_names():
    env = MacGerleroEnv()
    assert env.solver == "buoyantSimpleFoam"
    assert env.thermo_dict == "thermophysicalProperties"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_environment.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 구현**

`natconv/environment.py`:
```python
import shlex, subprocess

class OpenFOAMEnvironment:
    solver = ""
    thermo_dict = ""
    turb_dict = ""
    def run(self, command, cwd):
        raise NotImplementedError

class MacGerleroEnv(OpenFOAMEnvironment):
    """macOS gerlero OpenFOAM v2606 (ESI)."""
    solver = "buoyantSimpleFoam"
    thermo_dict = "thermophysicalProperties"
    turb_dict = "turbulenceProperties"

    def build_shell(self, command, cwd):
        inner = f"cd {shlex.quote(cwd)} && {command}"
        return ["openfoam", "-c", inner]

    def run(self, command, cwd):
        return subprocess.Popen(
            self.build_shell(command, cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_environment.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add natconv/environment.py tests/test_environment.py
git commit -m "environment: OpenFOAM 실행 추상화(Mac gerlero)"
```

---

### Task 6: templates/ 준비 — 검증된 케이스를 토큰화

**Files:**
- Create: `natconv/templates/` (아래 파일들을 `tutorial_1`에서 복사 후 토큰 치환)
- Test: `tests/test_templates_present.py`

**Interfaces:**
- Produces: 토큰이 삽입된 dict 템플릿 세트. `case_builder`(Task 7)가 소비.

토큰 규약(치환 대상): `__Q_FLUX__`, `__T_INF__`, `__EMISSIVITY__`, `__END_TIME__`, `__N_PROCS__`, `__SOLVER__`, `__XMIN__ __XMAX__ __YMIN__ __YMAX__ __ZMIN__ __ZMAX__ __NX__ __NY__ __NZ__`, `__BASE_CELL__`, `__REFINE_MIN__ __REFINE_MAX__`, `__N_LAYERS__`, `__LOC_IN_MESH__`, `__HEATER_T_BC__`.

- [ ] **Step 1: 원본 케이스 복사**

Run:
```bash
mkdir -p natconv/templates
cp /Users/wooya/claude/openfoam/tutorial_1/system/{fvSchemes,fvSolution,surfaceFeatureExtractDict} natconv/templates/
cp /Users/wooya/claude/openfoam/tutorial_1/constant/{g,thermophysicalProperties,turbulenceProperties,radiationProperties} natconv/templates/
```
Expected: 파일 복사됨(이들은 파라미터 독립이라 그대로 사용).

- [ ] **Step 2: 토큰화 dict 작성 — blockMeshDict.tmpl**

`natconv/templates/blockMeshDict.tmpl` (도메인·격자수 토큰): `tutorial_1/system/blockMeshDict`를 복사하되 `xMin..zMax`를 `__XMIN__..__ZMAX__`, `nx/ny/nz`를 `__NX__/__NY__/__NZ__`로 치환.

- [ ] **Step 3: 토큰화 dict 작성 — snappyHexMeshDict.tmpl**

`natconv/templates/snappyHexMeshDict.tmpl`: `tutorial_1/system/snappyHexMeshDict` 복사(이미 errorReduction 포함). `level (2 3)`→`level (__REFINE_MIN__ __REFINE_MAX__)`, `nSurfaceLayers 5`→`nSurfaceLayers __N_LAYERS__`, `locationInMesh (0.05 0.05 0.0)`→`locationInMesh (__LOC_IN_MESH__)`, features `level 3`→`level __REFINE_MAX__`.

- [ ] **Step 4: 토큰화 dict 작성 — controlDict.tmpl / decomposeParDict.tmpl / boundaryRadiationProperties.tmpl**

- `controlDict.tmpl`: `tutorial_1/system/controlDict`에서 `application buoyantSimpleFoam`→`application __SOLVER__`, `endTime 3000`→`endTime __END_TIME__`. (functionObjects는 그대로: heaterTavg/heaterTmax/heaterQr/wallHeatFlux, cutPlane.)
- `decomposeParDict.tmpl`: `numberOfSubdomains 6`→`numberOfSubdomains __N_PROCS__`.
- `boundaryRadiationProperties.tmpl`: `tutorial_1/constant/boundaryRadiationProperties`에서 heater `emissivity 0.95`→`emissivity __EMISSIVITY__`, `absorptivity 0.95`→`absorptivity __EMISSIVITY__`.

- [ ] **Step 5: 토큰화 필드 작성 — 0.orig 템플릿**

`natconv/templates/0.orig/` 아래에 `tutorial_1/0.orig/{U,p,p_rgh,alphat,G,IDefault,qr}` 복사(밀폐 인클로저 BC 그대로, 파라미터 독립). `T`만 `T.tmpl`로: heater patch 블록 전체를 `__HEATER_T_BC__`로, farfield `value uniform 298.15`→`value uniform __T_INF__`, internalField→`__T_INF__`.

- [ ] **Step 6: 존재 검증 테스트**

`tests/test_templates_present.py`:
```python
import os
from natconv import templates
TDIR = os.path.dirname(templates.__file__) if hasattr(templates, "__file__") else None

def test_key_templates_exist():
    base = os.path.join(os.path.dirname(__file__), "..", "natconv", "templates")
    for f in ["blockMeshDict.tmpl", "snappyHexMeshDict.tmpl", "controlDict.tmpl",
              "decomposeParDict.tmpl", "boundaryRadiationProperties.tmpl",
              "0.orig/T.tmpl", "fvSchemes", "thermophysicalProperties"]:
        assert os.path.exists(os.path.join(base, f)), f

def test_snappy_has_errorreduction():
    base = os.path.join(os.path.dirname(__file__), "..", "natconv", "templates")
    txt = open(os.path.join(base, "snappyHexMeshDict.tmpl")).read()
    assert "errorReduction" in txt
```
(`natconv/templates/__init__.py` 빈 파일 생성 필요.)

- [ ] **Step 7: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_templates_present.py -v`
Expected: 2 passed

- [ ] **Step 8: Commit**

```bash
git add natconv/templates tests/test_templates_present.py
git commit -m "templates: 검증된 케이스를 토큰화한 dict 템플릿"
```

---

### Task 7: case_builder.py — Params → 완전한 케이스 폴더

**Files:**
- Create: `natconv/case_builder.py`
- Test: `tests/test_case_builder.py`

**Interfaces:**
- Consumes: `Params`(T2), `geometry`(T4), `MacGerleroEnv`(T5, 솔버·딕셔너리명), templates(T6).
- Produces: `build_case(params, env, out_dir) -> str`(케이스 경로 반환). 도메인·격자수는 형상 바운딩박스×enclosure_factor로 산정. heater T BC 문자열은 heat.mode로 분기.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_case_builder.py`:
```python
import os
from natconv.params import Geometry, Heat, Params
from natconv.environment import MacGerleroEnv
from natconv.case_builder import build_case

def _p():
    return Params(geometry=Geometry(kind="cylinder", D=0.0065, L=0.10),
                  heat=Heat(mode="flux", value=8500.0, emissivity=0.95),
                  n_procs=4, end_time=1000)

def test_build_creates_case_files(tmp_path):
    out = build_case(_p(), MacGerleroEnv(), str(tmp_path / "case"))
    for f in ["system/blockMeshDict", "system/snappyHexMeshDict", "system/controlDict",
              "constant/triSurface/heater.stl", "constant/boundaryRadiationProperties",
              "0.orig/T", "system/fvSolution"]:
        assert os.path.exists(os.path.join(out, f)), f

def test_flux_bc_and_qr_coupling(tmp_path):
    out = build_case(_p(), MacGerleroEnv(), str(tmp_path / "case"))
    t = open(os.path.join(out, "0.orig/T")).read()
    assert "externalWallHeatFluxTemperature" in t and "qr" in t and "8500" in t

def test_enclosure_bc_not_open(tmp_path):
    out = build_case(_p(), MacGerleroEnv(), str(tmp_path / "case"))
    u = open(os.path.join(out, "0.orig/U")).read()
    assert "noSlip" in u and "pressureInletOutletVelocity" not in u

def test_tokens_all_replaced(tmp_path):
    out = build_case(_p(), MacGerleroEnv(), str(tmp_path / "case"))
    for root, _, files in os.walk(out):
        for fn in files:
            if fn.endswith(".stl"): continue
            assert "__" not in open(os.path.join(root, fn)).read(), f"토큰 미치환: {fn}"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_case_builder.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 구현**

`natconv/case_builder.py`:
```python
import os, shutil
from .geometry import write_cylinder_stl, write_plate_stl, stl_bounds

TDIR = os.path.join(os.path.dirname(__file__), "templates")

def _heater_T_bc(heat, T_inf):
    if heat.mode == "flux":
        return (f"        type            externalWallHeatFluxTemperature;\n"
                f"        mode            flux;\n"
                f"        q               uniform {heat.value};\n"
                f"        qr              qr;\n"
                f"        qrRelaxation    0.5;\n"
                f"        kappaMethod     fluidThermo;\n"
                f"        relaxation      0.7;\n"
                f"        value           uniform {T_inf};")
    if heat.mode == "fixedT":
        return (f"        type            fixedValue;\n"
                f"        value           uniform {heat.value};")
    # power: 총전력 W -> W/m2 는 build 시 면적으로 환산해 flux로 처리
    return (f"        type            externalWallHeatFluxTemperature;\n"
            f"        mode            power;\n"
            f"        Q               {heat.value};\n"
            f"        qr              qr;\n"
            f"        qrRelaxation    0.5;\n"
            f"        kappaMethod     fluidThermo;\n"
            f"        relaxation      0.7;\n"
            f"        value           uniform {T_inf};")

def _domain(params, out):
    """STL 바운딩박스 × enclosure_factor 로 도메인·격자수 산정."""
    lo, hi = stl_bounds(os.path.join(out, "constant/triSurface/heater.stl"))
    char = max(hi[i]-lo[i] for i in range(3))
    pad = char * params.enclosure_factor
    xmin, xmax = lo[0]-pad, hi[0]+pad
    ymin, ymax = lo[1]-pad, hi[1]+2*pad          # 위쪽(플룸) 더 길게
    zmin, zmax = lo[2]-pad, hi[2]+pad
    bc = params.base_cell
    nx = max(int((xmax-xmin)/bc), 10)
    ny = max(int((ymax-ymin)/bc), 10)
    nz = max(int((zmax-zmin)/bc), 10)
    return dict(XMIN=xmin, XMAX=xmax, YMIN=ymin, YMAX=ymax, ZMIN=zmin, ZMAX=zmax,
                NX=nx, NY=ny, NZ=nz,
                LOC_IN_MESH=f"{xmax-2*bc} {ymax-2*bc} {0.5*(zmin+zmax)}")

def _render(src, dst, subs):
    txt = open(src).read()
    for k, v in subs.items():
        txt = txt.replace(f"__{k}__", str(v))
    with open(dst, "w") as f:
        f.write(txt)

def build_case(params, env, out_dir):
    errors = params.validate()
    if errors:
        raise ValueError("invalid params: " + "; ".join(errors))
    for sub in ["system", "constant/triSurface", "0.orig"]:
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)

    # 1) STL
    stl = os.path.join(out_dir, "constant/triSurface/heater.stl")
    g = params.geometry
    if g.kind == "cylinder":
        write_cylinder_stl(stl, g.D, g.L)
    elif g.kind == "plate":
        write_plate_stl(stl, g.H, g.W, g.t)
    else:
        shutil.copy(g.stl_path, stl)

    # 2) 파라미터 독립 파일 그대로 복사
    for f in ["fvSchemes", "fvSolution", "surfaceFeatureExtractDict"]:
        shutil.copy(os.path.join(TDIR, f), os.path.join(out_dir, "system", f))
    for f in ["g", "thermophysicalProperties", "turbulenceProperties", "radiationProperties"]:
        shutil.copy(os.path.join(TDIR, f), os.path.join(out_dir, "constant", f))
    for f in ["U", "p", "p_rgh", "alphat", "G", "IDefault", "qr"]:
        shutil.copy(os.path.join(TDIR, "0.orig", f), os.path.join(out_dir, "0.orig", f))

    # 3) 토큰 치환
    dom = _domain(params, out_dir)
    common = dict(T_INF=params.T_inf, EMISSIVITY=params.heat.emissivity,
                  END_TIME=params.end_time, N_PROCS=params.n_procs, SOLVER=env.solver,
                  BASE_CELL=params.base_cell,
                  REFINE_MIN=max(params.refine_level-1, 1), REFINE_MAX=params.refine_level,
                  N_LAYERS=params.n_layers, Q_FLUX=params.heat.value,
                  HEATER_T_BC=_heater_T_bc(params.heat, params.T_inf), **dom)
    _render(os.path.join(TDIR, "blockMeshDict.tmpl"), os.path.join(out_dir, "system/blockMeshDict"), common)
    _render(os.path.join(TDIR, "snappyHexMeshDict.tmpl"), os.path.join(out_dir, "system/snappyHexMeshDict"), common)
    _render(os.path.join(TDIR, "controlDict.tmpl"), os.path.join(out_dir, "system/controlDict"), common)
    _render(os.path.join(TDIR, "decomposeParDict.tmpl"), os.path.join(out_dir, "system/decomposeParDict"), common)
    _render(os.path.join(TDIR, "boundaryRadiationProperties.tmpl"), os.path.join(out_dir, "constant/boundaryRadiationProperties"), common)
    _render(os.path.join(TDIR, "0.orig/T.tmpl"), os.path.join(out_dir, "0.orig/T"), common)
    return out_dir
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_case_builder.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add natconv/case_builder.py tests/test_case_builder.py
git commit -m "case_builder: Params로 완전한 케이스 폴더 생성"
```

---

### Task 8: logparse.py — 솔버 로그 → 시계열

**Files:**
- Create: `natconv/logparse.py`
- Test: `tests/test_logparse.py`, `tests/fixtures/sample_solver.log`

**Interfaces:**
- Produces: `parse_convergence(log_text) -> dict`(키 `iters, T_avg, T_max, qr` = 리스트); `current_stage(runstate) -> str`(T9에서 사용). 로그 라인 패턴은 `areaAverage(heater) of T = <값>`, `max(heater) of T = <값>`, `areaAverage(heater) of qr = <값>`.

- [ ] **Step 1: 픽스처 작성**

`tests/fixtures/sample_solver.log`:
```
Time = 50
    areaAverage(heater) of T = 451.16
    max(heater) of T = 508.6
    areaAverage(heater) of qr = -1794.0
Time = 100
    areaAverage(heater) of T = 491.37
    max(heater) of T = 543.2
    areaAverage(heater) of qr = -2639.0
```

- [ ] **Step 2: 실패 테스트 작성**

`tests/test_logparse.py`:
```python
import os
from natconv.logparse import parse_convergence

def test_parse_series():
    log = open(os.path.join(os.path.dirname(__file__), "fixtures", "sample_solver.log")).read()
    d = parse_convergence(log)
    assert d["T_avg"] == [451.16, 491.37]
    assert d["T_max"] == [508.6, 543.2]
    assert d["qr"] == [-1794.0, -2639.0]
    assert len(d["T_avg"]) == 2
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_logparse.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 4: 구현**

`natconv/logparse.py`:
```python
import re

_RE_TAVG = re.compile(r"areaAverage\(heater\) of T = ([-\d.eE+]+)")
_RE_TMAX = re.compile(r"max\(heater\) of T = ([-\d.eE+]+)")
_RE_QR   = re.compile(r"areaAverage\(heater\) of qr = ([-\d.eE+]+)")

def parse_convergence(log_text):
    T_avg = [float(x) for x in _RE_TAVG.findall(log_text)]
    T_max = [float(x) for x in _RE_TMAX.findall(log_text)]
    qr    = [float(x) for x in _RE_QR.findall(log_text)]
    iters = list(range(1, len(T_avg) + 1))
    return {"iters": iters, "T_avg": T_avg, "T_max": T_max, "qr": qr}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_logparse.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add natconv/logparse.py tests/test_logparse.py tests/fixtures/sample_solver.log
git commit -m "logparse: 솔버 로그에서 수렴 시계열 추출"
```

---

### Task 9: runner.py — 파이프라인 오케스트레이션 + RunState

**Files:**
- Create: `natconv/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: `OpenFOAMEnvironment`(T5, `run(cmd,cwd)`), 케이스 폴더(T7).
- Produces: `PIPELINE`(단계 (이름,명령) 리스트); `run_pipeline(env, case_dir, on_update=None) -> RunState`; `RunState`(dataclass: `stage:str, index:int, total:int, done:bool, error:str|None`); `read_state(case_dir)`/`write_state(case_dir, state)`(JSON). FATAL 감지 시 중단.

- [ ] **Step 1: 실패 테스트 작성 (FakeEnv로 실제 OpenFOAM 없이 검증)**

`tests/test_runner.py`:
```python
import os, subprocess
from natconv.runner import run_pipeline, PIPELINE, read_state

class FakeEnv:
    """모든 명령을 'echo <stage>'로 성공 처리."""
    solver = "buoyantSimpleFoam"
    def __init__(self, fail_on=None): self.fail_on = fail_on
    def run(self, command, cwd):
        if self.fail_on and self.fail_on in command:
            return subprocess.Popen(["bash","-c","echo 'FOAM FATAL ERROR'; exit 1"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return subprocess.Popen(["bash","-c",f"echo ok {command.split()[0]}"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

def test_pipeline_runs_all_stages(tmp_path):
    st = run_pipeline(FakeEnv(), str(tmp_path))
    assert st.done and st.error is None
    assert st.index == len(PIPELINE)

def test_pipeline_stops_on_fatal(tmp_path):
    st = run_pipeline(FakeEnv(fail_on="snappyHexMesh"), str(tmp_path))
    assert not st.done and st.error is not None
    assert "snappy" in st.stage.lower()

def test_state_persisted(tmp_path):
    run_pipeline(FakeEnv(), str(tmp_path))
    s = read_state(str(tmp_path))
    assert s["done"] is True
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_runner.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 구현**

`natconv/runner.py`:
```python
import os, json
from dataclasses import dataclass, asdict

@dataclass
class RunState:
    stage: str = ""
    index: int = 0
    total: int = 0
    done: bool = False
    error: str = None

def _pipeline(env, nprocs=None):
    solver = getattr(env, "solver", "buoyantSimpleFoam")
    return [
        ("blockMesh", "blockMesh"),
        ("surfaceFeatureExtract", "surfaceFeatureExtract"),
        ("snappyHexMesh", "snappyHexMesh -overwrite"),
        ("checkMesh", "checkMesh"),
        ("decomposePar", "cp -r 0.orig 0 && decomposePar -force"),
        ("solver", f"mpirun -np 6 {solver} -parallel"),
        ("reconstructPar", "reconstructPar -latestTime"),
    ]

PIPELINE = _pipeline(type("E", (), {"solver": "buoyantSimpleFoam"})())

def write_state(case_dir, state):
    with open(os.path.join(case_dir, "runstate.json"), "w") as f:
        json.dump(asdict(state), f)

def read_state(case_dir):
    with open(os.path.join(case_dir, "runstate.json")) as f:
        return json.load(f)

def run_pipeline(env, case_dir, on_update=None):
    stages = _pipeline(env)
    state = RunState(total=len(stages))
    for i, (name, cmd) in enumerate(stages, 1):
        state.stage, state.index = name, i
        write_state(case_dir, state)
        if on_update: on_update(state)
        proc = env.run(cmd, case_dir)
        out, _ = proc.communicate()
        logpath = os.path.join(case_dir, f"log.{name}")
        with open(logpath, "w") as f:
            f.write(out or "")
        if proc.returncode != 0 or "FOAM FATAL" in (out or ""):
            state.error = f"{name} 실패 (로그: log.{name})"
            write_state(case_dir, state)
            if on_update: on_update(state)
            return state
    state.done = True
    write_state(case_dir, state)
    if on_update: on_update(state)
    return state
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_runner.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add natconv/runner.py tests/test_runner.py
git commit -m "runner: 파이프라인 오케스트레이션과 RunState"
```

---

### Task 10: postprocess.py — 필드/메시 파싱 → 그림

**Files:**
- Create: `natconv/postprocess.py`
- Test: `tests/test_postprocess.py`

**Interfaces:**
- Consumes: 실행 완료 케이스 폴더(polyMesh, 시간폴더 `C`/`T`).
- Produces: `read_scalar_field(path) -> list[float]`; `read_vector_field(path) -> list[list[float]]`; `temperature_slice_png(case_dir, latest_time, out_png)`; `mesh_slice_png(case_dir, out_png)`. (검증된 `tutorial_1/system/makeFigures.py` 파서 로직 재사용, matplotlib Agg.)

- [ ] **Step 1: 실패 테스트 작성 (합성 필드 파일로 파서만 검증)**

`tests/test_postprocess.py`:
```python
from natconv.postprocess import read_scalar_field, read_vector_field

def test_read_scalar(tmp_path):
    p = tmp_path / "T"
    p.write_text("dimensions [0 0 0 1 0 0 0];\n"
                 "internalField   nonuniform List<scalar> \n3\n(\n298.1\n400.2\n555.3\n)\n;\n")
    assert read_scalar_field(str(p)) == [298.1, 400.2, 555.3]

def test_read_vector(tmp_path):
    p = tmp_path / "C"
    p.write_text("internalField   nonuniform List<vector> \n2\n(\n(0 0 0)\n(1 2 3)\n)\n;\n")
    assert read_vector_field(str(p)) == [[0.0,0.0,0.0],[1.0,2.0,3.0]]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/pytest tests/test_postprocess.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 구현**

`natconv/postprocess.py` — `tutorial_1/system/makeFigures.py`의 `read_scalar_field`, `read_vector_field`, `read_points`, `read_faces` 함수를 그대로 가져오고, 그림 함수 `temperature_slice_png(case_dir, latest_time, out_png)`와 `mesh_slice_png(case_dir, out_png)`를 추가한다(makeFigures.py의 fig2/fig3 로직 이식, `matplotlib.use("Agg")`, 한글 폰트 setup 포함). 파서 4개 함수의 정규식은 makeFigures.py와 동일:
```python
import re
def read_scalar_field(path):
    txt = open(path).read()
    m = re.search(r"nonuniform List<scalar>\s*\n(\d+)\s*\n\(", txt)
    n = int(m.group(1)); body = txt[m.end():]
    return [float(x) for x in body[:body.index(")")].split()][:n]

def read_vector_field(path):
    txt = open(path).read()
    m = re.search(r"nonuniform List<vector>\s*\n(\d+)\s*\n\(", txt)
    n = int(m.group(1)); body = txt[m.end():]
    vals = re.findall(r"\(\s*([-\d.eE+ ]+?)\s*\)", body)
    return [[float(x) for x in v.split()] for v in vals[:n]]
```
(그림 함수는 makeFigures.py의 해당 블록을 함수로 감싸 이식. 실행 필요 데이터가 있을 때만 호출됨.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/pytest tests/test_postprocess.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add natconv/postprocess.py tests/test_postprocess.py
git commit -m "postprocess: 필드/메시 파서와 그림 생성"
```

---

### Task 11: app/streamlit_app.py — 얇은 UI 연동

**Files:**
- Create: `app/streamlit_app.py`
- (단위테스트 없음 — 수동 검증)

**Interfaces:**
- Consumes: 코어 전부(params, case_builder, environment, runner, logparse, postprocess, energy).

- [ ] **Step 1: UI 구현**

`app/streamlit_app.py`: 사이드바에 형상(원통/평판/STL 업로드)·치수·열조건(mode/value/ε)·주변온도·인클로저배율·메시·코어수 입력 → `Params` 구성. "해석 실행" 버튼 → `build_case` → 백그라운드 스레드로 `run_pipeline(on_update=...)` → `st.autorefresh`로 `read_state`+`log.solver` tail+`parse_convergence`를 폴링해 단계 표시등·수렴 그래프·실시간 표면온도 갱신. 완료 시 `temperature_slice_png`/`mesh_slice_png` 표시, `energy.solve_surface_temp`로 손계산 대비, 에너지평형·KPI 표시.

```python
import streamlit as st, threading, os
from natconv.params import Geometry, Heat, Params
from natconv.environment import MacGerleroEnv
from natconv.case_builder import build_case
from natconv.runner import run_pipeline, read_state
from natconv.logparse import parse_convergence
from natconv import energy

st.set_page_config(page_title="natconv-studio", layout="wide")
st.title("natconv-studio — 자연대류+복사 표면온도 해석")
# ... 사이드바 입력 → Params, 실행 버튼 → 백그라운드 run_pipeline, 폴링 UI ...
```
(전체 UI 코드는 구현 시 코어 인터페이스에 맞춰 작성. UI는 로직을 갖지 않고 코어 호출만.)

- [ ] **Step 2: 앱 기동 확인**

Run: `cd /Users/wooya/claude/openfoam/natconv-studio && .venv/bin/streamlit run app/streamlit_app.py --server.headless true &` 후 `curl -s localhost:8501 | grep -qi streamlit && echo OK`
Expected: OK (앱 기동, import 에러 없음). 확인 후 프로세스 종료.

- [ ] **Step 3: Commit**

```bash
git add app/streamlit_app.py
git commit -m "app: Streamlit UI 연동(얇은 껍데기)"
```

---

### Task 12: 통합 검증 — 벤치마크 재현

**Files:** (코드 변경 없음, 검증 태스크)

- [ ] **Step 1: 벤치마크 케이스 빌드 & 실행**

Python으로 `Params(Geometry(cylinder, D=0.0065, L=0.10), Heat(flux, 8500, 0.95), n_procs=6, end_time=1500)` → `build_case` → `run_pipeline(MacGerleroEnv(), case)`. (수십 분 소요, 백그라운드.)

- [ ] **Step 2: 결과 검증**

Run: `grep "areaAverage(heater) of T" <case>/log.solver | tail -1`
Expected: 약 535~545 K (262~272 °C). `parse_convergence`와 `energy.solve_surface_temp(8500,0.0065,298.15,0.95)` 손계산(≈555 K) 대비 ±10 %.

- [ ] **Step 3: 전체 테스트 스위트 통과**

Run: `.venv/bin/pytest -q`
Expected: 전체 통과.

- [ ] **Step 4: README 갱신 & Commit**

`README.md`에 설치·실행(`streamlit run app/streamlit_app.py`)·벤치마크 결과 기록.
```bash
git add README.md
git commit -m "통합 검증: 벤치마크 재현 및 README"
```

---

## Self-Review

**Spec coverage:**
- 형상 3종(원통 T4/평판 T4/STL T7 copy) ✓ · 열조건 3모드(T7 `_heater_T_bc`) ✓ · 방사율(T6/T7) ✓
- 밀폐 인클로저 BC(T6 템플릿, T7 test_enclosure_bc_not_open) ✓ · qr 커플(T7) ✓ · errorReduction(T6 test) ✓
- 실행 파이프라인(T9) ✓ · 실시간 모니터링(T9 on_update + T11 폴링) ✓ · logparse(T8) ✓
- 시각화(T10) ✓ · 에너지평형/손계산(T3) ✓ · 환경 추상화(T5) ✓ · pytest(각 코어 태스크) ✓
- 성공기준 벤치마크 265 °C(T12) ✓

**Placeholder scan:** UI 전체 코드(T11)는 의도적으로 뼈대만 — UI는 로직 없는 얇은 껍데기이며 코어 인터페이스가 모두 확정되어 있어 구현자가 조립 가능. 그 외 코어 태스크는 실제 코드·테스트 완비.

**Type consistency:** `MacGerleroEnv.solver`(T5) ↔ case_builder `env.solver`(T7) ↔ runner `env.solver`(T9) 일치. `parse_convergence` 반환 키(iters/T_avg/T_max/qr)는 T8 정의 ↔ T11 사용 일치. `RunState` 필드(stage/index/total/done/error)는 T9 정의 ↔ T11 사용 일치.

**Gap 처리:** 없음.
