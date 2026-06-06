# 옴니버스 개념정리 — VPS(Three.js) 출신을 위한 매핑

> 이 문서는 "옴니버스가 뭔지", "지금 맵이 바로 뜨는지", "맵 먼저 띄우고 기능 얹는 게 맞는지",
> "Composer 실행법"을 한 번에 정리한 기준 문서다. 코드/진행상황은 `../02_mqtt_demo_plan.md` 참고.

---

## 1. 옴니버스가 뭔데? (네가 아는 걸로 매핑)

| 네가 아는 것 (VPS / 웹) | 옴니버스 |
|---|---|
| **Three.js** (렌더 엔진) | **RTX 렌더러** (NVIDIA GPU 레이트레이싱, 훨씬 사실적) |
| **`.gltf` / 씬 파일** | **`.usd` / `.usda`** (씬 저장 포맷) |
| **브라우저 + React 앱** (Three.js 띄우는 껍데기) | **Kit 앱** (RTX 띄우는 껍데기). GUI 버전이 **Composer** |
| `THREE.InstancedMesh` + `setMatrixAt` | `UsdGeom.PointInstancer` (positions/orientations/scales) |
| `THREE.BufferGeometry` | `UsdGeom.Mesh` (points/faceVertexCounts/faceVertexIndices) |
| 곡선 보간 | `UsdGeom.BasisCurves` (컨트롤 포인트 주면 USD가 보간) |
| `requestAnimationFrame` 루프 | Kit `update_event_stream` (메인 스레드 tick) |

**한 줄 요약:** 옴니버스 = "NVIDIA가 만든 고품질 3D 씬 뷰어/편집기 플랫폼".
씬을 `.usd` 파일로 주고받고, VPS에서 Three.js가 하던 렌더를 GPU 빵빵한 **RTX**가 대신 한다.

### 헷갈리는 종류 구분
- **usdview** = 가벼운 USD 뷰어(래스터, 노트북용). **보기만** 됨. 익스텐션/MQTT/실시간 갱신 ❌
- **Composer (Kit 앱)** = 진짜 옴니버스. RTX 렌더 + 익스텐션 + 실시간 갱신 다 됨.
  → **차량 실시간 렌더는 무조건 여기서.**

### 좌표계 주의 (Three.js 출신이 헷갈리는 지점)
- Three.js 기본 **Y-up** / USD 기본 **Z-up**.
- 이 프로젝트 규약(확정): **Z-up identity** — `editor_x→x, editor_y→y, z=3.8`(레일 높이). 축 안 바꿈.

---

## 2. 지금 맵 바로 나와? → **응, 나온다**

Phase A(맵→USD 변환)가 끝나서 결과물이 이미 있다:

```
out/y_short.usda   ← 맵 전체(레일 874개 + 스테이션 4350개)가 USD로 변환 완료 (~1.4MB)
out/render_*.png   ← 미리뷰 렌더 4장도 이미 뽑힘
```

Composer에서 `File ▸ Open`으로 이 파일 열면 **추가 작업 0으로 바로 뜬다.**
씬 구조: `/World`(Z-up, m) → `/World/Rails`(BasisCurves) + `/World/Stations`(PointInstancer) + `/World/TopCam`.

---

## 3. "맵 띄워놓고 기능 덧붙이는 게 맞아?" → **정석이다**

`02_mqtt_demo_plan.md`가 정확히 그 순서로 짜여 있다:

```
맵 USD 열기 (✅ 이미 됨)
  └→ 그 위에 차량 prim 1개 올려서 sin/cos로 혼자 움직이기   ← STEP 3 (다음)
       └→ MQTT 수신해서 로그만 찍기                          ← STEP 4
            └→ 수신 데이터로 그 prim 움직이기                ← STEP 6
                 └→ VPS 실데이터 연결                         ← STEP 7
```

**왜 맞나:**
- 맵은 "배경(고정 에셋)", 차량은 "그 위에서 움직이는 것". 배경 먼저 깔고 얹는 게 자연스럽다.
- 맵이 떠 있으면 차량 좌표 검증이 **눈으로** 된다 — 차량이 레일 위에 딱 올라가면 좌표 OK,
  옆으로 누우면 Z-up/스케일 문제.
- 한 번에 다 붙이면 어디서 깨졌는지 모른다. 그래서 계획서 핵심 원칙도
  **"수신(MQTT)과 렌더링(prim 갱신)을 절대 한 번에 붙이지 않는다."**

---

## 4. Composer 실행법

커스텀 Composer 앱을 이미 빌드해둠(`my_company.my_usd_composer`). 실행기는 이 `.bat` 하나:

```
C:\dev\kit-app-template\_build\windows-x86_64\release\my_company.my_usd_composer.kit.bat
```

> ⚠️ Windows 전용. WSL 셸에서는 못 돌린다. Windows 탐색기 더블클릭 또는 PowerShell/cmd에서 실행.
> 첫 실행은 셰이더 컴파일로 느림.

### ① 맵만 보기
더블클릭으로 켜고 → `File ▸ Open` → `C:\dev\vps_omniverse\out\y_short.usda`

### ② 차량 익스텐션까지 물려서 켜기 (STEP 3~)
```bat
C:\dev\kit-app-template\_build\windows-x86_64\release\my_company.my_usd_composer.kit.bat ^
  --ext-folder "C:/dev/vps_omniverse/exts" --enable vps.live.viz
```
- `.bat`이 `%*`로 인자를 그대로 kit.exe에 넘기므로, **kit-app-template은 안 건드리고**
  검색경로(`--ext-folder`)만 붙여서 우리 익스텐션(`vps.live.viz`)을 로드한다.
- 먼저 `y_short.usda`를 열어두면 그 위에 차량 prim이 올라간다.

---

## 5. 지금 상태 한 줄 정리

> **맵은 이미 옴니버스에서 열 수 있다(✅). 막혀있는 건 "그 위에 움직이는 차량을 얹는" 부분인데,
> 헤드리스(화면 없는) 검증에선 stage가 없어 안 보였다. STEP 3부터 Composer GUI로 직접 띄워야 진도가 나간다.**

**다음 액션:** Windows에서 Composer 열고 → `y_short.usda` 열어서 맵이 제대로 뜨는지 눈으로 확인
→ 되면 차량 1개 올리는 STEP 3로.
