import math


def _facet(f, p1, p2, p3):
    f.write("  facet normal 0 0 0\n    outer loop\n")
    for p in (p1, p2, p3):
        f.write(f"      vertex {p[0]:.8e} {p[1]:.8e} {p[2]:.8e}\n")
    f.write("    endloop\n  endfacet\n")


def write_cylinder_stl(path, D, L, n=80):
    """수평 원통(축=z, 중심 원점) STL. 측면 + 양끝 평면 캡."""
    R = D / 2.0
    z0, z1 = -L / 2.0, L / 2.0
    pts = [(R * math.cos(2 * math.pi * i / n), R * math.sin(2 * math.pi * i / n))
           for i in range(n)]
    with open(path, "w") as f:
        f.write("solid heater\n")
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            _facet(f, (x0, y0, z0), (x1, y1, z0), (x1, y1, z1))
            _facet(f, (x0, y0, z0), (x1, y1, z1), (x0, y0, z1))
            _facet(f, (0, 0, z0), (x1, y1, z0), (x0, y0, z0))
            _facet(f, (0, 0, z1), (x0, y0, z1), (x1, y1, z1))
        f.write("endsolid heater\n")


def write_plate_stl(path, H, W, t):
    """수직 평판(박스): x=폭W, y=높이H, z=두께t, 중심 원점."""
    hx, hy, hz = W / 2.0, H / 2.0, t / 2.0
    v = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
         (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
    quads = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
             (2, 3, 7, 6), (1, 2, 6, 5), (0, 3, 7, 4)]
    with open(path, "w") as f:
        f.write("solid heater\n")
        for a, b, c, d in quads:
            _facet(f, v[a], v[b], v[c])
            _facet(f, v[a], v[c], v[d])
        f.write("endsolid heater\n")


def _read_triangles(path):
    tris, cur = [], []
    for line in open(path):
        s = line.strip()
        if s.startswith("vertex"):
            cur.append([float(x) for x in s.split()[1:4]])
            if len(cur) == 3:
                tris.append(cur)
                cur = []
    return tris


def stl_area(path):
    total = 0.0
    for a, b, c in _read_triangles(path):
        ux, uy, uz = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        vx, vy, vz = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        cx, cy, cz = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
        total += 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
    return total


def stl_bounds(path):
    tris = _read_triangles(path)
    pts = [v for tri in tris for v in tri]
    lo = tuple(min(p[i] for p in pts) for i in range(3))
    hi = tuple(max(p[i] for p in pts) for i in range(3))
    return lo, hi


def rows_y(n, pitch):
    return [-pitch * (n - 1) / 2 + pitch * i for i in range(n)]


def cols_z(n, pitch):
    return [-pitch * (n - 1) / 2 + pitch * j for j in range(n)]


def _cyl_x(f, x0, x1, yc, zc, r, n=40, caps=(True, True)):
    """x축 원통(중심 yc,zc)을 열린 STL 파일 f에 기록 (측면+양끝 캡 선택).

    caps: (x0에 캡을 씌울지, x1에 캡을 씌울지). 기본값은 양끝 모두 캡.
    """
    pts = [(yc + r * math.cos(2 * math.pi * i / n), zc + r * math.sin(2 * math.pi * i / n))
           for i in range(n)]
    for i in range(n):
        y0, z0 = pts[i]
        y1, z1 = pts[(i + 1) % n]
        _facet(f, (x0, y0, z0), (x1, y1, z1), (x1, y0, z0))
        _facet(f, (x0, y0, z0), (x0, y1, z1), (x1, y1, z1))
        if caps[0]:
            _facet(f, (x0, yc, zc), (x0, y1, z1), (x0, y0, z0))
        if caps[1]:
            _facet(f, (x1, yc, zc), (x1, y0, z0), (x1, y1, z1))


def write_tube_bank_stl(path, D_t, ys, zs, x0, x1):
    with open(path, "w") as f:
        f.write("solid tubes\n")
        for yc in ys:
            for zc in zs:
                _cyl_x(f, x0, x1, yc, zc, D_t / 2)
        f.write("endsolid tubes\n")


def n_fins(x0, x1, pitch):
    return int(round((x1 - x0) / pitch)) + 1


def write_fins_stl(path, ys, fin_h, fin_z, pitch_x, x0, x1):
    """각 단(y) 중심에 fin_h(y)×fin_z(z) 사각 핀을 x방향 pitch_x 간격으로. 두께 0."""
    hz = fin_z / 2.0
    xs = [x0 + pitch_x * k for k in range(n_fins(x0, x1, pitch_x))]
    with open(path, "w") as f:
        f.write("solid fins\n")
        for xf in xs:
            for yc in ys:
                y0, y1 = yc - fin_h / 2, yc + fin_h / 2
                a = (xf, y0, -hz); b = (xf, y1, -hz)
                c = (xf, y1, hz); d = (xf, y0, hz)
                _facet(f, a, b, c)
                _facet(f, a, c, d)
        f.write("endsolid fins\n")


def heater_total_length(x0, x1, z_pitch):
    R = z_pitch / 2.0
    return 2.0 * (x1 - x0) + math.pi * R


def _ubend_x(f, xc, yc, R, r, n=40, m=24):
    """x-z 평면 반원(중심 xc,yc, 반경 R, z=-R→+R, +x로 볼록) 중심선을 따라 반경 r 튜브 스윕."""
    phis = [(-math.pi / 2) + math.pi * k / m for k in range(m + 1)]
    rings = []
    for phi in phis:
        cx, cz = xc + R * math.cos(phi), R * math.sin(phi)
        u = (math.cos(phi), 0.0, math.sin(phi))   # 접선에 수직(면내)
        ring = []
        for i in range(n):
            th = 2 * math.pi * i / n
            ring.append((cx + r * math.cos(th) * u[0],
                         yc + r * math.sin(th),
                         cz + r * math.cos(th) * u[2]))
        rings.append(ring)
    for k in range(m):
        for i in range(n):
            a = rings[k][i]; b = rings[k][(i + 1) % n]
            c = rings[k + 1][(i + 1) % n]; d = rings[k + 1][i]
            _facet(f, a, b, c)
            _facet(f, a, c, d)


def write_heater_hairpin_stl(path, D_h, x0, x1, z_pitch, yc):
    """2열(z=±z_pitch/2) 직관 다리 + 오른쪽(x1) U밴드로 이은 hairpin."""
    r = D_h / 2.0
    zc = z_pitch / 2.0
    with open(path, "w") as f:
        f.write("solid heater\n")
        _cyl_x(f, x0, x1, yc, -zc, r, caps=(True, False))     # 다리 1 (x1은 U밴드로 이어짐, 캡 없음)
        _cyl_x(f, x0, x1, yc, +zc, r, caps=(True, False))     # 다리 2 (x1은 U밴드로 이어짐, 캡 없음)
        _ubend_x(f, x1, yc, zc, r)        # 오른쪽 U밴드(z=-zc→+zc)
        f.write("endsolid heater\n")
