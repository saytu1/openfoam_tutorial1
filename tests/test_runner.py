import subprocess
from natconv.runner import run_pipeline, PIPELINE, read_state


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
