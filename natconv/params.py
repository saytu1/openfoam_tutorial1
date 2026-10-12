from dataclasses import dataclass


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
