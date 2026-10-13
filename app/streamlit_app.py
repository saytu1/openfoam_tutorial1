"""natconv-studio — 얇은 Streamlit UI (로직은 natconv 코어에 있음).

논블로킹 실행 + 중지/재개/초기화 + 기존 케이스 불러오기·이어하기 + 시각화 탭.
"""
import os
import sys
import time
import shutil
import threading
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from natconv.params import Geometry, Heat, Params, Evaporator
from natconv.environment import get_environment
from natconv.case_builder import build_case
from natconv.evaporator_case import build_evaporator_geometry
from natconv.runner import (run_pipeline, read_state, RunController,
                            latest_processor_time, set_end_time)
from natconv.logparse import parse_convergence
from natconv import energy, postprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "cases")
FIGS = ["structure.png", "mesh.png", "temp_cross.png", "temp_field.png"]
ss = st.session_state

st.set_page_config(page_title="natconv-studio", layout="wide")
st.title("natconv-studio — 자연대류 + 복사 표면온도 해석")

# ============================ 사이드바: 파라미터 ============================
with st.sidebar:
    st.header("형상")
    kind = st.selectbox("형상 종류", ["cylinder", "plate", "stl"],
                        format_func=lambda k: {"cylinder": "수평 원통", "plate": "수직 평판",
                                               "stl": "STL 업로드"}[k])
    geo = Geometry(kind=kind)
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
    # ── 병렬 실행(코어 수 ↔ 케이스 분할 수) ───────────────────────
    _avail = os.cpu_count() or 1
    _in_container = os.environ.get("NATCONV_ENV", "").strip().lower() == "linux"
    _where = "컨테이너 VM" if _in_container else "이 컴퓨터"
    _smax = max(_avail, 10)
    if "n_procs" not in st.session_state:
        st.session_state["n_procs"] = min(6, _smax)

    def _match_cores():
        st.session_state["n_procs"] = _avail

    st.button("↔ 분할 수를 코어 수에 맞추기", on_click=_match_cores,
              help="케이스 분할 수를 가용 코어 수로 맞춰 MPI 실행 실패(분할>코어)를 예방합니다.")
    n_procs = st.slider(
        "병렬 코어 수(= 케이스 분할 수)", 1, _smax, key="n_procs",
        help="해석을 몇 개의 CPU 코어로 나눠 동시에 계산할지. 코어가 많을수록 빠릅니다. "
             "이 값이 '가용 코어 수'보다 크면 MPI(mpirun)가 실행을 거부합니다.")
    _c1, _c2 = st.columns(2)
    _c1.metric(f"가용 코어 ({_where})", _avail)
    _c2.metric("케이스 분할 수", n_procs)
    if n_procs > _avail:
        st.warning(f"⚠️ 분할 수({n_procs}) > 가용 코어({_avail}) → 솔버(MPI) 실행이 "
                   f"실패합니다(prte alloc-error). 위 '맞추기' 버튼을 누르거나 분할 수를 "
                   f"{_avail} 이하로 낮추세요.")
    else:
        st.caption(f"✅ 분할 수 {n_procs} ≤ 가용 코어 {_avail} — 병렬 실행 가능")
    with st.expander("ℹ️ 가용 코어(VM) 수를 늘리려면 — 호스트에서 실행"):
        st.markdown(
            "컨테이너 안에서는 VM 코어 수를 바꿀 수 없습니다. "
            "**호스트(컨테이너 바깥) 터미널**에서 아래를 실행하세요.\n\n"
            "**Mac / Windows (Podman):**\n"
            "```\npodman machine stop\npodman machine set --cpus 8\npodman machine start\n```\n"
            "**회사 PC (WSL2):** `C:\\Users\\<사용자>\\.wslconfig` 에 추가 후 "
            "`wsl --shutdown` 으로 재시작:\n"
            "```\n[wsl2]\nprocessors=8\n```\n"
            "변경 후 분할 수를 그 코어 수 이하로 두면 됩니다.")
    end_time = st.number_input(
        "최대 반복(endTime)", value=1500, step=100,
        help="정상상태 솔버의 최대 반복(iteration) 횟수. 온도가 수렴하려면 약 1000~1500회 "
             "필요합니다. 작은 값은 동작 확인용(수렴 전).")

    st.header("🧊 증발기")
    evap_enabled = st.checkbox(
        "증발기 포함", value=False,
        help="증발기(튜브 다발 + 핀 + 히터 hairpin) 형상을 함께 생성합니다. "
             "Phase 2A는 형상·메시 생성까지이며, 증발기와의 결합 해석(솔버)은 Phase 2B에서 다룹니다.")
    evap = Evaporator()
    evap_errors = []
    if evap_enabled:
        evap.D_t = st.number_input("튜브 외경 D_t [mm]", value=evap.D_t * 1000.0, format="%.2f",
                                   help="증발기 튜브의 바깥 지름") / 1000.0
        evap.n_rows = int(st.number_input("튜브 단수 n_rows", value=evap.n_rows, step=1,
                                          help="연직(y) 방향 튜브 단(row) 개수"))
        evap.n_cols = int(st.number_input("튜브 열수 n_cols", value=evap.n_cols, step=1,
                                          help="깊이(z) 방향 튜브 열(column) 개수"))
        evap.pitch_y = st.number_input("단 피치 pitch_y [mm]", value=evap.pitch_y * 1000.0, format="%.1f",
                                       help="튜브 단 사이의 연직(y) 간격") / 1000.0
        evap.pitch_z = st.number_input("열 피치 pitch_z [mm]", value=evap.pitch_z * 1000.0, format="%.1f",
                                       help="튜브 열 사이의 깊이(z) 간격") / 1000.0
        evap.tube_len = st.number_input("튜브 길이 tube_len [mm]", value=evap.tube_len * 1000.0, format="%.1f",
                                        help="튜브의 축방향(x) 길이") / 1000.0
        evap.fin_h = st.number_input("핀 높이 fin_h [mm]", value=evap.fin_h * 1000.0, format="%.1f",
                                     help="핀의 연직(y) 방향 높이") / 1000.0
        evap.fin_z = st.number_input("핀 깊이 fin_z [mm]", value=evap.fin_z * 1000.0, format="%.1f",
                                     help="핀의 깊이(z) 방향 크기 — 튜브 열 전체를 덮음") / 1000.0
        evap.fin_pitch_x = st.number_input("핀 피치 fin_pitch_x [mm]", value=evap.fin_pitch_x * 1000.0,
                                           format="%.2f", help="핀 사이의 축방향(x) 간격") / 1000.0
        evap.fin_thickness = st.number_input("핀 두께 fin_thickness [mm]", value=evap.fin_thickness * 1000.0,
                                             format="%.3f", help="핀 한 장의 두께") / 1000.0
        evap.heater_gap = st.number_input("히터 간격 heater_gap [mm]", value=evap.heater_gap * 1000.0,
                                          format="%.1f",
                                          help="최하단 튜브에서 히터까지의 연직 간격") / 1000.0
        evap.heater_leg_len = st.number_input("히터 다리 길이 heater_leg_len [mm]",
                                              value=evap.heater_leg_len * 1000.0, format="%.1f",
                                              help="히터 hairpin 각 다리의 축방향(x) 길이") / 1000.0
        evap.heater_col_pitch = st.number_input("히터 열 간격 heater_col_pitch [mm]",
                                                value=evap.heater_col_pitch * 1000.0, format="%.1f",
                                                help="히터 U자(hairpin) 두 다리 사이의 간격") / 1000.0
        evap_errors = evap.validate()

    st.header("저장")
    if "case_name" not in ss:
        ss.case_name = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    case_name = st.text_input("케이스 이름 (cases/ 아래)", key="case_name")

