# natconv-studio — 설계 문서 (Design Spec)

작성일: 2026-07-05
상태: 설계 승인됨 (구현 계획 대기)

## 1. 배경 / 목적 (Context)

OpenFOAM으로 **자연대류 + 복사** 열전달 표면온도 해석을 수행하는 **Streamlit GUI 도구**를 만든다.
앞서 냉장고 제상 히터(Ø6.5 mm 수평 원통, 8500 W/m², ε0.95, 25 °C) 해석을 Mac(ESI v2606)에서
완료·검증했고(표면온도 265 °C), 그 과정을 파라미터화해 **다양한 형상·열조건의 자연대류 해석을
GUI에서 직접 실행·시각화**할 수 있게 하는 것이 목표다.

사용자는 매번 dict를 손으로 고치는 대신, 형상·열조건 파라미터를 입력하고 버튼 하나로
케이스 생성 → 메시 → 솔버 → 결과 시각화까지 진행하며, 실행 상태를 실시간으로 본다.

이 도구는 **지금 Mac 환경(ESI v2606, `openfoam -c`)용으로 먼저 제작**한다. 사무실
(Windows + WSL Ubuntu) 이식은 별도 프롬프트(`사무실_WSL_natconv-studio_구축_프롬프트.md`)로 진행하며,
본 설계의 **환경 추상화 계층** 덕분에 어댑터 교체로 이식된다.

## 2. 목표 / 비목표

**목표(v1)**
- 형상 3종: 수평 원통, 수직 평판, 사용자 STL 업로드
- 열조건: 표면 열유속 / 고정 표면온도 / 총전력, 방사율, 주변온도
- 케이스 자동 생성 → 실행 → **실시간 진행 표시**(수렴·표면온도·단계)
- 결과: 메시 단면, 온도장(단면+플룸), 에너지평형, 표면온도 KPI, 손계산 대비 검증
- 코어 라이브러리는 pytest로 독립 검증

**비목표(v1, YAGNI)**
- 유체 종류 다양화(공기 고정), 난류 모델 선택(laminar 고정), 과도 해석
- 범용 임의 OpenFOAM 케이스 러너, 구(sphere) 형상
- ParaView 연동(선택, matplotlib으로 충분)

## 3. 아키텍처

**원칙: 순수 Python 코어(테스트 가능) + 얇은 Streamlit UI + 환경 추상화.**
코어(`natconv/`)는 Streamlit을 전혀 모른다. UI는 코어를 호출만 한다.

```
natconv-studio/
├── natconv/                  # 코어 (Streamlit 의존성 없음)
│   ├── params.py             # Params 데이터클래스 = 한 해석의 단일 진실 소스
│   ├── geometry.py           # STL 생성(원통·평판) / 업로드 STL 검증
│   ├── templates/            # 검증된 dict 템플릿(플레이스홀더)
│   ├── case_builder.py       # Params → 완전한 케이스 폴더(0/constant/system)
│   ├── environment.py        # OpenFOAM 실행 추상화 (Mac gerlero / WSL 어댑터)
│   ├── runner.py             # 파이프라인 오케스트레이션 + 백그라운드 실행 + 로그
│   ├── logparse.py           # 로그 → 수렴·표면온도·복사 시계열
│   ├── postprocess.py        # 필드(C,T)·polyMesh 파싱 → matplotlib 그림
│   └── energy.py             # 에너지 평형 + 손계산(Churchill–Chu) 검증
├── app/streamlit_app.py      # 얇은 UI: 파라미터 폼 → 실행 → 실시간 모니터 → 결과
├── tests/                    # pytest (코어 단위 테스트)
├── cases/                    # 실행별 생성 케이스(타임스탬프)
├── requirements.txt          # streamlit, numpy, matplotlib
└── README.md
```

**모듈 책임 (단일 책임·독립 인터페이스)**
- `params.py`: 입력 파라미터를 담고 검증(범위·조합 유효성).
- `geometry.py`: Params.geometry → STL 파일. 업로드 STL은 닫힘·바운딩박스 검증.
- `case_builder.py`: 템플릿 + Params → 케이스 폴더. 솔버/딕셔너리 이름은 environment에서 주입.
- `environment.py`: `OpenFOAMEnvironment.run(cmd, cwd) -> 스트리밍 프로세스`. `MacGerleroEnv`는
  `openfoam -c 'cd <cwd> && <cmd>'` 래핑. 솔버명(`buoyantSimpleFoam`)·딕셔너리명(ESI) 제공.
- `runner.py`: 파이프라인 실행·상태 관리(RunState JSON).
- `logparse.py`: 솔버 로그에서 iteration별 표면 T·qr·잔차 추출.
- `postprocess.py`: 결과 필드/메시 파싱 → 그림 (기존 `makeFigures.py` 로직 흡수).
- `energy.py`: 대류·복사 분해, Churchill–Chu 손계산으로 검증.

## 4. Params (단일 진실 소스)

