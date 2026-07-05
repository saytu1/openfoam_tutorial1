import math

SIGMA = 5.670374419e-8   # Stefan-Boltzmann [W/m2K4]


def _air_props(Tf):
    """막온도 Tf[K]에서 공기 물성 근사 (k, nu, alpha, Pr, beta)."""
    k = 0.0242 * (Tf / 300.0) ** 0.83        # 열전도도 [W/mK]
    nu = 1.57e-5 * (Tf / 300.0) ** 1.75       # 동점성 [m2/s]
    Pr = 0.70
    alpha = nu / Pr
    beta = 1.0 / Tf
    return k, nu, alpha, Pr, beta


def churchill_chu_cylinder(D, Ts, Tinf):
    """수평 원통 자연대류 대류계수 h [W/m2K] (Churchill-Chu)."""
    Tf = 0.5 * (Ts + Tinf)
    k, nu, alpha, Pr, beta = _air_props(Tf)
    dT = max(Ts - Tinf, 1e-6)
    Ra = 9.81 * beta * dT * D**3 / (nu * alpha)
    num = 0.387 * Ra ** (1.0 / 6.0)
    den = (1.0 + (0.559 / Pr) ** (9.0 / 16.0)) ** (8.0 / 27.0)
    Nu = (0.60 + num / den) ** 2
    return Nu * k / D


def split(q, Ts, D, Tinf, emissivity):
    """주어진 Ts에서 (h, 대류유속, 복사유속)."""
    h = churchill_chu_cylinder(D, Ts, Tinf)
    q_conv = h * (Ts - Tinf)
    q_rad = emissivity * SIGMA * (Ts**4 - Tinf**4)
    return h, q_conv, q_rad


def solve_surface_temp(q, D, Tinf, emissivity):
    """q" = 대류 + 복사 를 만족하는 표면온도 Ts[K] (이분법)."""
    lo, hi = Tinf, Tinf + 2000.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        _, qc, qr = split(q, mid, D, Tinf, emissivity)
        if qc + qr > q:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)
