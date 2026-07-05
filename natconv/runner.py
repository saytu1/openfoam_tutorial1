import os
import json
from dataclasses import dataclass, asdict


@dataclass
class RunState:
    stage: str = ""
    index: int = 0
    total: int = 0
    done: bool = False
    error: str = None


def _pipeline(env):
    solver = getattr(env, "solver", "buoyantSimpleFoam")
    nprocs = getattr(env, "n_procs", 6)
    return [
        ("blockMesh", "blockMesh"),
        ("surfaceFeatureExtract", "surfaceFeatureExtract"),
        ("snappyHexMesh", "snappyHexMesh -overwrite"),
        ("checkMesh", "checkMesh"),
        ("decomposePar", "cp -r 0.orig 0 && decomposePar -force"),
        ("solver", f"mpirun -np {nprocs} {solver} -parallel"),
        ("reconstructPar", "reconstructPar -latestTime"),
    ]


# 참조용 기본 파이프라인 (길이·단계 이름 확인용)
PIPELINE = _pipeline(type("E", (), {"solver": "buoyantSimpleFoam", "n_procs": 6})())


def write_state(case_dir, state):
    with open(os.path.join(case_dir, "runstate.json"), "w") as f:
        json.dump(asdict(state), f)


def read_state(case_dir):
    with open(os.path.join(case_dir, "runstate.json")) as f:
        return json.load(f)


def run_pipeline(env, case_dir, on_update=None):
    """파이프라인 단계를 순서대로 실행. FATAL/실패 시 중단. RunState 반환."""
    stages = _pipeline(env)
    state = RunState(total=len(stages))
    for i, (name, cmd) in enumerate(stages, 1):
        state.stage, state.index = name, i
        write_state(case_dir, state)
        if on_update:
            on_update(state)
        proc = env.run(cmd, case_dir)
        out, _ = proc.communicate()
        with open(os.path.join(case_dir, f"log.{name}"), "w") as f:
            f.write(out or "")
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
