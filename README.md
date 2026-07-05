# natconv-studio

OpenFOAM으로 **자연대류 + 복사** 표면온도 해석을 파라미터 입력 → 실행 → 실시간 시각화하는
Streamlit GUI 도구.

- 형상: 수평 원통 · 수직 평판 · 사용자 STL 업로드
- 열조건: 표면 열유속 / 고정 표면온도 / 총전력, 방사율, 주변온도
- 검증된 설정 내장: 밀폐 등온 인클로저 · fvDOM 복사 · qr 커플 · snappy 레이어 품질 수정

## 설치 (macOS, Apple Silicon)

```sh
# OpenFOAM (최초 1회)
brew trust gerlero/openfoam && brew install --cask gerlero/openfoam/openfoam
# 파이썬 환경
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## 실행

```sh
.venv/bin/streamlit run app/streamlit_app.py
```

## 테스트

```sh
.venv/bin/pytest -q
```

설계·계획: `docs/superpowers/specs/`, `docs/superpowers/plans/`.
