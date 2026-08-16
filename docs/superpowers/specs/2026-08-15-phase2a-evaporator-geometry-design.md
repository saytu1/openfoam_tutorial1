# Phase 2A — 히터 + 증발기 형상·메시 설계 스펙

작성일: 2026-08-15 (형상 확정 갱신)
상태: 형상 확정·시각 검증 완료 (구현 계획 대기)
선행: natconv-studio v1.0.0 (단독 히터 자연대류+복사, 표면온도 264 °C 검증)

## 1. 배경 / 목적 (Context)

Phase 1은 25 °C 밀폐 인클로저 안 단독 수평 원통 히터(Ø6.5 mm)를 자연대류+복사로 풀었다.
Phase 2의 최종 목표는 **히터 위에 냉장고 증발기를 배치해 함께 열해석하고 제상 소요 시간을 예측**하는 것.
전체 Phase 2는 3단계로 분해한다.

- **2A (이 스펙)**: 히터 + 증발기 **형상·메시**를 만든다. 해석(BC/솔버)은 하지 않는다.
- 2B: 히터↔증발기 정상 결합 열해석(복사+대류, 핀은 thermalBaffle1D). 별도 스펙.
- 2C: 2B 열전달 + 서리 융해(잠열) 준정상 과도 모델로 제상 시간 산출. 별도 스펙.

**2A의 산출물**: 히터·튜브·핀(baffle)이 배치된, checkMesh를 통과하는 케이스 메시 + 이를
파라미터로 편집하는 GUI "증발기" 탭.

## 2. 범위

**목표(2A)**
- 증발기 튜브(실제 원통) + 핀(두께 0 baffle) + 히터를 포함한 형상 생성
- snappyHexMesh로 표면정합 + baffle 핀 삽입, checkMesh 통과
- 증발기 치수를 편집하는 GUI 탭
- 구조 모델·메시 시각화로 배치 확인

**비목표(2A → 2B/2C로 이월)**
- 증발기/핀의 열 경계조건, 솔버 실행, 열전달 결과
- 서리·융해·제상 시간
- 튜브 곡관(serpentine bend) — 직관 다발로 근사

## 3. 확정 치수 (기본값, 모두 파라미터)

**좌표 규약**: **x = 폭(튜브·히터 축, 600 mm)**, **y = 높이(연직, 중력 −y)**, **z = 깊이(60 mm)**.
원점은 증발기 튜브 다발 중심. (Phase 1의 z축 히터와 달리 Phase 2 히터·튜브는 **x축**으로 길다.)

### 증발기 (독립 구조체)

| 항목 | 기본값 |
|---|---|
| 튜브 외경 D_t | 8 mm |
| 튜브 배열 | **2열(z) × 6단(y) = 12개**, inline, **직관(U밴드 없음)** |
| 튜브 피치 | 수직(y) 30 mm / 깊이(z) 30 mm → 열 위치 z=±15 |
| 튜브 길이·축 | x축 600 mm 직관 |
| 핀 크기 | **각 단 중심에 30(높이 y) × 60(깊이 z)** — z=60은 두 열(z=±15) 모두 덮음 |
| 핀 피치·개수 | 폭(x)방향 8 mm 간격 → 약 76장 |
| 핀 두께 | 0.15 mm (baffle 값으로만, 메시는 두께 0) |
| 증발기 외형 W×H×D | 600 × 180 × 60 mm |

### 히터 (독립 구조체 — 증발기와 절대 미연결)

| 항목 | 기본값 |
|---|---|
| 형상 | Ø6.5 mm, **2열(z=±15) + 오른쪽(+x) U밴드 = U자 hairpin** |
| 직선부 길이 | 각 다리 600 mm (x축) |
| U밴드 | 반경 15 mm(열피치/2), 반원 ≈ 47 mm |
| **총 히터 길이** | **≈ 1,247 mm** (직선 600×2 + U밴드 47, **모든 열·굽힘 포함**) |
| 표면적 | ≈ π × 6.5 × 1247 ≈ 255 cm² (Phase 1의 약 12배) |
| 위치 | 증발기 최하단 튜브에서 아래로 30 mm, 수평 중앙 |

### 인클로저

| 항목 | 기본값 |
|---|---|
| 도메인 | 전체 바운딩박스(증발기+히터) × enclosure_factor 밀폐 박스 |

> **★ 핵심 규칙**: 히터와 증발기는 **완전히 별개의 구조체**로, 서로 연결되지 않는다.
> U밴드는 **히터에만** 있고(2열 연결), 증발기 튜브는 직관 12개(연결 없음). 코드·patch도 분리.
> **히터 길이 보고 시 항상 모든 열·U밴드 포함한 총 길이로 표기.**

## 4. 설계

### 4-1. 형상 생성 (`geometry.py`) — x축 규약, 히터/증발기 분리

