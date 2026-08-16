import os
from .geometry import (rows_y, cols_z, write_tube_bank_stl, write_fins_stl,
                       write_heater_hairpin_stl, heater_total_length, stl_bounds)

TDIR = os.path.join(os.path.dirname(__file__), "templates")


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


def _render(src, dst, subs):
    txt = open(src).read()
    for k, v in subs.items():
        txt = txt.replace(f"__{k}__", str(v))
    with open(dst, "w") as f:
        f.write(txt)


def _p2a_domain(tri, enclosure_factor, base_cell):
    """3개 STL(tubes/fins/heater)의 결합 바운딩박스로 밀폐 인클로저 도메인 산정.

    Phase 1 _domain과 같은 방식(패딩 = max(factor*최소치수, 최대치수))이나,
    이 조립체는 이미 거시적 크기(~600mm)이므로 factor를 완화(10~15)해서 쓴다.
    배경 격자수는 방향당 100 상한.
    """
    los, his = zip(*[stl_bounds(os.path.join(tri, f"{n}.stl"))
                      for n in ("tubes", "fins", "heater")])
    lo = tuple(min(l[i] for l in los) for i in range(3))
    hi = tuple(max(h[i] for h in his) for i in range(3))
    extents = [hi[i] - lo[i] for i in range(3)]
    pad = max(enclosure_factor * min(extents), max(extents))
    xmin, xmax = lo[0] - pad, hi[0] + pad
    ymin, ymax = lo[1] - pad, hi[1] + 2 * pad          # 위쪽(플룸) 더 길게
    zmin, zmax = lo[2] - pad, hi[2] + pad

    def ncells(span):
        return min(max(int(span / base_cell), 10), 100)

    return dict(XMIN=xmin, XMAX=xmax, YMIN=ymin, YMAX=ymax, ZMIN=zmin, ZMAX=zmax,
                NX=ncells(xmax - xmin), NY=ncells(ymax - ymin), NZ=ncells(zmax - zmin),
                LOC_IN_MESH=f"{xmax - 2 * base_cell} {ymax - 2 * base_cell} "
                            f"{0.5 * (zmin + zmax)}")


def build_phase2a_case(evap, out_dir, enclosure_factor=10.0, base_cell=0.025,
                        refine_min=2, refine_max=4, n_layers=3):
    """Phase 2A 증발기+히터 케이스: STL + 메시 관련 dict 일체 작성.

    tubes/heater는 벽(wall), fins는 faceZone -> createBaffles로 baffle patch화.
    """
    for sub in ["system", "constant/triSurface"]:
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
    tri = os.path.join(out_dir, "constant", "triSurface")

    build_evaporator_geometry(evap, out_dir)

    dom = _p2a_domain(tri, enclosure_factor, base_cell)
    common = dict(REFINE_MIN=refine_min, REFINE_MAX=refine_max, N_LAYERS=n_layers, **dom)

    _render(os.path.join(TDIR, "blockMeshDict.tmpl"),
            os.path.join(out_dir, "system/blockMeshDict"), common)
    _render(os.path.join(TDIR, "snappyHexMeshDict_evap.tmpl"),
            os.path.join(out_dir, "system/snappyHexMeshDict"), common)

    with open(os.path.join(out_dir, "system/surfaceFeatureExtractDict"), "w") as f:
        f.write(_SFE_HEADER)
        for name in ("tubes", "fins", "heater"):
            f.write(_SFE_ENTRY.format(name=name))
        f.write(_SFE_FOOTER)

    with open(os.path.join(out_dir, "system/createBafflesDict"), "w") as f:
        f.write(_CREATE_BAFFLES_DICT)

    for f_ in ["fvSchemes", "fvSolution"]:
        with open(os.path.join(TDIR, f_)) as src, \
             open(os.path.join(out_dir, "system", f_), "w") as dst:
            dst.write(src.read())

    _render(os.path.join(TDIR, "controlDict.tmpl"),
            os.path.join(out_dir, "system/controlDict"),
            dict(SOLVER="buoyantSimpleFoam", END_TIME=1000, WRITE_INTERVAL=500))

    return out_dir


_SFE_HEADER = """/*--------------------------------*- C++ -*----------------------------------*\\
| Phase 2A 증발기+히터 - 특징선 추출 (tubes/fins/heater STL)                  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      surfaceFeatureExtractDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

"""

_SFE_ENTRY = """{name}.stl
{{
    extractionMethod    extractFromSurface;

    extractFromSurfaceCoeffs
    {{
        includedAngle   150;
    }}

    subsetFeatures
    {{
        nonManifoldEdges no;
        openEdges       yes;
    }}

    writeObj        yes;
}}

"""

_SFE_FOOTER = "// ************************************************************************* //\n"

_CREATE_BAFFLES_DICT = """/*--------------------------------*- C++ -*----------------------------------*\\
| Phase 2A 증발기 핀 - snappyHexMesh가 만든 finsZone faceZone을              |
| baffle patch(fins/fins_slave)로 변환                                        |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      createBafflesDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

internalFacesOnly true;

baffles
{
    fins
    {
        type        faceZone;
        zoneName    finsZone;

        patchPairs
        {
            type            wall;
        }
    }
}

// ************************************************************************* //
"""
