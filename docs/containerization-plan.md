# natconv-studio 컨테이너화 계획 (개발 Mac ↔ 사용 회사 Windows 환경 일치)

> 목표: 개발(Mac)과 사용(회사 Windows PC)의 OpenFOAM 실행 환경을 **컨테이너로 완전히 일치**시킨다.
> 제약: 회사 PC는 **Docker Desktop 설치 불가** → **Podman**(무료 오픈소스 컨테이너 엔진)만 사용.
> 이동 수단: **GitHub(코드) + GitHub Actions(자동 빌드) + GHCR(이미지 창고)**.
> 이 문서는 초보자가 따라할 수 있도록 "왜/무엇을/어떻게"를 단계별로 적는다.

---

## 0. 핵심 개념 (초보용 요약)

- **컨테이너** = 프로그램과 그 실행에 필요한 모든 것(OS 라이브러리, OpenFOAM, 파이썬 등)을 통째로 담은 "박스". 어느 PC에서 열어도 박스 안은 똑같다 → 환경 일치.
- **이미지** = 컨테이너의 "설치 CD". `Containerfile`(= Dockerfile, 설계도)로 만든다.
- **Podman** = 컨테이너를 돌리는 엔진. Docker와 사용법 거의 동일, **라이센스 무료**. (라이센스 제한은 "Docker Desktop" GUI 앱에만 해당)
- **GHCR** = GitHub가 제공하는 이미지 창고(`ghcr.io`). Podman으로 올리고/받는다.
- **아키텍처**: Mac=arm64, 회사 PC=amd64. 이미지는 아키텍처별로 다르다 → **GitHub Actions가 클라우드에서 amd64 이미지를 자동 빌드**해 해결.

**완성 후 회사 PC 사용법 (목표 상태):**
```
(WSL 터미널)  podman pull ghcr.io/<계정>/natconv-studio:latest
             podman run --rm -p 8501:8501 -v $PWD/cases:/app/cases ghcr.io/<계정>/natconv-studio
(윈도우 브라우저)  http://localhost:8501  접속 → 평소처럼 사용
```

---

## 1. 전체 흐름

```
[개발: Mac] ──git push──▶ [GitHub 저장소: 코드 + Containerfile]
                                   │
                           [GitHub Actions] 클라우드에서 amd64 이미지 자동 빌드
                                   │ push
                                   ▼
                          [GHCR: ghcr.io/<계정>/natconv-studio]
                                   │ podman pull
                                   ▼
          [회사 Windows PC: WSL + Podman] ── podman run -p 8501:8501
                                   │
                          [윈도우 브라우저] localhost:8501
```

- 컨테이너 **한 개 안에 OpenFOAM + 파이썬 + Streamlit + natconv-studio 전부** 포함 → 경로 변환·의존성 문제 없음.
- Mac 일상 개발은 지금처럼 네이티브(`MacGerleroEnv`)로 빠르게, 컨테이너는 "배포·완전일치 검증"용으로 병행.

---

## 2. 사전 확인 (먼저 체크할 것)

| 확인 항목 | 방법 | 안 되면 대안 |
|---|---|---|
| 회사 PC WSL이 `ghcr.io`에 접속되나 | WSL에서 `curl -I https://ghcr.io` (응답 오면 OK) | 폐쇄망 → 7장 오프라인(USB tar) |
| 회사 PC WSL에 Podman 설치 가능한가 | WSL에서 `sudo apt-get install -y podman` | 관리자/보안정책 확인 필요 |
| GitHub 계정·저장소 생성 가능한가 | github.com 로그인 | 사내 GitHub Enterprise면 그쪽 사용 |
| Mac에서 로컬 컨테이너 테스트 | `brew install podman && podman machine init && podman machine start` | 선택(없어도 CI로 검증 가능) |

---

## 3. 만들 산출물 (4가지)

1. **`Containerfile`** (프로젝트 루트) — 이미지 설계도.
2. **`.github/workflows/build-image.yml`** — GitHub Actions 자동 빌드·GHCR 푸시.
3. **`natconv/environment.py`에 `OpenFOAMLinuxEnv` 추가** + 환경 선택 함수 — 컨테이너(리눅스) 안에서 OpenFOAM 실행.
4. **`docs/deploy-windows.md`** — 회사 PC 설치·실행 안내서(초보용).

코어·UI·물리 로직은 변경 없음.

---

## 4. 설계 상세

### 4-1. Containerfile (설계도)

