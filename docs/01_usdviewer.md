# MapTool 맵파일 → USD → usdview 뷰어 (노트북 PoC)

## 목표 (이번 작업 범위 — 딱 이것만)
- MapTool 맵파일을 읽어서 **USD 파일로 변환**한다.
- 변환한 USD를 **usdview**로 띄워서 레일 + port가 제대로 보이는지 확인한다.
- **노트북 환경**이라 GPU 부담을 최소화한다 → 무거운 Omniverse(Kit/RTX) 안 씀. `usd-core` + usdview만 사용.
- 효율을 위해 **`UsdGeom.PointInstancer`(= Three.js InstancedMesh 대응)** 로 그린다. 인스턴싱 안 하면 노트북에서 못 띄우는 규모이므로 인스턴싱은 필수.

## 명시적으로 범위 밖 (이번엔 안 한다)
- 차량 움직임 / 실시간 시뮬레이션 ❌
- MQTT, FastAPI, 데이터 연동 ❌
- Omniverse Kit / RTX 렌더 / 웹뷰 스트리밍 ❌
- 차량(vehicle) 표현 ❌ — 이번엔 **레일과 port만**.
- 화려한 Material/PBR ❌ — 형상만 보이면 됨.

## 배경 (작업자 컨텍스트)
- 작업자는 Three.js/React/WebGL로 대규모 AMHS 플릿 시뮬레이터(VPS)를 만든 경험이 있음. InstancedMesh, BufferGeometry, 씬 그래프, 트랜스폼 멘탈 모델 보유.
- 따라서 이 작업은 **개념 학습이 아니라 "Three.js → USD 문법 번역"**이다. 설명은 Three.js 대응 개념으로 매핑해주면 빠르게 이해함.
- USD/usdview는 처음 만짐. API 이름과 문법만 새로움.

## Three.js → USD 매핑 (참고)
| Three.js | USD |
|---|---|
| `THREE.InstancedMesh` + `setMatrixAt(i, m)` | `UsdGeom.PointInstancer` (`positions`, `orientations`, `scales`, `protoIndices`) |
| `THREE.BufferGeometry` (단일 메쉬) | `UsdGeom.Mesh` (`points`, `faceVertexCounts`, `faceVertexIndices`) |
| 곡선 (점들 사이 보간) | `UsdGeom.BasisCurves` (컨트롤 포인트 주면 USD가 보간) |
| `mesh.position` / `quaternion` | `UsdGeom.Xformable` translate / orient op |
| `requestAnimationFrame` 루프 | (이번 범위 밖) |

## 환경 / 제약
- OS: (Windows / 기타 — 채워넣기)
- Python: 시스템 파이썬 사용 (Omniverse 임베디드 파이썬 아님)
- 핵심 의존성: `usd-core` (pip). 이거 하나면 USD 생성 + usdview 둘 다 됨. Omniverse 설치 불필요.
- GPU: 노트북 (약함 가정) → usdview는 Hydra Storm(래스터)으로 가볍게 뜸. 인스턴싱 필수.

## 좌표계 주의 (Three.js 출신이라 헷갈리는 지점)
- Three.js: 기본 **Y-up**
- USD: 기본 **Z-up** (stage upAxis 설정 가능)
- 맵파일 좌표가 평면(예: x,y)이면 USD에서 어느 축에 매핑할지 처음에 결정하고 일관되게 갈 것.
- `metersPerUnit`도 명시 (맵 단위가 mm냐 m냐).

## 맵파일 포맷 (y_short, MapTool v5.0.4 출력)

- 맵파일 경로: `/home/vosui/vosui/vps/public/railConfig/y_short/`
- 맵파일 형식: **MapTool 텍스트 출력 (헤더는 `#` 주석 + CSV 본문)**. 파일 5개로 구성됨.
- 좌표 단위: **미터로 추정** (x 범위 약 0~몇십, y 범위 약 -95 ~ 0, z=3.8 — 레일 천장 높이). MapTool은 평면이 `editor_x`, `editor_y`이고 `editor_z`는 고도. ⚠️ **`editor_y`가 음수**라는 점 주의 — Three.js 씬에서는 그대로 깔았었음. USD 변환 시 `Y-up` 그대로 가도 되고, Z-up으로 돌리려면 `(x, -y, z)` 같은 변환을 명시적으로 결정할 것.

