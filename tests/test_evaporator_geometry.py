import math
from natconv.geometry import (write_tube_bank_stl, stl_area, rows_y, cols_z)


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
