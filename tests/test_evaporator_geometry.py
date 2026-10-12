import math
from natconv.geometry import (write_tube_bank_stl, stl_area, rows_y, cols_z,
                               write_fins_stl, n_fins, stl_bounds)


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