params = Params(geometry=geo, heat=Heat(mode=mode, value=value, emissivity=emissivity),
                T_inf=T_inf, enclosure_factor=enclosure_factor,
                refine_level=refine_level, n_layers=n_layers,
                n_procs=n_procs, end_time=int(end_time))
errors = params.validate() + evap_errors
if not case_name.strip():
    errors = errors + ["케이스 이름을 입력하세요"]


# ============================ 헬퍼 ============================
def _latest_time(case_dir):
    times = [d for d in os.listdir(case_dir)
             if d.replace(".", "").isdigit() and os.path.isdir(os.path.join(case_dir, d))]
    return max(times, key=float) if times else "0"


def _fig(case_dir, name, genfunc):
    """png 캐시: 없으면 생성해 경로 반환."""
    p = os.path.join(case_dir, name)
    if not os.path.exists(p):
        genfunc(p)
    return p


def _start(case_dir, start_index=0):
    for f in FIGS:                     # 새 실행 → 이전 그림 캐시 제거(완료 후 재생성)
        try:
            os.remove(os.path.join(case_dir, f))
        except OSError:
            pass
    ctrl = RunController()
    th = threading.Thread(target=run_pipeline, args=(get_environment(), case_dir),
                          kwargs={"start_index": start_index, "controller": ctrl}, daemon=True)
    th.start()
    ss.update(ctrl=ctrl, thread=th, case_dir=case_dir,
              active=True, stopped=False, finished=False)