### 파일 구성 (5개)

#### 1) `nodes.cfg` — 노드 (2743 lines, 헤더 5줄 주석)
헤더: `node_name,barcode,editor_x,editor_y,editor_z`
```
N0001,470,2.325,-0.47,3.8
N0002,53690,2.325,-53.691,3.8
```
- **N-노드** (`N0001`~): 약 **658개** — 그래프 노드 (엣지의 from/to).
- **TMP-노드** (`TMP_FROM_N_Exxxx`, `TMP_TO_N_Exxxx`): 약 **2075개** — 각 엣지의 곡선/직선 **컨트롤 포인트**. 엣지 1개당 보통 2개씩 들어감.
  - 예: `TMP_FROM_N_E0005,-1,2.325,-95.888,3.8` (barcode = -1 → 실제 노드 아님)
- 총 라인 = 658 + 2075 = 2733 (+헤더 10줄 ≈ 2743 OK)

#### 2) `edges.cfg` — 엣지/세그먼트 (875 lines, 헤더 1줄)
헤더: `edge_name,from_node,to_node,distance,vos_rail_type,bay_name,waypoints,radius,waiting_offset`
```
E0001,N0001,N0002,53.221,LINEAR,BAY26,"[N0001, TMP_FROM_N_E0002, TMP_TO_N_E0002, N0002]",-1.0,-1
E0004,N0004,N0005,2.511,CURVE_180,BAY26,"[N0004, TMP_FROM_N_E0005, TMP_TO_N_E0005, N0005]",0.5,-1
```
- **총 874개 엣지**.
- `waypoints` = 4개 노드명 리스트 `[from, TMP_FROM, TMP_TO, to]` — 곡선 형상의 컨트롤 포인트 4개.
- `vos_rail_type` 분포:
  | type | 개수 | 의미 |
  |---|---|---|
  | LINEAR | 501 | 직선 |
  | CURVE_90 | 257 | 90도 회전 |
  | S_CURVE | 66 | S자 |
  | CURVE_180 | 36 | 180도 U턴 |
  | CURVE_CSC | 14 | C-S-C 복합 |
- `radius`: 곡선의 반경 (직선이면 -1.0)
- `distance`: 엣지 길이 (m)

#### 3) `station.map` — 포트 (4356 lines, 헤더 5줄 주석 + 1줄 컬럼)
헤더: `station_name,editor_x,editor_y,barcode_x,barcode_y,barcode_r,bay_name,station_type,nearest_edge,nearest_edge_distance`
```
100001,5.196,-93.296,860652,100,90,BAY26,OHB,E0089,0.5083
```
- **총 약 4350개 station(=port)**.
- `station_type` 분포:
  | type | 개수 | 의미 |
  |---|---|---|
  | OHB | 2836 | Overhead Buffer (대다수) |
  | EQ | 1489 | 장비 포트 |
  | STK | 24 | Stocker |
- 위치: `editor_x`, `editor_y` (평면) — z는 없음. 레일 아래 매달리거나 가까이 붙는 형태.
- `barcode_r`: barcode 회전각 (degree, 보통 90).
- `nearest_edge`: 어느 엣지에 매달려 있는지.

#### 4) `loops.map` — 베이 그룹 (29 lines)
```
BAY01 [E0255 E0542]
BAY02 [E0246 E0531]
```
- BAY 단위로 엣지 묶음. USD 변환 시 **꼭 필요 없음** (시각화 목적이면 skip 가능, 색상 구분에는 활용 가능).

#### 5) `vehicles.cfg` — 차량 초기 배치
- 이번 범위 **밖** (vehicle 표현 안 함). 무시.

