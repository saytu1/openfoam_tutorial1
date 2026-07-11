"""natconv-studio — 얇은 Streamlit UI (로직은 natconv 코어에 있음).

논블로킹 실행: 백그라운드 스레드로 파이프라인을 돌리고 2초마다 자동 새로고침으로
진행/수렴/결과를 갱신한다. 중지·재개·초기화 지원.
"""
import os
import sys
import time
import shutil
import threading
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from natconv.params import Geometry, Heat, Params
from natconv.environment import MacGerleroEnv
from natconv.case_builder import build_case
from natconv.runner import (run_pipeline, read_state, RunController,
                            latest_processor_time, set_end_time)
from natconv.logparse import parse_convergence
from natconv import energy, postprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "cases")
ss = st.session_state

st.set_page_config(page_title="natconv-studio", layout="wide")
st.title("natconv-studio — 자연대류 + 복사 표면온도 해석")

# ---------------- 사이드바: 파라미터 입력 ----------------
with st.sidebar:
    st.header("형상")
    kind = st.selectbox("형상 종류", ["cylinder", "plate", "stl"],
                        format_func=lambda k: {"cylinder": "수평 원통", "plate": "수직 평판",
                                               "stl": "STL 업로드"}[k])
    geo = Geometry(kind=kind)
    # UI는 mm 입력 → 코어는 m 사용(÷1000)
    if kind == "cylinder":
        geo.D = st.number_input("직경 D [mm]", value=6.5, format="%.2f",
                                help="원통 히터의 바깥 지름") / 1000.0
        geo.L = st.number_input("길이 L [mm]", value=100.0, format="%.1f",
                                help="원통 히터의 축방향 길이") / 1000.0
    elif kind == "plate":
        geo.H = st.number_input("높이 H [mm]", value=100.0, format="%.1f",
                                help="수직 평판의 높이(연직 방향)") / 1000.0
        geo.W = st.number_input("폭 W [mm]", value=50.0, format="%.1f",
                                help="수직 평판의 폭") / 1000.0
        geo.t = st.number_input("두께 t [mm]", value=3.0, format="%.2f",
                                help="수직 평판의 두께") / 1000.0
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
                                               "fixedT": "고정 표면온도 [°C]",
                                               "power": "총 전력 [W]"}[m],
                        help="히터 발열을 주는 방식 — 표면 단위면적당 열유속 / 표면온도 고정 / 총 전력")
    if mode == "fixedT":
        # UI는 °C 입력 → 코어는 K(+273.15)
        value = st.number_input("표면 온도 [°C]", value=282.0, format="%.1f",
                                help="히터 표면을 이 온도로 고정하고 방열량을 계산") + 273.15
    else:
        _label, _default, _fmt, _tip = {
            "flux": ("표면 열유속 [W/m²]", 8500.0, "%.1f", "히터 표면 단위면적당 발열량 (0.85 W/cm² = 8500 W/m²)"),
            "power": ("총 전력 [W]", 17.9, "%.2f", "히터 전체가 내는 총 전력"),
        }[mode]
        value = st.number_input(_label, value=_default, format=_fmt, help=_tip)
    emissivity = st.slider("방사율 ε", 0.05, 1.0, 0.95, 0.01,
                           help="표면 복사 방출률(0~1). 산화된 금속 표면은 약 0.95")

    st.header("주변 / 메시 / 실행")
    # UI는 °C 입력 → 코어는 K(+273.15)
    T_inf = st.number_input("주변 온도 [°C]", value=25.0, format="%.1f",
                            help="히터를 둘러싼 대기(인클로저 벽)의 온도. "
                                 "자연대류와 복사의 기준(주변) 온도입니다.") + 273.15
    enclosure_factor = st.slider(
        "인클로저 배율", 15.0, 40.0, 20.0, 1.0,
        help="히터를 감싸는 가상의 방(인클로저) 크기 = 형상 최소치수 × 이 값. "
             "클수록 '열린 대기'에 가깝지만 계산량이 늘어납니다. 15~30 권장.")
    refine_level = st.slider(
        "표면 정밀화 level", 2, 4, 3,
        help="히터 표면 근처 격자를 얼마나 잘게 쪼갤지. 한 단계 올릴 때마다 셀이 절반 크기로 "
             "쪼개져 정밀해지지만 셀 수가 급증합니다. 2~3 권장.")
    n_layers = st.slider(
        "프리즘 레이어 층수", 3, 7, 5,
        help="히터 표면에 붙이는 얇은 경계층 격자 층 수. 벽 근처 급격한 온도변화(열경계층)를 "
             "잘 잡아 표면온도 정확도를 높입니다. 5 권장.")
    n_procs = st.slider(
        "병렬 코어 수", 1, 10, 6,
        help="해석을 몇 개의 CPU 코어로 나눠 동시에 계산할지. 코어가 많을수록 빠릅니다.")
    end_time = st.number_input(
        "최대 반복(endTime)", value=1500, step=100,
        help="정상상태 솔버의 최대 반복(iteration) 횟수. 온도가 수렴하려면 약 1000~1500회 "
             "필요합니다. 작은 값은 동작 확인용(수렴 전).")

    st.header("저장")
    if "case_name" not in ss:
        ss.case_name = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    case_name = st.text_input("케이스 이름 (cases/ 아래)", key="case_name")

    st.header("기존 케이스 이어하기")
    existing = []
    if os.path.isdir(CASES):
        existing = sorted(d for d in os.listdir(CASES)
                          if os.path.exists(os.path.join(CASES, d, "system/controlDict")))
    sel_case = st.selectbox("케이스 선택", ["— 없음 —"] + existing)
    cont_extra = st.number_input("추가 반복 수", value=500, step=100, min_value=1)
    sel_latest = 0
    if sel_case != "— 없음 —":
        sel_latest = latest_processor_time(os.path.join(CASES, sel_case))
        st.caption(f"현재 마지막 시각: {sel_latest} → 이어서 {sel_latest + int(cont_extra)} 까지")
    cont_clicked = st.button("이어서 실행", disabled=(sel_case == "— 없음 —" or sel_latest == 0))
    if sel_case != "— 없음 —" and sel_latest == 0:
        st.caption("⚠️ 이어할 진행 결과(processor)가 없어 이어하기 불가")