def _stage_banner(case_dir, box):
    rs_path = os.path.join(case_dir, "runstate.json")
    if not os.path.exists(rs_path):
        return
    rs = read_state(case_dir)
    if rs.get("cancelled"):
        box.warning(f"중지됨 (단계 {rs['index']}: {rs['stage']}) — '재개' 또는 '초기화'")
    elif rs.get("error"):
        box.error(rs["error"] + " — '재개' 또는 '초기화'")
    elif rs.get("done"):
        box.success("완료")
    else:
        box.info(f"진행 중 · 단계 {rs['index']}/{rs['total']}: **{rs['stage']}**")


def _render_tabs(case_dir, params, active):
    t1, t2, t3, t4 = st.tabs(["🧊 구조 모델", "🔲 메쉬 구조", "📈 온도 그래프", "🌡 온도 프로파일"])

    with t3:   # 온도 그래프 (가벼움 → 항상 렌더)
        logf = os.path.join(case_dir, "log.solver")
        d = parse_convergence(open(logf).read()) if os.path.exists(logf) else {"T_avg": [], "T_max": [], "qr": []}
        if d["T_avg"]:
            k1, k2, k3 = st.columns(3)
            k1.metric("표면 평균온도", f"{d['T_avg'][-1] - 273.15:.1f} °C")
            k2.metric("표면 최고온도", f"{d['T_max'][-1] - 273.15:.1f} °C")
            if params.heat.mode == "flux" and d["qr"]:
                k3.metric("복사 비중", f"{100 * abs(d['qr'][-1]) / params.heat.value:.0f} %")
            st.line_chart({"표면 평균 T [K]": d["T_avg"], "표면 최고 T [K]": d["T_max"]})
            if params.heat.mode == "flux" and params.geometry.kind == "cylinder":
                Ts = energy.solve_surface_temp(params.heat.value, params.geometry.D,
                                               params.T_inf, params.heat.emissivity)
                st.caption(f"손계산(Churchill–Chu) 대비: {Ts - 273.15:.0f} °C "
                           f"(차이 {abs(Ts - d['T_avg'][-1]):.0f} K)")
        else:
            st.info("솔버 수렴 데이터가 아직 없습니다. (솔버 로그는 단계 완료 후 기록됩니다)")

    with t1:   # 구조 모델
        if active:
            st.info("완료 후 표시됩니다.")
        else:
            try:
                has_evap_stl = os.path.exists(os.path.join(case_dir, "constant/triSurface/tubes.stl"))
                genfunc = postprocess.structure_multi_png if has_evap_stl else postprocess.structure_png
                st.image(_fig(case_dir, "structure.png", lambda p: genfunc(case_dir, p)))
            except Exception:
                st.info("구조 모델 데이터(STL)가 아직 없습니다.")

    with t2:   # 메쉬 구조
        if active:
            st.info("완료 후 표시됩니다.")
        else:
            try:
                st.image(_fig(case_dir, "mesh.png",
                              lambda p: postprocess.mesh_slice_png(case_dir, p)))
            except Exception:
                st.info("메시가 아직 생성되지 않았습니다.")

    with t4:   # 온도 프로파일 (주변 시각화)
        latest = _latest_time(case_dir)
        if active or latest == "0":
            st.info("완료 후 표시됩니다.")
        else:
            try:
                col1, col2 = st.columns(2)
                col1.image(_fig(case_dir, "temp_cross.png",
                                lambda p: postprocess.temperature_crosssection_png(case_dir, latest, p)),
                           caption="단면 온도장 (상단이 뜨거움)")
                col2.image(_fig(case_dir, "temp_field.png",
                                lambda p: postprocess.temperature_field_png(case_dir, latest, p)),
                           caption="주변 온도 프로파일 (상승 플룸 + 대기)")
            except Exception as e:
                st.warning(f"온도장 그림 생성 실패: {e}")


