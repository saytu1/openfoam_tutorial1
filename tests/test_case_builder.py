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
            if fn.endswith(".stl"):
                continue
            assert "__" not in open(os.path.join(root, fn)).read(), f"토큰 미치환: {fn}"
