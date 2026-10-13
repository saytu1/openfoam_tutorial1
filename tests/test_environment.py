from natconv.environment import MacGerleroEnv, OpenFOAMLinuxEnv, get_environment


def test_build_shell_wraps_openfoam():
    env = MacGerleroEnv()
    cmd = env.build_shell("blockMesh", "/tmp/case")
    assert cmd[0] == "openfoam" and cmd[1] == "-c"
    assert "cd " in cmd[2] and "blockMesh" in cmd[2]


def test_solver_and_dict_names():
    env = MacGerleroEnv()
    assert env.solver == "buoyantSimpleFoam"
    assert env.thermo_dict == "thermophysicalProperties"


def test_linux_env_uses_plain_bash():
    # 컨테이너는 ENTRYPOINT가 FOAM 환경을 상속시키므로 bashrc를 source하지 않는다.
    cmd = OpenFOAMLinuxEnv().build_shell("blockMesh", "/app/case")
    assert cmd[0] == "bash" and cmd[1] == "-c"
    assert "cd " in cmd[2] and "blockMesh" in cmd[2]
    assert "source" not in cmd[2]


def test_get_environment_selects_by_env(monkeypatch):
    monkeypatch.delenv("NATCONV_ENV", raising=False)
    assert isinstance(get_environment(), MacGerleroEnv)
    monkeypatch.setenv("NATCONV_ENV", "linux")
    assert isinstance(get_environment(), OpenFOAMLinuxEnv)
