import os, math
from natconv.params import Evaporator
from natconv.evaporator_case import build_evaporator_geometry, build_phase2a_case
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


def test_build_phase2a_case_writes_system_dicts(tmp_path):
    out = str(tmp_path / "p2a")
    build_phase2a_case(Evaporator(), out)
    for name in ("blockMeshDict", "snappyHexMeshDict", "surfaceFeatureExtractDict",
                 "createBafflesDict", "controlDict", "fvSchemes", "fvSolution"):
        path = os.path.join(out, "system", name)
        assert os.path.exists(path), name

    # 토큰이 모두 치환되어 __XXX__ 형태가 남아있지 않아야 함
    for name in ("blockMeshDict", "snappyHexMeshDict", "controlDict"):
        txt = open(os.path.join(out, "system", name)).read()
        assert "__" not in txt, f"unsubstituted token in {name}"

    # createBafflesDict: fins faceZone -> baffle patch
    cb = open(os.path.join(out, "system", "createBafflesDict")).read()
    assert "finsZone" in cb
    assert "type        faceZone" in cb

    # snappyHexMeshDict: tubes/heater는 wall, fins는 baffle 유지
    shm = open(os.path.join(out, "system", "snappyHexMeshDict")).read()
    assert "finsZone" in shm
    assert "faceType    baffle" in shm

    # surfaceFeatureExtractDict: 3개 STL 모두 등록
    sfe = open(os.path.join(out, "system", "surfaceFeatureExtractDict")).read()
    for name in ("tubes.stl", "fins.stl", "heater.stl"):
        assert name in sfe
