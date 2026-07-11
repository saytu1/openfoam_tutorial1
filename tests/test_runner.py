import subprocess
import time
from natconv.runner import run_pipeline, PIPELINE, read_state, RunController


class RecordingEnv:
    """실행된 명령을 기록하는 가짜 환경 (즉시 성공)."""
    solver = "buoyantSimpleFoam"

    def __init__(self):
        self.ran = []

    def run(self, command, cwd):
        self.ran.append(command)
        return subprocess.Popen(["bash", "-c", "true"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


class FakeEnv:
    """모든 명령을 성공 처리하는 가짜 환경 (실제 OpenFOAM 없이 파이프라인 검증)."""
    solver = "buoyantSimpleFoam"

    def __init__(self, fail_on=None):
        self.fail_on = fail_on

    def run(self, command, cwd):
        if self.fail_on and self.fail_on in command:
            return subprocess.Popen(["bash", "-c", "echo 'FOAM FATAL ERROR'; exit 1"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return subprocess.Popen(["bash", "-c", f"echo ok {command.split()[0]}"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def test_pipeline_runs_all_stages(tmp_path):
    st = run_pipeline(FakeEnv(), str(tmp_path))
    assert st.done and st.error is None
    assert st.index == len(PIPELINE)


def test_pipeline_stops_on_fatal(tmp_path):
    st = run_pipeline(FakeEnv(fail_on="snappyHexMesh"), str(tmp_path))
    assert not st.done and st.error is not None
    assert "snappy" in st.stage.lower()


def test_state_persisted(tmp_path):
    run_pipeline(FakeEnv(), str(tmp_path))
    s = read_state(str(tmp_path))
    assert s["done"] is True


def test_latest_processor_time(tmp_path):
    import os
    from natconv.runner import latest_processor_time
    for t in ["0", "500", "1000", "constant"]:
        os.makedirs(os.path.join(str(tmp_path), "processor0", t))
    assert latest_processor_time(str(tmp_path)) == 1000


def test_latest_processor_time_none(tmp_path):
    from natconv.runner import latest_processor_time
    assert latest_processor_time(str(tmp_path)) == 0


def test_set_end_time_patches_controldict(tmp_path):
    import os
    from natconv.runner import set_end_time
    os.makedirs(os.path.join(str(tmp_path), "system"))
    open(os.path.join(str(tmp_path), "system", "controlDict"), "w").write(
        "startTime       0;\nendTime         1500;         // 상한\ndeltaT          1;\n"
        "writeInterval   500;\nfunctions\n{\n    x { writeInterval   50; }\n}\n")
    et, wi = set_end_time(str(tmp_path), 2000)
    txt = open(os.path.join(str(tmp_path), "system", "controlDict")).read()
    assert et == 2000 and wi == 666
    assert "endTime         2000;" in txt
    assert "writeInterval   666;" in txt
    assert "writeInterval   50;" in txt   # functionObject 값은 그대로


def test_read_state_tolerates_partial_file(tmp_path):
    # 쓰기 도중 읽어 빈/깨진 파일이어도 예외 없이 {} 반환 (동시 접근 경합 방어)
    (tmp_path / "runstate.json").write_text("")
    assert read_state(str(tmp_path)) == {}
    (tmp_path / "runstate.json").write_text("{partial")
    assert read_state(str(tmp_path)) == {}


def test_read_state_missing_returns_empty(tmp_path):
    assert read_state(str(tmp_path)) == {}


def test_start_index_skips_stages(tmp_path):
    # start_index=5 이면 앞 5단계 건너뛰고 solver부터 실행 (재개용)
    env = RecordingEnv()
    st = run_pipeline(env, str(tmp_path), start_index=5)
    assert st.done
    assert len(env.ran) == len(PIPELINE) - 5
    assert any("buoyantSimpleFoam" in c for c in env.ran)
    assert not any(c == "blockMesh" for c in env.ran)


def test_precancelled_runs_nothing(tmp_path):
    env = RecordingEnv()
    ctrl = RunController()
    ctrl.cancelled = True
    st = run_pipeline(env, str(tmp_path), controller=ctrl)
    assert st.cancelled and not st.done
    assert env.ran == []


def test_controller_cancel_kills_process():
    ctrl = RunController()
    p = subprocess.Popen(["bash", "-c", "sleep 30"], start_new_session=True)
    ctrl.set_proc(p)
    ctrl.cancel()
    for _ in range(50):
        if p.poll() is not None:
            break
        time.sleep(0.1)
    assert p.poll() is not None   # 프로세스가 종료됨
