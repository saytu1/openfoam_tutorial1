import re
from natconv.params import Geometry, Heat, Params
from natconv.environment import MacGerleroEnv
from natconv.case_builder import build_case


def _wi_et(case_dir):
    txt = open(f"{case_dir}/system/controlDict").read()
    wi = int(re.search(r"\nwriteInterval\s+(\d+);", txt).group(1))
    et = int(re.search(r"\nendTime\s+(\d+);", txt).group(1))
    return wi, et


def test_small_endtime_still_writes(tmp_path):
    # 작은 endTime(빠른 테스트)에서도 중간 write가 나오도록 writeInterval < endTime
    p = Params(geometry=Geometry(kind="cylinder", D=0.0065, L=0.10),
               heat=Heat(mode="flux", value=8500.0, emissivity=0.95), end_time=10)
    out = build_case(p, MacGerleroEnv(), str(tmp_path / "c"))
    wi, et = _wi_et(out)
    assert 1 <= wi < et            # 반드시 endTime 전에 최소 1회 write


def test_normal_endtime(tmp_path):
    p = Params(geometry=Geometry(kind="cylinder", D=0.0065, L=0.10),
               heat=Heat(mode="flux", value=8500.0, emissivity=0.95), end_time=1500)
    out = build_case(p, MacGerleroEnv(), str(tmp_path / "c"))
    wi, et = _wi_et(out)
    assert 1 <= wi < et
    assert wi == 500               # 검증된 벤치마크와 동일