```
geometry : kind(cylinder|plate|stl), dims{D,L | H,W,t}, stl_path, orientation(horizontal|vertical)
heat     : mode(flux|fixedT|power), value, emissivity
ambient  : T_inf(기본 298.15 K), enclosure_factor(기본 20×, 범위 15~30)
fluid    : air (v1 고정: perfectGas + sutherland, Cp 1005)
mesh     : base_cell, refine_level(2~3), n_layers(5)
numerics : endTime, residualControl, n_procs
solver   : (environment 주입) 솔버명 + 딕셔너리명 매핑
```

## 5. 케이스 생성 · BC 전략 (검증된 설정 내장)

- **원방 = 밀폐 등온 인클로저** (형상의 15~30배 상자): `U=noSlip`, `T=fixedValue T_inf`,
  `p_rgh=fixedFluxPressure`. 벽이 열 싱크 + 복사 싱크(ε=1). **개방 경계 금지**(3D 부력 발산 방지).
- 발열 모드 매핑:
  - `flux` → `externalWallHeatFluxTemperature` mode flux + **`qr qr` 커플** + kappaMethod fluidThermo
  - `fixedT` → 형상 표면 `fixedValue T`
  - `power` → mode power, Q = 전력밀도 × 표면적
- 복사: `fvDOM`(nPhi 3, nTheta 5), 공기 흡수 0. ε는 `boundaryRadiationProperties` lookup.
- 난류 laminar, 공기 perfectGas+sutherland.
- 메시: blockMesh(배경) + surfaceFeatureExtract + snappyHexMesh(표면정합, level 2~3, 프리즘 5층).
  **`meshQualityControls`에 `errorReduction 0.75; nSmoothScale 4; relaxed{maxNonOrtho 75;}` 필수**
  (없으면 레이어 단계 FATAL).
- **고체/유체 구분**: `locationInMesh`를 유체 점으로 → 형상 내부 셀 삭제, 표면만 벽 patch(유체 단일영역).
- 도메인 크기는 형상 바운딩박스 × enclosure_factor로 자동 산정.

## 6. 실행 · 실시간 모니터링

- 파이프라인: `makeSTL → blockMesh → surfaceFeatureExtract → snappyHexMesh → checkMesh →
  decomposePar → 솔버(mpirun -np N) → reconstructPar`.
- `runner`가 백그라운드 프로세스로 실행, 각 단계 로그를 케이스 폴더에 기록,
  `RunState`(단계·진행·완료·에러)를 케이스 폴더 JSON에 갱신.
- Streamlit: 실행 시작 → 백그라운드 spawn → `st_autorefresh`(~2–3 s)로 RunState·로그 tail·logparse
  읽어 **단계 표시등 + 실시간 수렴 그래프 + 실시간 표면온도** 갱신. 취소 버튼.

## 7. 시각화 · 결과

- `postprocess`(ParaView 불필요, matplotlib): 메시 단면, 온도장 단면(상단이 뜨거움), 주변 플룸.
- 실시간 수렴 그래프(logparse 시계열).
- 에너지 평형 막대(대류/복사) + KPI(표면 T 평균/최고, 복사 %).
- `energy` 손계산(Churchill–Chu) 대비 검증 표시.
- 케이스 폴더·그림 다운로드.

## 8. 에러 처리

- 각 단계 종료코드 + 로그 `FOAM FATAL`/`bounding`/NaN 스캔 → 실패 시 파이프라인 중단, UI에 로그 꼬리.
- checkMesh 실패는 경고 게이트(특히 업로드 STL). 솔버 발산 감지·보고.
- 밀폐 인클로저로 개방경계 발산은 설계상 예방.

## 9. 테스트 (pytest, 코어만)

- `params`: 범위·조합 검증.
- `case_builder`: 생성 dict가 파싱 가능·핵심 BC(밀폐 인클로저, qr 커플) 존재.
- `geometry`: STL 닫힘·면적이 해석식과 일치.
- `logparse`: 샘플 로그 → 표면 T·잔차 시계열 정확 추출.
- `energy`: 손계산 앵커(≈282 °C, 8500 W/m² 원통) 재현.
- UI(streamlit)는 얇아 단위테스트 제외(수동 검증).

## 10. 이식성 (Mac now / WSL 별도)

- 지금은 `MacGerleroEnv`만 구현(`openfoam -c`). `environment.py` 인터페이스로 실행 방식을 격리.
- 사무실 WSL 이식은 `WslUbuntuEnv`(bash -lc + bashrc source, 경로 처리) 어댑터를 추가하고
  솔버/딕셔너리 이름을 배포판(ESI vs Foundation)에 맞춰 주입하면 됨 — 코어·UI 불변.
- 별도 프롬프트 `사무실_WSL_natconv-studio_구축_프롬프트.md` 참조.

## 11. 성공 기준

1. **기준 벤치마크 재현**: GUI에서 Ø6.5 mm 원통·8500 W/m²·ε0.95·25 °C 실행 →
   표면 평균온도 265 °C(±10 %), 복사 ≈ 48 %, 에너지평형 오차 < 1 %.
2. 파라미터 변경(전력밀도 0.5/1.0 W/cm² 등) 시 물리적으로 타당한 경향(전력↑→온도↑, 비선형).
3. 코어 pytest 전부 통과.
4. 수평 원통·수직 평판·업로드 STL 각각 최소 1회 성공 실행.
