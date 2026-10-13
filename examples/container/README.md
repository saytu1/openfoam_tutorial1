# 컨테이너 설정 예시 (초안)

이 폴더는 **"예시(초안)"** 입니다. 지금 이 위치(`examples/container/`)에 있는 동안은
아무것도 자동으로 실행되지 않습니다. 개념을 먼저 눈으로 보고, 준비가 되면 아래 안내대로
"실제 위치"로 옮기면 됩니다.

전체 배경 설명은 [`docs/containerization-plan.md`](../../docs/containerization-plan.md) 를 보세요.

---

## 왜 컨테이너인가 (한 줄 요약)

개발은 **Mac(arm64)**, 실제 사용은 **회사 윈도우 PC(WSL, amd64)** 라 환경이 다릅니다.
컨테이너로 "OpenFOAM + 파이썬 + 앱"을 하나로 묶으면 두 곳에서 **똑같이** 돌아갑니다.
회사 PC는 Docker Desktop을 못 깔지만 **Podman(무료)** 으로 같은 이미지를 실행할 수 있습니다.

```
Mac(개발) ──push──▶ GitHub ──Actions(클라우드, amd64 빌드)──▶ GHCR(이미지 저장소)
                                                                 │
                                           회사 PC(WSL+Podman) ──pull──┘  → 실행
```

---

## 파일 설명

| 파일 | 역할 | 실제 적용 시 옮길 위치 |
|------|------|------------------------|
| `Containerfile` | 이미지 레시피 (OpenFOAM+Python+Streamlit 올인원) | 저장소 **루트** |
| `build-image.yml` | GitHub가 클라우드(amd64)에서 자동 빌드→GHCR 게시 | `.github/workflows/build-image.yml` |

> `build-image.yml` 을 `.github/workflows/` 로 옮기는 순간부터 `main` 에 push할 때마다
> 실제 빌드가 돌아갑니다. 그래서 지금은 일부러 `examples/` 에 두었습니다.

---

## 실제로 적용하는 순서 (준비되면)

1. **코어 코드 보완** — `natconv/environment.py` 에 리눅스용 어댑터(`OpenFOAMLinuxEnv`)와
   `get_environment()` 추가 (환경변수 `NATCONV_ENV=linux` 이면 리눅스 어댑터 선택).
2. `Containerfile` 을 저장소 루트로 복사하고 ⚠️ 주석의 확인 항목(베이스 이미지 태그·`FOAM_BASHRC` 경로)을 점검.
3. `build-image.yml` 을 `.github/workflows/build-image.yml` 로 복사.
4. `main` 에 push → GitHub Actions 탭에서 빌드 성공 확인 → GHCR에 이미지 게시됨.
5. 회사 PC(WSL)에서:
   ```bash
   podman login ghcr.io              # GitHub 토큰으로 1회 로그인
   podman pull ghcr.io/saytu1/openfoam_tutorial1:latest
   podman run --rm -p 8501:8501 -v "$PWD/cases:/app/cases" ghcr.io/saytu1/openfoam_tutorial1:latest
   # 브라우저에서 http://localhost:8501
   ```

---

## 로컬(Mac)에서 바로 빌드·테스트 해보고 싶다면

```bash
# 저장소 루트에서
podman build -t openfoam_tutorial1 -f examples/container/Containerfile .
podman run --rm -p 8501:8501 -v "$PWD/cases:/app/cases" openfoam_tutorial1
```

> Mac에서 빌드하면 arm64 이미지가 됩니다. 회사 PC(amd64)용은 GitHub Actions가 만들어 주므로
> 아키텍처 걱정 없이 `pull` 만 하면 됩니다.
