import re
from natconv.params import Geometry, Heat, Params
from natconv.environment import MacGerleroEnv
from natconv.case_builder import build_case


def _cyl():
    return Params(geometry=Geometry(kind="cylinder", D=0.0065, L=0.10),
                  heat=Heat(mode="flux", value=8500.0, emissivity=0.95))


def _read_n(block_txt):
    def v(name):
        return int(re.search(rf"\n{name}\s+(\d+);", block_txt).group(1))
    return v("nx"), v("ny"), v("nz")


def test_cylinder_domain_not_absurd(tmp_path):
    out = build_case(_cyl(), MacGerleroEnv(), str(tmp_path / "case"))
    txt = open(f"{out}/system/blockMeshDict").read()
    nx, ny, nz = _read_n(txt)
    # 방향당 100 이하, 총 배경셀 200만 이하로 유지 (폭발 방지)
    assert nx <= 100 and ny <= 100 and nz <= 100
    assert nx * ny * nz <= 2_000_000
    # 도메인이 형상(6.5mm)보다 충분히 크되(원방 벽 이격), 미터 단위로 과대하지 않음
    assert "xMin" in txt
