import os
import shutil

from .geometry import write_cylinder_stl, write_plate_stl, stl_bounds

TDIR = os.path.join(os.path.dirname(__file__), "templates")


def _heater_T_bc(heat, T_inf):
    """heat.mode 에 따른 히터 표면 온도 BC 블록(들여쓰기 8칸)."""
    if heat.mode == "flux":
        return (f"        type            externalWallHeatFluxTemperature;\n"
                f"        mode            flux;\n"
                f"        q               uniform {heat.value};\n"
                f"        qr              qr;\n"
                f"        qrRelaxation    0.5;\n"
                f"        kappaMethod     fluidThermo;\n"
                f"        relaxation      0.7;\n"
                f"        value           uniform {T_inf};")
    if heat.mode == "fixedT":
        return (f"        type            fixedValue;\n"
                f"        value           uniform {heat.value};")
    # power: 총전력 Q [W]
    return (f"        type            externalWallHeatFluxTemperature;\n"
            f"        mode            power;\n"
            f"        Q               {heat.value};\n"
            f"        qr              qr;\n"
            f"        qrRelaxation    0.5;\n"
            f"        kappaMethod     fluidThermo;\n"
            f"        relaxation      0.7;\n"
            f"        value           uniform {T_inf};")


def _domain(params, out):
    """STL 바운딩박스로 밀폐 인클로저 도메인·격자수 산정.

    패딩 = max(enclosure_factor × 최소치수, 최대치수).
    - 최소치수(지름/두께)는 경계층 스케일 → factor 배로 원방 벽을 충분히 멀리.
    - 최대치수만큼의 여유를 하한으로 두어 길쭉한 형상도 벽 간섭 방지.
    배경 격자수는 방향당 100으로 상한(과도 셀 폭발 방지, 근처는 snappy가 정밀화).
    """
    lo, hi = stl_bounds(os.path.join(out, "constant/triSurface/heater.stl"))
    extents = [hi[i] - lo[i] for i in range(3)]
    pad = max(params.enclosure_factor * min(extents), max(extents))
    xmin, xmax = lo[0] - pad, hi[0] + pad
    ymin, ymax = lo[1] - pad, hi[1] + 2 * pad          # 위쪽(플룸) 더 길게
    zmin, zmax = lo[2] - pad, hi[2] + pad
    bc = params.base_cell

    def ncells(span):
        return min(max(int(span / bc), 10), 100)

    return dict(XMIN=xmin, XMAX=xmax, YMIN=ymin, YMAX=ymax, ZMIN=zmin, ZMAX=zmax,
                NX=ncells(xmax - xmin), NY=ncells(ymax - ymin), NZ=ncells(zmax - zmin),
                LOC_IN_MESH=f"{xmax - 2 * bc} {ymax - 2 * bc} {0.5 * (zmin + zmax)}")


def _render(src, dst, subs):
    txt = open(src).read()
    for k, v in subs.items():
        txt = txt.replace(f"__{k}__", str(v))
    with open(dst, "w") as f:
        f.write(txt)


def build_case(params, env, out_dir):
    errors = params.validate()
    if errors:
        raise ValueError("invalid params: " + "; ".join(errors))
    for sub in ["system", "constant/triSurface", "0.orig"]:
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)

    # 1) STL
    stl = os.path.join(out_dir, "constant/triSurface/heater.stl")
    g = params.geometry
    if g.kind == "cylinder":
        write_cylinder_stl(stl, g.D, g.L)
    elif g.kind == "plate":
        write_plate_stl(stl, g.H, g.W, g.t)
    else:
        shutil.copy(g.stl_path, stl)

    # 2) 파라미터 독립 파일 그대로 복사
    for f in ["fvSchemes", "fvSolution", "surfaceFeatureExtractDict"]:
        shutil.copy(os.path.join(TDIR, f), os.path.join(out_dir, "system", f))
    for f in ["g", "thermophysicalProperties", "turbulenceProperties", "radiationProperties"]:
        shutil.copy(os.path.join(TDIR, f), os.path.join(out_dir, "constant", f))
    for f in ["U", "p", "p_rgh", "alphat", "G", "IDefault", "qr"]:
        shutil.copy(os.path.join(TDIR, "0.orig", f), os.path.join(out_dir, "0.orig", f))

    # 3) 토큰 치환
    dom = _domain(params, out_dir)
    common = dict(T_INF=params.T_inf, EMISSIVITY=params.heat.emissivity,
                  END_TIME=params.end_time, N_PROCS=params.n_procs, SOLVER=env.solver,
                  BASE_CELL=params.base_cell,
                  REFINE_MIN=max(params.refine_level - 1, 1), REFINE_MAX=params.refine_level,
                  N_LAYERS=params.n_layers, Q_FLUX=params.heat.value,
                  HEATER_T_BC=_heater_T_bc(params.heat, params.T_inf), **dom)
    _render(os.path.join(TDIR, "blockMeshDict.tmpl"),
            os.path.join(out_dir, "system/blockMeshDict"), common)
    _render(os.path.join(TDIR, "snappyHexMeshDict.tmpl"),
            os.path.join(out_dir, "system/snappyHexMeshDict"), common)
    _render(os.path.join(TDIR, "controlDict.tmpl"),
            os.path.join(out_dir, "system/controlDict"), common)
    _render(os.path.join(TDIR, "decomposeParDict.tmpl"),
            os.path.join(out_dir, "system/decomposeParDict"), common)
    _render(os.path.join(TDIR, "boundaryRadiationProperties.tmpl"),
            os.path.join(out_dir, "constant/boundaryRadiationProperties"), common)
    _render(os.path.join(TDIR, "0.orig/T.tmpl"),
            os.path.join(out_dir, "0.orig/T"), common)
    return out_dir
