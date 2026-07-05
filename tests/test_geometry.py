import math
from natconv.geometry import write_cylinder_stl, stl_area, stl_bounds


def test_cylinder_area_matches_formula(tmp_path):
    p = str(tmp_path / "c.stl")
    D, L = 0.0065, 0.10
    write_cylinder_stl(p, D, L, n=200)
    lateral = math.pi * D * L
    caps = 2 * math.pi * (D / 2) ** 2
    assert abs(stl_area(p) - (lateral + caps)) / (lateral + caps) < 0.02


def test_cylinder_bounds(tmp_path):
    p = str(tmp_path / "c.stl")
    write_cylinder_stl(p, 0.0065, 0.10, n=80)
    lo, hi = stl_bounds(p)
    assert abs(hi[2] - 0.05) < 1e-6 and abs(lo[2] + 0.05) < 1e-6   # z 축 길이
    assert abs(hi[0] - 0.00325) < 1e-4                              # 반경