구성(의사 코드):
```dockerfile
# 1) 베이스: 리눅스 OpenFOAM (Mac의 v2606과 "같은 버전"으로 맞춘다)
#    ESI 공식 이미지 사용 권장: opencfd/openfoam-default:<버전>
#    ★구현 시 확인: hub.docker.com 에서 2606 태그 존재 여부. 없으면 가장 가까운 ESI 버전
#    또는 ubuntu + openfoam.com apt 저장소로 openfoam2606 설치.
FROM opencfd/openfoam-default:2606

# 2) 파이썬/앱 의존성
RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*

# 3) 앱 복사 + 설치
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY natconv/ ./natconv/
COPY app/ ./app/

# 4) 앱이 "리눅스 환경"을 쓰도록 지정
ENV NATCONV_ENV=linux
# OpenFOAM bashrc 경로(베이스 이미지에 따라 다름) — 어댑터가 source 할 경로
ENV FOAM_BASHRC=/openfoam/bashrc

# 5) Streamlit 포트 + 실행
EXPOSE 8501
CMD ["bash","-lc","source $FOAM_BASHRC && streamlit run app/streamlit_app.py --server.address 0.0.0.0 --server.port 8501"]
```
핵심:
- **베이스 OpenFOAM 버전을 Mac(v2606)과 맞춘다** → 결과 일치의 근거.
- 앱이 컨테이너 안에서 돌므로 `--server.address 0.0.0.0`(외부에서 접속 허용) 필요.
- 결과 보존을 위해 실행 시 `cases/`를 호스트에 볼륨 마운트(5장).

### 4-2. environment.py — 리눅스 어댑터 1개 추가

기존 `MacGerleroEnv`(= `openfoam -c '...'`)는 그대로 두고, 아래를 추가:
```python
class OpenFOAMLinuxEnv(OpenFOAMEnvironment):
    """컨테이너/WSL 리눅스 안에서 OpenFOAM 실행 (bashrc source 후 bash -lc)."""
    solver = "buoyantSimpleFoam"
    thermo_dict = "thermophysicalProperties"
    turb_dict = "turbulenceProperties"

    def __init__(self, bashrc=None):
        self.bashrc = bashrc or os.environ.get("FOAM_BASHRC", "")

    def build_shell(self, command, cwd):
        src = f"source {shlex.quote(self.bashrc)} && " if self.bashrc else ""
        return ["bash", "-lc", f"{src}cd {shlex.quote(cwd)} && {command}"]

    def run(self, command, cwd):
        return subprocess.Popen(self.build_shell(command, cwd),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, start_new_session=True)


def get_environment():
    """NATCONV_ENV 로 환경 선택 (기본 mac). 컨테이너에선 linux."""
    if os.environ.get("NATCONV_ENV", "mac").lower() == "linux":
        return OpenFOAMLinuxEnv()
    return MacGerleroEnv()
```
그리고 `app/streamlit_app.py`에서 `MacGerleroEnv()` 직접 호출을 **`get_environment()`로 교체**(한 줄 수준). 코어 `runner`는 env를 인자로 받으므로 변경 없음.

검증(테스트): `build_shell`이 `bash -lc`로 감싸는지, `get_environment()`가 환경변수로 올바른 어댑터를 반환하는지 pytest. (OpenFOAM 실제 실행은 컨테이너에서 통합 검증.)

### 4-3. GitHub Actions (자동 빌드)

`.github/workflows/build-image.yml`(요지):
```yaml
on:
  push: { branches: [main] }
jobs:
  build:
    runs-on: ubuntu-latest        # GitHub 클라우드 = amd64 네이티브
    permissions: { contents: read, packages: write }
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with: { registry: ghcr.io, username: ${{ github.actor }}, password: ${{ secrets.GITHUB_TOKEN }} }
      - uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64          # 회사 PC용. (필요시 ,linux/arm64 추가)
          push: true
          tags: ghcr.io/${{ github.repository_owner }}/natconv-studio:latest
```
→ `main`에 push할 때마다 amd64 이미지가 자동으로 GHCR에 올라간다. 회사 PC는 받기만 하면 됨.

### 4-4. 실행 시 결과 보존 (볼륨)

컨테이너는 끄면 내부 결과가 사라진다. 케이스/결과를 호스트에 남기려면:
```
podman run --rm -p 8501:8501 -v $PWD/cases:/app/cases ghcr.io/<계정>/natconv-studio
```
`-v 호스트경로:컨테이너경로` 로 `cases/`를 연결 → 결과가 WSL 파일시스템에 남음.

