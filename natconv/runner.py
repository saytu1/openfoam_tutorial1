import os
import re
import json
import signal
from dataclasses import dataclass, asdict


@dataclass
class RunState:
    stage: str = ""
    index: int = 0
    total: int = 0
    done: bool = False
    error: str = None
    cancelled: bool = False


class RunController:
    """실행 중인 OpenFOAM 프로세스를 취소(종료)하기 위한 공유 컨트롤러.

    앱(메인 스레드)과 파이프라인(백그라운드 스레드) 사이에서 공유된다.
    cancel() 은 현재 실행 중인 프로세스 그룹을 종료한다(mpirun 자식 포함)."""

    def __init__(self):
        self._proc = None
        self.cancelled = False

    def set_proc(self, proc):
        self._proc = proc

    def cancel(self):
        self.cancelled = True
        p = self._proc
        if p is not None and p.poll() is None:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception:
                try:
                    p.terminate()
                except Exception:
                    pass


def _read_nprocs(case_dir):
    """케이스의 decomposeParDict 에서 실제 병렬 분할 수를 읽는다(불일치 방지)."""
    try:
        t = open(os.path.join(case_dir, "system/decomposeParDict")).read()
        return int(re.search(r"numberOfSubdomains\s+(\d+)", t).group(1))
    except Exception:
        return 6


def _pipeline(env, nprocs=6):
    solver = getattr(env, "solver", "buoyantSimpleFoam")
    return [
        ("blockMesh", "blockMesh"),
        ("surfaceFeatureExtract", "surfaceFeatureExtract"),
        ("snappyHexMesh", "snappyHexMesh -overwrite"),
        ("checkMesh", "checkMesh"),
        # snappyHexMesh가 0/ 를 생성하므로 반드시 제거 후 초기장 복원(중첩 복사 방지)
        ("decomposePar", "rm -rf 0 && cp -r 0.orig 0 && decomposePar -force"),
        ("solver", f"mpirun -np {nprocs} {solver} -parallel"),
        ("reconstructPar", "reconstructPar -latestTime"),
        ("cellCentres", "postProcess -func writeCellCentres -latestTime"),
    ]


# 참조용 기본 파이프라인 (길이·단계 이름 확인용)
PIPELINE = _pipeline(type("E", (), {"solver": "buoyantSimpleFoam"})())


def write_state(case_dir, state):
    with open(os.path.join(case_dir, "runstate.json"), "w") as f:
        json.dump(asdict(state), f)


def read_state(case_dir):
    with open(os.path.join(case_dir, "runstate.json")) as f:
        return json.load(f)


def run_pipeline(env, case_dir, start_index=0, controller=None, on_update=None):
    """파이프라인을 start_index 다음 단계부터 실행.

    - start_index: 이 값 이하 인덱스(1-based)의 단계는 건너뛴다(재개용).
    - controller: cancel 시 현재 단계를 중단하고 cancelled 상태로 반환.
    FATAL/실패 시 error 로 중단. 반환값은 RunState.
    """
    stages = _pipeline(env, _read_nprocs(case_dir))
    state = RunState(total=len(stages))
    for i, (name, cmd) in enumerate(stages, 1):
        if i <= start_index:
            continue
        if controller is not None and controller.cancelled:
            state.cancelled = True
            write_state(case_dir, state)
            if on_update:
                on_update(state)
            return state
        state.stage, state.index = name, i
        write_state(case_dir, state)
        if on_update:
            on_update(state)
        proc = env.run(cmd, case_dir)
        if controller is not None:
            controller.set_proc(proc)
        out, _ = proc.communicate()
        with open(os.path.join(case_dir, f"log.{name}"), "w") as f:
            f.write(out or "")
        if controller is not None and controller.cancelled:
            state.cancelled = True         # 중지: 이 단계부터 재개 가능(index 유지)
            write_state(case_dir, state)
            if on_update:
                on_update(state)
            return state
        if proc.returncode != 0 or "FOAM FATAL" in (out or ""):
            state.error = f"{name} 실패 (로그: log.{name})"
            write_state(case_dir, state)
            if on_update:
                on_update(state)
            return state
    state.done = True
    write_state(case_dir, state)
    if on_update:
        on_update(state)
    return state
