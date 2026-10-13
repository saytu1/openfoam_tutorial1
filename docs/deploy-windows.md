# 회사 PC(Windows + WSL) 설치·실행 가이드

natconv-studio를 회사 윈도우 PC에서 돌리는 방법입니다. **완전 초보 기준**으로,
명령을 위에서 아래로 그대로 따라 하면 됩니다.

## 큰 그림

```
개발(Mac) ──git push──▶ GitHub ──Actions(클라우드, amd64 빌드)──▶ GHCR(이미지 저장소)
                                                                      │
                                               회사 PC(WSL+Podman) ──pull──┘ → 실행
```

- 회사 PC는 **직접 빌드하지 않습니다.** GitHub가 amd64 이미지를 미리 만들어 두면,
  회사 PC는 그 이미지를 **내려받아(pull) 실행(run)만** 합니다.
- Docker Desktop은 필요 없습니다. **Podman(무료)** 만 씁니다.
- OpenFOAM은 이미지 안에 들어 있으므로, 회사 PC에 OpenFOAM을 따로 설치하지 않습니다.

---

## 0. 사전 준비 (한 번만)

### 0-1. WSL + Ubuntu 확인
윈도우 **PowerShell**에서:
```powershell
wsl -l -v
```
`Ubuntu` 가 보이고 상태가 `Running`/`Stopped`면 OK. 없으면 `wsl --install -d Ubuntu`.

이후 모든 명령은 **Ubuntu(WSL) 터미널**에서 실행합니다. (시작 메뉴 → "Ubuntu")

### 0-2. Podman 설치 (WSL Ubuntu 안에서)
```bash
sudo apt-get update
sudo apt-get install -y podman
podman --version        # 버전이 찍히면 성공
```

---

## 1. GHCR 로그인 (한 번만)

저장소가 **비공개(private)** 라서 이미지도 비공개입니다. 받으려면 토큰으로 1회 로그인해야 합니다.

### 1-1. GitHub 토큰 발급
GitHub → 우측 상단 프로필 → **Settings → Developer settings →
Personal access tokens → Tokens (classic) → Generate new token (classic)**
- 권한(Scopes)에서 **`read:packages`** 만 체크
- 생성된 토큰 문자열(`ghp_...`)을 복사 (한 번만 보입니다)

### 1-2. 로그인
WSL Ubuntu에서 (`<GitHub사용자명>` = `saytu1`):
```bash
echo '복사한_토큰_ghp_xxx' | podman login ghcr.io -u saytu1 --password-stdin
```
`Login Succeeded` 가 뜨면 끝. (로그인 정보는 저장되어 재부팅해도 유지)

---

## 2. 이미지 내려받기

```bash
podman pull ghcr.io/saytu1/openfoam_tutorial1:latest
```

> 개발자가 Mac에서 코드를 고쳐 push하면 GitHub가 새 이미지를 만듭니다.
> 최신본을 쓰려면 위 `pull` 을 다시 실행하면 됩니다(§6 업데이트 참고).

---

## 3. 실행

```bash
# 결과 케이스를 윈도우에서도 보존하려면 작업 폴더를 하나 정해 둡니다.
mkdir -p ~/natconv-cases

podman run --rm \
  -p 8501:8501 \
  -v ~/natconv-cases:/app/cases \
  ghcr.io/saytu1/openfoam_tutorial1:latest
```

- `-p 8501:8501` : 웹 접속 포트
- `-v ~/natconv-cases:/app/cases` : 해석 케이스/결과를 WSL 디스크에 남김 (컨테이너를 꺼도 유지)
- `--rm` : 종료 시 컨테이너 자동 정리 (이미지와 케이스는 그대로 남음)

터미널에 `You can now view your Streamlit app ... http://0.0.0.0:8501` 이 뜨면 준비 완료.

---

## 4. 브라우저로 접속

윈도우의 크롬/엣지 주소창에:
```
http://localhost:8501
```
WSL2는 localhost가 윈도우와 공유되므로 보통 바로 열립니다.
안 열리면 §7 문제해결을 보세요.

**종료:** 실행 중인 WSL 터미널에서 `Ctrl + C`.

---

## 5. 결과 파일 위치

- WSL 안: `~/natconv-cases/`
- 윈도우 탐색기에서 보려면 주소창에: `\\wsl$\Ubuntu\home\<사용자명>\natconv-cases`

---

## 6. 업데이트 (개발자가 코드를 고친 뒤)

```bash
podman pull ghcr.io/saytu1/openfoam_tutorial1:latest   # 최신 이미지 받기
# 그 다음 §3 run 을 다시 실행
```
`pull` 이 `Already up to date` 면 새 버전이 없는 것입니다.

---

## 7. 문제 해결

| 증상 | 조치 |
|------|------|
| `podman login` 실패(denied) | 토큰에 `read:packages` 권한이 있는지, 사용자명이 `saytu1`인지 확인 |
| `pull` 이 `manifest unknown` | 아직 GitHub Actions 빌드가 끝나지 않음. GitHub → **Actions** 탭에서 `build-image` 성공(초록 체크) 확인 후 재시도 |
| 브라우저에서 `localhost:8501` 안 열림 | WSL 터미널에서 `ip addr show eth0` 의 inet 주소(예 `172.x.x.x`)로 `http://172.x.x.x:8501` 접속 |
| 포트 충돌(8501 사용 중) | `-p 8502:8501` 로 바꿔 실행 후 `http://localhost:8502` |
| 해석이 오래 걸림 | 정상입니다. 메시/솔버 진행은 앱 화면의 로그/진행탭에서 확인 |

---

## 참고: 아키텍처

- 개발 Mac = arm64, 회사 PC = amd64 로 CPU 계열이 다릅니다.
- 그래서 **회사 PC용 amd64 이미지는 GitHub Actions(클라우드 amd64)가 빌드**합니다.
  회사 PC는 맞는 이미지를 받기만 하므로 아키텍처를 신경 쓸 필요가 없습니다.
- 전체 설계 배경: [`containerization-plan.md`](containerization-plan.md)
