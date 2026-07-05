from natconv.energy import solve_surface_temp, split, SIGMA


def test_benchmark_cylinder_282C():
    # Ø6.5mm, 8500 W/m2, eps0.95, 25C 무한원통 손계산 -> ~555K(282C)
    Ts = solve_surface_temp(q=8500.0, D=0.0065, Tinf=298.15, emissivity=0.95)
    assert 545.0 < Ts < 565.0          # 272~292 C


def test_split_sums_to_q():
    Ts = solve_surface_temp(8500.0, 0.0065, 298.15, 0.95)
    h, qc, qr = split(8500.0, Ts, 0.0065, 298.15, 0.95)
    assert abs((qc + qr) - 8500.0) < 5.0
    assert 0.30 < qr / 8500.0 < 0.60   # 복사 비중 대략 절반
