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
