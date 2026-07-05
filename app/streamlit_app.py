"""natconv-studio — 얇은 Streamlit UI (로직은 natconv 코어에 있음)."""
import os
import sys
import time
import json
import threading
from datetime import datetime

# 프로젝트 루트를 import 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from natconv.params import Geometry, Heat, Params
from natconv.environment import MacGerleroEnv
from natconv.case_builder import build_case
from natconv.runner import run_pipeline
from natconv.logparse import parse_convergence
from natconv import energy, postprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "cases")

st.set_page_config(page_title="natconv-studio", layout="wide")
st.title("natconv-studio — 자연대류 + 복사 표면온도 해석")

# ---------------- 사이드바: 파라미터 입력 ----------------
with st.sidebar:
    st.header("형상")
    kind = st.selectbox("형상 종류", ["cylinder", "plate", "stl"],
                        format_func=lambda k: {"cylinder": "수평 원통", "plate": "수직 평판",
                                               "stl": "STL 업로드"}[k])
    geo = Geometry(kind=kind)
    if kind == "cylinder":
        geo.D = st.number_input("직경 D [m]", value=0.0065, format="%.4f")
        geo.L = st.number_input("길이 L [m]", value=0.10, format="%.3f")
    elif kind == "plate":
        geo.H = st.number_input("높이 H [m]", value=0.10, format="%.3f")
        geo.W = st.number_input("폭 W [m]", value=0.05, format="%.3f")
        geo.t = st.number_input("두께 t [m]", value=0.003, format="%.4f")
    else:
        up = st.file_uploader("STL 파일", type=["stl"])
        if up:
            os.makedirs(CASES, exist_ok=True)
            geo.stl_path = os.path.join(CASES, "_upload.stl")
            with open(geo.stl_path, "wb") as f:
                f.write(up.getbuffer())

    st.header("열 조건")
    mode = st.selectbox("발열 방식", ["flux", "fixedT", "power"],
                        format_func=lambda m: {"flux": "표면 열유속 [W/m²]",
                                               "fixedT": "고정 표면온도 [K]",
                                               "power": "총 전력 [W]"}[m])
    default_val = {"flux": 8500.0, "fixedT": 555.0, "power": 17.9}[mode]
    value = st.number_input("값", value=default_val)
    emissivity = st.slider("방사율 ε", 0.05, 1.0, 0.95, 0.01)

    st.header("주변 / 메시 / 실행")
    T_inf = st.number_input("주변 온도 [K]", value=298.15)
    enclosure_factor = st.slider("인클로저 배율", 15.0, 40.0, 20.0, 1.0)
    refine_level = st.slider("표면 정밀화 level", 2, 4, 3)
    n_layers = st.slider("프리즘 레이어 층수", 3, 7, 5)
    n_procs = st.slider("병렬 코어 수", 1, 10, 6)
    end_time = st.number_input("최대 반복(endTime)", value=1500, step=100)

params = Params(geometry=geo, heat=Heat(mode=mode, value=value, emissivity=emissivity),
                T_inf=T_inf, enclosure_factor=enclosure_factor,
                refine_level=refine_level, n_layers=n_layers,
                n_procs=n_procs, end_time=int(end_time))

errors = params.validate()
if errors:
    st.error("입력 오류: " + "; ".join(errors))

# ---------------- 실시간 모니터링 / 결과 헬퍼 ----------------
def _live_update(case_dir, stage_box, chart_box, kpi_box):
    rs_path = os.path.join(case_dir, "runstate.json")
    if os.path.exists(rs_path):
        rs = json.load(open(rs_path))
        msg = f"단계 {rs['index']}/{rs['total']}: **{rs['stage']}**"
        if rs.get("error"):
            stage_box.error(rs["error"])
        elif rs.get("done"):
            stage_box.success("완료")
        else:
            stage_box.info(msg)
    logf = os.path.join(case_dir, "log.solver")
    if os.path.exists(logf):
        d = parse_convergence(open(logf).read())
        if d["T_avg"]:
            chart_box.line_chart({"표면 평균 T [K]": d["T_avg"], "표면 최고 T [K]": d["T_max"]})
            kpi_box.metric("현재 표면 평균온도", f"{d['T_avg'][-1] - 273.15:.1f} °C")


def _show_results(case_dir, params):
    logf = os.path.join(case_dir, "log.solver")
    if not os.path.exists(logf):
        return
    d = parse_convergence(open(logf).read())
    if not d["T_avg"]:
        st.warning("솔버 결과가 없습니다. 로그를 확인하세요.")
        return
    Tavg = d["T_avg"][-1]; Tmax = d["T_max"][-1]; qr = abs(d["qr"][-1]) if d["qr"] else 0.0
    c1, c2, c3 = st.columns(3)
    c1.metric("표면 평균온도", f"{Tavg - 273.15:.1f} °C")
    c2.metric("표면 최고온도", f"{Tmax - 273.15:.1f} °C")
    if params.heat.mode == "flux":
        q = params.heat.value
        c3.metric("복사 비중", f"{100 * qr / q:.0f} %")
        Ts_hand = energy.solve_surface_temp(q, params.geometry.D, params.T_inf,
                                            params.heat.emissivity)
        st.caption(f"손계산(Churchill–Chu) 대비: {Ts_hand - 273.15:.0f} °C "
                   f"(차이 {abs(Ts_hand - Tavg):.0f} K)")
    # 그림
    try:
        latest = _latest_time(case_dir)
        mp = postprocess.mesh_slice_png(case_dir, os.path.join(case_dir, "mesh.png"))
        tp = postprocess.temperature_slice_png(case_dir, latest,
                                               os.path.join(case_dir, "temp.png"))
        g1, g2 = st.columns(2)
        g1.image(mp, caption="단면 메시")
        g2.image(tp, caption="단면 온도장 (상단이 뜨거움)")
    except Exception as e:
        st.warning(f"그림 생성 건너뜀: {e}")


def _latest_time(case_dir):
    times = [d for d in os.listdir(case_dir)
             if d.replace(".", "").isdigit() and os.path.isdir(os.path.join(case_dir, d))]
    return max(times, key=float)


# ---------------- 실행 & 실시간 모니터링 ----------------
run = st.button("해석 실행", type="primary", disabled=bool(errors))

if run:
    case_dir = os.path.join(CASES, datetime.now().strftime("%Y%m%d_%H%M%S"))
    build_case(params, MacGerleroEnv(), case_dir)
    st.info(f"케이스 생성: `{case_dir}` — 파이프라인 실행 중…")

    th = threading.Thread(target=run_pipeline, args=(MacGerleroEnv(), case_dir), daemon=True)
    th.start()

    stage_box, chart_box, kpi_box = st.empty(), st.empty(), st.empty()
    while th.is_alive():
        _live_update(case_dir, stage_box, chart_box, kpi_box)
        time.sleep(2)
    _live_update(case_dir, stage_box, chart_box, kpi_box)
    _show_results(case_dir, params)
