from natconv.environment import MacGerleroEnv


def test_build_shell_wraps_openfoam():
    env = MacGerleroEnv()
    cmd = env.build_shell("blockMesh", "/tmp/case")
    assert cmd[0] == "openfoam" and cmd[1] == "-c"
    assert "cd " in cmd[2] and "blockMesh" in cmd[2]


def test_solver_and_dict_names():
    env = MacGerleroEnv()
    assert env.solver == "buoyantSimpleFoam"
    assert env.thermo_dict == "thermophysicalProperties"