- `write_tube_bank_stl(path, D_t, n_rows, n_cols, pitch_v, pitch_z, length, ...)`:
  x축 직관 원통을 2열(z=±pitch_z/2) × 6단(y) 격자로 배치한 STL(solid=tubes). U밴드 없음.
- `write_fins_stl(path, fin_h, fin_z, pitch_x, x_range, rows_y)`: 각 단(y) 중심에 놓인
  30(y)×60(z) 사각 핀을 x방향 pitch_x(8mm) 간격으로 배치한 STL(solid=fins). 각 핀 두께 0.
- `write_heater_hairpin_stl(path, D_h, leg_len, z_cols, ubend_R, y)`: 2열 직관 + 오른쪽 U밴드
  (반원 스윕)로 U자 hairpin STL(solid=heater). 총 길이 = 다리×2 + πR.
- 세 STL을 각각 `constant/triSurface/{tubes,fins,heater}.stl`로 저장 → snappy에서 별도 patch.

### 4-2. 메시 (`case_builder` + 템플릿)

- blockMesh 배경 박스: 전체 바운딩박스(히터+증발기) × enclosure_factor, 격자수 상한.
- snappyHexMesh:
  - `refinementSurfaces`: heater(wall), tubes(wall) — 표면정합·레이어.
  - `fins`: **`faceZone` + `faceType baffle`** (또는 `cellZone none` + baffle) → 두께 0 내부 면.
  - `locationInMesh`는 유체 점(형상 바깥).
- `createBaffles`(필요 시)로 fins faceZone을 실제 baffle patch 쌍으로 분리.
- 검증 참조: `$FOAM_TUTORIALS/heatTransfer/buoyantSimpleFoam/circuitBoardCooling`(동일 솔버 baffle 예제).

### 4-3. 파라미터 (`params.py`)

- 새 데이터클래스 `Evaporator`:
  `D_t, n_rows(6), n_cols(2), pitch_y(30), pitch_z(30), tube_len(600),
   fin_h(30), fin_z(60), fin_pitch_x(8), fin_thickness(0.15), heater_gap(30)`.
- 히터 hairpin 파라미터: `heater_leg_len(600), heater_cols(2), heater_col_pitch(30)`.
- `Params`에 선택적 `evaporator: Evaporator | None` 추가(None이면 Phase 1 단독 히터 = 하위호환).

### 4-4. GUI (`app`)

- 새 입력 섹션/탭 **"🧊 증발기"**: 위 Evaporator 필드를 mm 단위로 편집(단위 환산 규칙 재사용),
  각 항목 tooltip. "증발기 포함" 체크박스로 Phase 1(단독)과 전환.
- 구조 모델·메시 시각화 탭이 튜브+핀+히터를 함께 렌더(postprocess에 다중 STL 지원 추가).

### 4-5. 데이터 흐름

```
[증발기 탭(mm)] → Evaporator(SI) → geometry: tubes/fins/heater STL
   → case_builder: 배경 메시 + snappy(튜브 wall + 핀 baffle) → checkMesh
   → postprocess: 구조·메시 시각화
```

## 5. 성공 기준

1. `checkMesh` 통과(음체적/과왜곡 없음).
2. `tubes` patch 존재, 표면적 ≈ 12 × π D_t × tube_len (±5 %).
3. `fins`가 **baffle(두께 0 내부 면)** 으로 생성됨(faceZone/patch 확인), 장수 = x범위/핀피치(≈76).
4. `heater` patch 존재, 전개 길이 ≈ 1,247 mm (다리×2 + U밴드), 증발기 아래 30 mm 위치.
5. 히터·증발기가 **별도 patch**로 분리됨(혼합 없음).
6. 코어 pytest: geometry(튜브 12개·면적·핀 장수·히터 총길이), params(Evaporator 검증) 통과.

## 6. 테스트 (pytest, 코어)

- `test_geometry`: `write_tube_bank_stl`이 n_rows×n_cols개 원통·총면적 생성; `write_fins_stl`이
  올바른 장수·간격 생성.
- `test_params`: Evaporator 필드 검증(양수·개수 ≥1·핀피치>두께).
- 메시(snappy/createBaffles)는 통합 검증(실행)으로 확인(실제 OpenFOAM 필요).

## 7. 리스크 / 주의

- baffle 핀 + 튜브 다발 snappy 메시는 까다로울 수 있음 → 표준 refinement/layer, 필요 시 핀 장수·
  refinement 단계적 상향.
- 핀 두께 0 baffle의 열전도는 2B의 `thermalBaffle1D`에서 처리(2A는 면 생성까지).
- 튜브 곡관 생략(직관 근사) — 열전달 결과에 영향은 2B에서 평가.

## 8. 다음 단계

2A 메시 검증 후 → 2B(정상 결합 열해석) 스펙: 튜브 벽 온도/열유속 BC, 핀 thermalBaffle1D,
히터↔증발기 복사(fvDOM), 증발기로의 열유속·분포 산출.
