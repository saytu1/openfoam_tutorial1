# Phase 2A — 히터 + 증발기 형상·메시 설계 스펙

작성일: 2026-08-15
상태: 설계 승인됨 (구현 계획 대기)
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

## 3. 표준 치수 (기본값, 모두 파라미터)

| 구분 | 항목 | 기본값 |
|---|---|---|
| 튜브 | 외경 D_t | 8 mm |
| | 배열 | 4단(수직 n_rows) × 3열(수평 n_cols) = 12개, inline |
| | 피치 | 수직 20 mm / 수평 20 mm |
| | 축 | z 방향(히터와 평행), 길이 = 핀 깊이 |
| 핀 | 피치 | 8 mm (→ z 범위/피치 = 핀 장수) |
| | 두께 | 0.15 mm (baffle 값으로만 사용, 메시는 두께 0) |
| | 크기 | 폭 70 × 높이 80 mm (x-y 평면) |
| 증발기 전체 | W×H×D | 70 × 80 × 100 mm |
| 히터 | 형상 | Ø6.5 mm 원통(Phase 1) |
| | 위치 | 증발기 최하단 튜브에서 아래로 30 mm, 수평 중앙 |
| 인클로저 | 도메인 | 전체 바운딩박스 × enclosure_factor 밀폐 박스 |

좌표 규약: x=수평, y=연직(중력 −y), z=튜브 축(=히터 축). 원점은 증발기+히터 묶음 중심 근처.

## 4. 설계

### 4-1. 형상 생성 (`geometry.py`)

- `write_tube_bank_stl(path, D_t, n_rows, n_cols, pitch_v, pitch_h, length, y_center)`:
  기존 `write_cylinder_stl` 로직을 재사용해 격자 배열로 튜브 원통들을 하나의 STL(solid=tubes)로 생성.
- `write_fins_stl(path, W, H, pitch, z_range)`: x-y 평면 사각 핀들을 z를 따라 pitch 간격으로
  배치한 STL(solid=fins). 각 핀은 4점 사각형 2삼각형(두께 0).
- 히터는 기존 `write_cylinder_stl` 재사용, 위치 오프셋만 적용.
- 세 STL을 각각 `constant/triSurface/{tubes,fins,heater}.stl`로 저장.

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
  `D_t, n_rows, n_cols, pitch_v, pitch_h, fin_pitch, fin_thickness, W, H, depth, heater_gap`.
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
2. 튜브 patch 존재, 표면적 ≈ n_tubes × π D_t L (±5 %).
3. 핀이 **baffle(두께 0 내부 면)** 으로 생성됨(faceZone/patch 확인), 장수 = z범위/핀피치.
4. 히터가 증발기 아래 지정 간격에 위치(구조 모델 시각화로 확인).
5. 코어 pytest: geometry(튜브 개수·면적·핀 장수), params(Evaporator 검증) 통과.

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
