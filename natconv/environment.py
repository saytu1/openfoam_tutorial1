import shlex
import subprocess


class OpenFOAMEnvironment:
    """OpenFOAM 실행 방식을 격리하는 인터페이스. (WSL 어댑터 drop-in 지점)"""
    solver = ""
    thermo_dict = ""
    turb_dict = ""

    def run(self, command, cwd):
        raise NotImplementedError


class MacGerleroEnv(OpenFOAMEnvironment):
    """macOS gerlero OpenFOAM v2606 (ESI)."""
    solver = "buoyantSimpleFoam"
    thermo_dict = "thermophysicalProperties"
    turb_dict = "turbulenceProperties"

    def build_shell(self, command, cwd):
        inner = f"cd {shlex.quote(cwd)} && {command}"
        return ["openfoam", "-c", inner]

    def run(self, command, cwd):
        return subprocess.Popen(
            self.build_shell(command, cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True,   # 프로세스 그룹 분리 → 취소 시 자식까지 종료 가능
        )
