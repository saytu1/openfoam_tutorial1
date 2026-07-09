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