### 곡선 표현 방식 (중요)
- waypoints 4점이 컨트롤 포인트처럼 보이지만, **VPS 본진 로직에서는 곡선 타입(`vos_rail_type`)과 `radius`를 보고 직접 곡선을 생성**하는 것으로 추정. (waypoints의 TMP 점은 곡선 시작/끝 지점이고, 사이는 radius와 type으로 보간.)
- USD 변환 옵션:
  1. **간단**: `from_node`, `to_node` 두 점만 잇는 직선으로 일단 그리기 (곡선 무시) → 형상 확인용 1차 PoC.
  2. **중간**: TMP 포함 4점 waypoint를 그대로 `UsdGeom.BasisCurves`에 넘겨서 보간.
  3. **정확**: VPS의 곡선 생성 로직 (`src/common/...` 또는 `src/shmSimulator/`에서 EWMA/곡선 보간 부분) 포팅해서 폴리라인 생성 후 세그먼트 인스턴싱.
- **권장**: 1번부터 해서 형상이 보이는지 먼저 확인 → 2번으로 곡선 모양 살리기 → 3번은 본진 통합 단계에서.

### 대략 규모
- 레일 N-노드: **658개**
- TMP 컨트롤 포인트: **2075개**
- 엣지: **874개** (LINEAR 501 + 곡선 373)
- 포트(station): **약 4350개**
- → 노트북 usdview에서 `UsdGeom.PointInstancer`로 그리면 무난한 규모. (포트 4350개 박스 인스턴싱 + 엣지 874개 곡선 정도)

## 작업 순서 (단계별 검증 — 한 번에 다 붙이지 말 것)
1. **환경 셋업**: `pip install usd-core`. `usdview` 실행되는지 확인 (빈 usd 파일이라도 열어봄).
2. **최소 USD 생성 테스트**: 박스 프로토타입 1개를 PointInstancer로 위치 몇 개에 찍어서 `.usda`(텍스트 포맷) 생성 → usdview로 열어 인스턴싱 보이는지 확인.
3. **맵파일 파서**: 맵파일 읽어서 (레일 세그먼트 위치/회전/길이 배열) + (port 위치/크기/회전 배열) 파이썬 자료구조로 추출.
4. **port 인스턴싱**: port 박스 프로토타입 + PointInstancer로 모든 port 배치.
5. **레일 인스턴싱**: 짧은 직선 세그먼트를 프로토타입으로 잡고, 각 세그먼트의 위치/회전/스케일을 인스턴스로 → 곡선을 세그먼트 인스턴스들로 표현. (인스턴싱 효율 확인이 목적이므로 BasisCurves 대신 세그먼트 인스턴싱 권장. 단 BasisCurves가 더 간단하면 그것도 OK — 판단해서 제안)
6. **전체 맵 USD 생성** → usdview로 열어서: (a) 형상이 맞는지 (b) 수천~수만 개에서 인스턴싱으로 가볍게 도는지 확인.

## 산출물
- `convert_map_to_usd.py` — 맵파일 → USD 변환 스크립트
- `out/map.usda` (또는 `.usd`) — 생성된 USD 파일
- usdview로 열어서 확인

## 검증 기준 (이게 되면 이번 작업 끝)
- usdview에서 맵(레일 + port)이 형상대로 보인다.
- 노트북에서 인스턴싱으로 버벅임 없이 뜬다 (InstancedMesh처럼 효율적인지 확인).
- 만든 USD 파일은 나중에 본진 Omniverse에서 그대로 열 수 있다 (호환 확인은 나중).

## 작업자 노트
- 이번 USD 파일은 **재사용 자산**이다. 노트북 usdview에서 잘 만들어두면 나중에 본진 GPU의 Omniverse에서 같은 파일을 RTX 뷰어로 열어 화려하게 띄울 수 있다. 작업 두 번 안 하도록 USD 구조를 깔끔하게.
- 텍스트 USD(`.usda`)로 먼저 만들면 사람이 열어서 디버깅하기 쉬움. 규모 커지면 `.usd`(바이너리)로.