---

## 5. 작업 순서 (단계별 계획)

### 단계 1 — GitHub 저장소 준비 (Mac)
- `natconv-studio`에 원격 추가: `git remote add origin https://github.com/<계정>/natconv-studio.git` → `git push -u origin main`.
- GHCR는 저장소에 자동 연동(별도 생성 불필요).

### 단계 2 — Containerfile 작성 & 로컬 빌드 검증 (Mac, 선택)
- `Containerfile` 작성.
- Mac에 Podman 머신 준비 후 `podman build -t natconv-studio .` → `podman run -p 8501:8501 natconv-studio` → `localhost:8501` 동작 확인. (arm64로 빌드되지만 "앱이 컨테이너 안에서 도는지" 기능 검증엔 충분.)
- 안에서 벤치마크(Ø6.5 원통) 1회 돌려 264 °C 재현 확인 → 네이티브 결과와 일치 검증.

### 단계 3 — environment.py 어댑터 + 앱 연결 (Mac)
- `OpenFOAMLinuxEnv` + `get_environment()` 추가, 앱에서 교체. pytest 통과.

### 단계 4 — GitHub Actions 자동 빌드 (Mac → GitHub)
- 워크플로 추가·push → Actions 탭에서 amd64 이미지가 GHCR에 올라오는지 확인.

### 단계 5 — 회사 PC 적용 (Windows WSL)
- WSL에 Podman 설치: `sudo apt-get install -y podman`.
- GHCR 로그인: `podman login ghcr.io`(GitHub Personal Access Token, 권한 `read:packages`).
- `podman pull ghcr.io/<계정>/natconv-studio:latest`.
- `podman run --rm -p 8501:8501 -v $PWD/cases:/app/cases ghcr.io/<계정>/natconv-studio`.
- 윈도우 브라우저 `localhost:8501` → 벤치마크 1회 돌려 264 °C 재현 확인(= dev=prod 일치 최종 검증).

### 단계 6 — 문서화
- `docs/deploy-windows.md`(초보용 설치·실행 안내) 작성. REQUIREMENTS.md에 배포 방식 반영.

---

## 6. 성공 기준

1. GitHub Actions가 amd64 이미지를 GHCR에 자동 빌드·게시.
2. 회사 PC(WSL+Podman)에서 `podman pull` + `podman run`만으로 Streamlit이 뜨고 브라우저 접속.
3. 회사 PC 컨테이너에서 **벤치마크(Ø6.5 원통, 8500 W/m²) 표면온도 ≈ 265 °C** 재현(Mac과 일치).
4. Docker Desktop 전혀 미사용(Podman만).

---

## 7. 오프라인 대안 (회사 PC가 ghcr.io 접속 불가 시)

- 인터넷 되는 **amd64 리눅스 PC**(또는 GitHub Actions 산출물 다운로드)에서 이미지를 tar로 저장:
  `podman save -o natconv-amd64.tar ghcr.io/<계정>/natconv-studio:latest`
- USB/사내망으로 회사 PC에 복사 후: `podman load -i natconv-amd64.tar` → 이후 `podman run` 동일.
- ※ arm64 Mac에서 만든 tar는 회사 amd64에서 안 돎 → 반드시 amd64에서 빌드/저장.

---

## 8. 주의/리스크

- **버전 일치**: 컨테이너 OpenFOAM을 Mac과 같은 v2606으로. 공식 이미지에 해당 태그가 없으면 openfoam.com apt로 설치하거나 가장 가까운 ESI 버전 사용(차이 명시).
- **아키텍처**: 반드시 amd64 이미지를 회사 PC에 제공(GitHub Actions가 처리).
- **메모리/성능**: WSL에 할당된 코어·메모리가 솔버 속도를 좌우. `.wslconfig`로 조정 가능.
- **GHCR 권한**: 처음엔 이미지가 private일 수 있음 → public으로 바꾸거나 `podman login` 토큰 사용.
- **베이스 이미지 라이센스**: OpenFOAM(GPL)·Podman(Apache2)·Ubuntu 모두 무료. Docker Desktop만 회피.

---

## 9. 다음 단계

이 계획 승인 시, 위 단계 1~6을 TDD 기반 상세 구현 계획으로 분해(writing-plans)하여 실행한다.
Phase 2A(완료) 이후의 인프라 작업이며, Phase 2B(결합 해석)와는 독립적으로 진행 가능.