# ============================ 상단: 기존 해석 불러오기 · 이어하기 ============================
existing = []
if os.path.isdir(CASES):
    existing = sorted(d for d in os.listdir(CASES)
                      if os.path.exists(os.path.join(CASES, d, "system/controlDict")))

with st.container(border=True):
    st.markdown("**📂 기존 해석 불러오기 · 이어하기**")
    c1, c2, c3, c4 = st.columns([3, 1, 1.2, 1.4])
    sel_case = c1.selectbox("케이스 선택", ["— 없음 —"] + existing, label_visibility="collapsed")
    load_clicked = c2.button("불러오기", disabled=(sel_case == "— 없음 —"), use_container_width=True)
    cont_extra = c3.number_input("추가 반복", value=500, step=100, min_value=1, label_visibility="collapsed")
    cont_clicked = c4.button("이어서 실행", disabled=(sel_case == "— 없음 —"), use_container_width=True)
    if sel_case != "— 없음 —":
        _lt = latest_processor_time(os.path.join(CASES, sel_case))
        if _lt:
            st.caption(f"`{sel_case}` — 마지막 시각 {_lt} · 불러오면 시각화 표시 / 이어서 {_lt + int(cont_extra)} 까지 계산")
        else:
            st.caption(f"`{sel_case}` — 진행 결과(processor) 없음: 이어하기 불가")

# ============================ 실행 버튼 ============================
active = ss.get("active", False)
stopped = ss.get("stopped", False)
b1, b2, b3, b4 = st.columns(4)
run_clicked = b1.button("▶ 해석 실행", type="primary", disabled=bool(errors) or active)
stop_clicked = b2.button("■ 중지", disabled=not active)
resume_clicked = b3.button("↻ 재개", disabled=not stopped)
reset_clicked = b4.button("✕ 초기화")

if errors:
    st.error("입력 오류: " + "; ".join(errors))

# ---- 버튼 핸들러 ----
if reset_clicked:
    if ss.get("ctrl"):
        ss.ctrl.cancel()
    for k in ["ctrl", "thread", "case_dir", "active", "stopped", "finished"]:
        ss.pop(k, None)
    st.rerun()

if run_clicked:
    case_dir = os.path.join(CASES, case_name.strip())
    if os.path.exists(case_dir):
        shutil.rmtree(case_dir)
    build_case(params, get_environment(), case_dir)
    if evap_enabled:
        build_evaporator_geometry(evap, case_dir)
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

if load_clicked and sel_case != "— 없음 —":
    ss.update(case_dir=os.path.join(CASES, sel_case),
              active=False, stopped=False, finished=True, ctrl=None, thread=None)
    st.rerun()

if cont_clicked and sel_case != "— 없음 —":
    case_dir = os.path.join(CASES, sel_case)
    latest = latest_processor_time(case_dir)
    set_end_time(case_dir, latest + int(cont_extra))
    _start(case_dir, start_index=5)
    st.rerun()

# ============================ 진행 상태 + 시각화 탭 ============================
if ss.get("case_dir"):
    st.caption(f"케이스: `{ss.case_dir}`")
    _stage_banner(ss.case_dir, st.empty())

    _render_tabs(ss.case_dir, params, ss.get("active", False))

    if ss.get("active"):
        th = ss.get("thread")
        if th is None or not th.is_alive():
            ss.active = False
            rs = read_state(ss.case_dir)
            ss.finished = bool(rs.get("done"))
            ss.stopped = not ss.finished
            st.rerun()
        else:
            time.sleep(2)
            st.rerun()
else:
    st.info("좌측에서 파라미터를 설정하고 **해석 실행**을 누르거나, 위에서 **기존 해석을 불러오세요**.")
