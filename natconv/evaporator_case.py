import os
from .geometry import (rows_y, cols_z, write_tube_bank_stl, write_fins_stl,
                       write_heater_hairpin_stl, heater_total_length)


def build_evaporator_geometry(evap, out_dir):
    """3개 STL(tubes/fins/heater)을 out_dir/constant/triSurface 에 생성. 좌표 정보 반환."""
    tri = os.path.join(out_dir, "constant", "triSurface")
    os.makedirs(tri, exist_ok=True)
    ys = rows_y(evap.n_rows, evap.pitch_y)
    zs = cols_z(evap.n_cols, evap.pitch_z)
    x0, x1 = -evap.tube_len / 2, evap.tube_len / 2
    heater_yc = min(ys) - evap.D_t / 2 - evap.heater_gap - 0.0065 / 2

    write_tube_bank_stl(os.path.join(tri, "tubes.stl"), evap.D_t, ys, zs, x0, x1)
    write_fins_stl(os.path.join(tri, "fins.stl"), ys, evap.fin_h, evap.fin_z,
                   evap.fin_pitch_x, x0, x1)
    hx0, hx1 = -evap.heater_leg_len / 2, evap.heater_leg_len / 2
    write_heater_hairpin_stl(os.path.join(tri, "heater.stl"), 0.0065, hx0, hx1,
                             evap.heater_col_pitch, heater_yc)
    return {"ys": ys, "zs": zs, "x0": x0, "x1": x1, "heater_yc": heater_yc,
            "heater_length": heater_total_length(hx0, hx1, evap.heater_col_pitch)}
