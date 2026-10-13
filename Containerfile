# natconv-studio 컨테이너 — OpenFOAM v2606 + Python + Streamlit 올인원
# ─────────────────────────────────────────────────────────────────────
# 베이스는 Mac 개발환경과 "같은 제공자(gerlero)"의 OpenFOAM v2606 리눅스 이미지.
#  - ENTRYPOINT(/openfoam/run)가 OpenFOAM 환경을 자동 로드한 채 CMD를 실행 →
#    Streamlit과 그 자식 프로세스(blockMesh 등)가 FOAM 환경변수를 그대로 상속.
#  - 그래서 bashrc를 따로 source할 필요 없음.
#
# 로컬(Mac arm64) 빌드/실행:
#   podman build -t natconv-studio .
#   podman run --rm -p 8501:8501 -v "$PWD/cases:/app/cases" natconv-studio
#   → 브라우저 http://localhost:8501
# 회사 PC(amd64) 배포는 docs/deploy-windows.md 참고 (GHCR에서 pull).
# ─────────────────────────────────────────────────────────────────────
FROM microfluidica/openfoam:2606

# 베이스는 Ubuntu 24.04 → python3/pip 설치. (루트 사용자로 설치)
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 파이썬 의존성. Ubuntu 24.04는 PEP 668(externally-managed)라서
# 격리된 컨테이너에서는 --break-system-packages 로 시스템에 바로 설치.
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# 앱 코드
COPY natconv/ ./natconv/
COPY app/ ./app/

# 코어가 리눅스(컨테이너) 실행 어댑터를 쓰도록 지정
ENV NATCONV_ENV=linux

EXPOSE 8501

# ENTRYPOINT(/openfoam/run)가 FOAM 환경을 로드한 뒤 아래 CMD를 실행한다.
CMD ["streamlit", "run", "app/streamlit_app.py", \
     "--server.address", "0.0.0.0", "--server.port", "8501"]
