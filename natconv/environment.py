import os
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


class OpenFOAMLinuxEnv(OpenFOAMEnvironment):
    """컨테이너(Linux) 환경. gerlero/microfluidica OpenFOAM v2606 이미지 전제.

    컨테이너 ENTRYPOINT(/openfoam/run)가 OpenFOAM 환경을 이미 로드한 채로
    Streamlit을 띄우므로, 자식 프로세스는 FOAM 환경변수를 그대로 상속받는다.
    따라서 bashrc를 다시 source할 필요 없이 일반 bash로 명령을 실행하면 된다.
    """
    solver = "buoyantSimpleFoam"
    thermo_dict = "thermophysicalProperties"
    turb_dict = "turbulenceProperties"

    def build_shell(self, command, cwd):
        inner = f"cd {shlex.quote(cwd)} && {command}"
        return ["bash", "-c", inner]

    def run(self, command, cwd):
        return subprocess.Popen(
            self.build_shell(command, cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True,
        )


def get_environment():
    """실행 환경 선택. NATCONV_ENV=linux(컨테이너) 이면 Linux, 아니면 Mac."""
    if os.environ.get("NATCONV_ENV", "mac").strip().lower() == "linux":
        return OpenFOAMLinuxEnv()
    return MacGerleroEnv()