params = Params(geometry=geo, heat=Heat(mode=mode, value=value, emissivity=emissivity),
                T_inf=T_inf, enclosure_factor=enclosure_factor,
                refine_level=refine_level, n_layers=n_layers,
                n_procs=n_procs, end_time=int(end_time))
errors = params.validate()
if not case_name.strip():
    errors = errors + ["케이스 이름을 입력하세요"]
if errors:
    st.error("입력 오류: " + "; ".join(errors))


# ---------------- 렌더링 헬퍼 ----------------
def _live_update(case_dir, stage_box, chart_box, kpi_box):
    rs = read_state(case_dir)
    if rs:
        idx, tot, stg = rs.get("index", 0), rs.get("total", 0), rs.get("stage", "")
        if rs.get("cancelled"):
            stage_box.warning(f"중지됨 (단계 {idx}: {stg})")
        elif rs.get("error"):
            stage_box.error(rs["error"])
        elif rs.get("done"):
            stage_box.success("완료")
        else:
            stage_box.info(f"단계 {idx}/{tot}: **{stg}**")
    logf = os.path.join(case_dir, "log.solver")
    if os.path.exists(logf):
        d = parse_convergence(open(logf).read())
        if d["T_avg"]:
            chart_box.line_chart({"표면 평균 T [K]": d["T_avg"], "표면 최고 T [K]": d["T_max"]})
            kpi_box.metric("현재 표면 평균온도", f"{d['T_avg'][-1] - 273.15:.1f} °C")


def _latest_time(case_dir):
    times = [d for d in os.listdir(case_dir)
             if d.replace(".", "").isdigit() and os.path.isdir(os.path.join(case_dir, d))]
    return max(times, key=float) if times else "0"


