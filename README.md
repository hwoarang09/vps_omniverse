# vps_omniverse

VPS(MapTool) 맵을 **USD로 변환**하고, 나아가 **Omniverse에서 차량 위치를 실시간 렌더**하기 위한 작업 정본 폴더.

VPS 웹 시뮬레이터의 렌더링 로직을 Omniverse(USD/Kit)로 옮기는 것이 목표.
출처 로직: `vps/src/components/three/entities/edge/points_calculator/*`, `renderers/*`.

---

## 폴더 구조

```
vps_omniverse/
├─ converter/     Phase A — 맵→USD 변환 (usd-core, Kit 불필요)
│   ├─ convert_map_to_usd.py   메인: <맵폴더> <출력.usda>
│   ├─ mapio.py                nodes/edges/station 파서
│   ├─ geometry.py             레일 곡선 + 스테이션 (VPS 로직 포팅)
│   ├─ usd_build.py            USD 스테이지/프림 헬퍼
│   └─ 01_min_instancer.py     PointInstancer 최소 예제(학습용)
├─ input/         자급용 입력 맵 (y_short)  ※ 원본은 vps/public/railConfig/
├─ out/           결과물: y_short.usda + 렌더 PNG 4장
├─ exts/          Phase B — Kit 확장 (python, 실시간 MQTT 렌더)
│   └─ vps.live.viz/
│       ├─ config/extension.toml
│       └─ vps/live/viz/extension.py
├─ apps/          (선택) 커스텀 .kit — exts.folders에 ../exts 추가용
├─ docs/          기획 문서 (01_usdviewer.md)
└─ requirements.txt   usd-core==26.5
```

---

## Phase A — 맵 → USD (지금 동작함)

순수 `usd-core`. Omniverse/Kit 설치 불필요. 어느 OS든 됨.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |  WSL/mac: source .venv/bin/activate
pip install -r requirements.txt     # usd-core==26.5

cd converter
python convert_map_to_usd.py ../input/y_short ../out/y_short.usda
```

**결과 보기:**
- 미리보기만: `out/render_top.png` 등 4장 열기.
- 인터랙티브: `usdview out/y_short.usda` → Camera 메뉴 → `TopCam`.
  - WSLg는 GL이 소프트웨어라 느림: `LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe usdview ...`
  - Windows 네이티브 usdview / Omniverse Composer 권장.

씬: `/World` (Z-up, m) → `/World/Rails`(BasisCurves, 폭 0.25) + `/World/Stations`(PointInstancer, 타입별 색) + `/World/TopCam`.

---

## Phase B — 실시간 차량 렌더 (Kit 확장, 뼈대만)

"Kit을 python으로" = **Kit Extension**. 코드는 여기 `exts/vps.live.viz`에 두고,
kit-app-template은 **건드리지 않고** 런타임 호스트로만 쓴다 (확장 검색경로만 추가).

**흐름** (VPS의 SharedArrayBuffer→InstancedMesh 대응):
```
MQTT(차량위치) → on_message(네트워크 스레드, 버퍼 적재)
              → 앱 update tick(메인 스레드) → PointInstancer.positions 갱신 → RTX 렌더
```

**Kit에 우리 확장 물려서 실행:**
```bash
# kit-app-template 의 .kit 앱 실행 시 확장 검색경로 추가
<kit>/kit.exe <app>.kit --ext-folder "C:/dev/vps_omniverse/exts" --enable vps.live.viz
# 또는 .kit 의 [settings.app.exts.folders] '++' 에 "C:/dev/vps_omniverse/exts" 추가
```
- 먼저 `out/y_short.usda`를 스테이지로 열어두면 그 위에 차량이 올라감.
- `paho-mqtt`는 Kit 임베디드 파이썬에 없음 → extension.toml `[python.pipapi]`로 자동 설치되거나 `<kit>/python.bat -m pip install paho-mqtt`.

**채워야 할 TODO** (`extension.py`):
- `MQTT_PORT` / `MQTT_TOPIC` — 실제 VPS 차량 송신 토픽 (예: `VPS/vehicles/{session}`)
- `_on_message` payload 파싱 — VPS가 보내는 실제 JSON 포맷에 맞추기
- id→인스턴스 슬롯 매핑 (현재는 id 정렬 기반 임시)

---

## kit-app-template 과의 관계

| 코드 | 위치 | Kit |
|---|---|---|
| 맵→USD 변환 | `vps_omniverse/converter` | ❌ usd-core만 |
| USD 결과 에셋 | `vps_omniverse/out/*.usda` | – |
| 실시간 MQTT 렌더 | `vps_omniverse/exts/vps.live.viz` | ✅ (런타임) |
| Omniverse 앱 실행기 | `C:\dev\kit-app-template` (그대로) | ✅ RTX 호스트 |

우리 로직은 전부 이 폴더에. kit-app-template엔 "exts 폴더 봐줘"라고 경로만 알려준다.