def _show_results(case_dir, params):
    logf = os.path.join(case_dir, "log.solver")
    if not os.path.exists(logf):
        return
    d = parse_convergence(open(logf).read())
    if not d["T_avg"]:
        st.warning("솔버 결과가 없습니다. 로그를 확인하세요.")
        return
    Tavg, Tmax = d["T_avg"][-1], d["T_max"][-1]
    qr = abs(d["qr"][-1]) if d["qr"] else 0.0
    c1, c2, c3 = st.columns(3)
    c1.metric("표면 평균온도", f"{Tavg - 273.15:.1f} °C")
    c2.metric("표면 최고온도", f"{Tmax - 273.15:.1f} °C")
    if params.heat.mode == "flux":
        c3.metric("복사 비중", f"{100 * qr / params.heat.value:.0f} %")
        if params.geometry.kind == "cylinder":
            Ts_hand = energy.solve_surface_temp(params.heat.value, params.geometry.D,
                                                params.T_inf, params.heat.emissivity)
            st.caption(f"손계산(Churchill–Chu) 대비: {Ts_hand - 273.15:.0f} °C "
                       f"(차이 {abs(Ts_hand - Tavg):.0f} K)")
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


def _start(case_dir, start_index=0):
    ctrl = RunController()
    th = threading.Thread(target=run_pipeline, args=(MacGerleroEnv(), case_dir),
                          kwargs={"start_index": start_index, "controller": ctrl}, daemon=True)
    th.start()
    ss.update(ctrl=ctrl, thread=th, case_dir=case_dir,
              active=True, stopped=False, finished=False)


# ---------------- 버튼 ----------------
active = ss.get("active", False)
stopped = ss.get("stopped", False)
b1, b2, b3, b4 = st.columns(4)
run_clicked = b1.button("해석 실행", type="primary", disabled=bool(errors) or active)
stop_clicked = b2.button("중지", disabled=not active)
resume_clicked = b3.button("재개", disabled=not stopped)
reset_clicked = b4.button("초기화")

if reset_clicked:
    if ss.get("ctrl"):
        ss.ctrl.cancel()
    for k in ["ctrl", "thread", "case_dir", "active", "stopped", "finished"]:
        ss.pop(k, None)
    st.rerun()

if run_clicked:
    case_dir = os.path.join(CASES, case_name.strip())
    if os.path.exists(case_dir):
        shutil.rmtree(case_dir)          # 새 실행은 깨끗하게 시작
    build_case(params, MacGerleroEnv(), case_dir)
    _start(case_dir)
    st.rerun()

if stop_clicked and ss.get("ctrl"):
    ss.ctrl.cancel()
    ss.active, ss.stopped = False, True
    st.rerun()

if resume_clicked and ss.get("case_dir"):
    rs = read_state(ss.case_dir)
    _start(ss.case_dir, start_index=max(rs.get("index", 1) - 1, 0))
    st.rerun()

if cont_clicked and sel_case != "— 없음 —":
    case_dir = os.path.join(CASES, sel_case)
    latest = latest_processor_time(case_dir)
    set_end_time(case_dir, latest + int(cont_extra))
    _start(case_dir, start_index=5)     # 메시·분할 건너뛰고 솔버부터 이어서
    st.rerun()

# ---------------- 진행 / 결과 ----------------
if ss.get("case_dir"):
    st.caption(f"케이스: `{ss.case_dir}`")
    _live_update(ss.case_dir, st.empty(), st.empty(), st.empty())

    if ss.get("active"):
        th = ss.get("thread")
        if th is None or not th.is_alive():
            ss.active = False
            rs = read_state(ss.case_dir)
            if rs.get("done"):
                ss.finished = True
            else:
                ss.stopped = True        # 중지 또는 에러 → 재개/초기화 가능
            st.rerun()
        else:
            time.sleep(2)
            st.rerun()

    if ss.get("finished"):
        _show_results(ss.case_dir, params)
    elif ss.get("stopped"):
        rs = read_state(ss.case_dir)
        if rs.get("error"):
            st.error(rs["error"] + " — '재개' 또는 '초기화'.")
        else:
            st.warning(f"중지됨 (단계 {rs.get('index')}/{rs.get('total')}). "
                       f"'재개'로 이어서 계속하거나 '초기화'.")
