# Omniverse Kit Extension: MQTT 실시간 차량 데모 — 진행 계획 v2 (리뷰 반영)

> v1(`~/omniverse_mqtt_demo_plan.md`) + 2026-06-06 코드/환경 검증 리뷰 반영본.
> 정본 위치: `C:\dev\vps_omniverse\docs\02_mqtt_demo_plan.md`
> 최종 산출물: **화면녹화 영상** (VPS → MQTT → Omniverse 차량 prim 실시간 이동)

---

## 📊 진행 현황 (2026-06-06 헤드리스 스모크 검증)

| STEP | 내용 | 상태 |
|---|---|---|
| 0-1 | Kit 버전 확인 | ✅ 완료 (앱 110.1.1, SDK exts 110.x / omni.usd 1.15.2) |
| 0-2 | Win↔WSL 브로커 연결 | ✅ 완료 (MQTT 왕복, host=localhost) |
| 0-3 | Kit 파이썬 paho | ✅ 완료 (paho 2.1.0 설치+import 동작) |
| 0-4 | 브로커 생존 | ✅ 완료 (9883/9003 LISTEN) |
| 1 | Extension 켜기 | ✅ 완료 (registered + `[vps.live.viz] startup` 로그) |
| 2 | Update loop 훅 | ✅ 완료 (동작, deprecation 경고만 — 추후 Events 2.0) |
| 3 | Prim 생성 + 하드코딩 이동 | ⬜ **남음** (스테이지/윈도우 필요, 헤드리스엔 stage 없었음) |
| 4 | MQTT 수신 로그 | 🟡 **부분** (연결+구독 rc=0 확인 ✅ / 메시지 수신 출력은 미관측) |
| 5 | Thread-safe 큐 다리 | ⬜ **남음** (스켈레톤 코드 있음, 데이터 통과 미검증) |
| 6 | MQTT 데이터로 prim 이동 | ⬜ **남음** |
| 7 | VPS 실데이터 연결 | ⬜ **남음** (VPS 송신부 추가) |
| 8 | 보간 (선택) | ⬜ 선택 |

**다음 할 일**: STEP 3 (Composer GUI로 `y_short.usda` 열고 차량 prim 1개 띄워 sin/cos 이동)
→ STEP 4 메시지 수신 출력 확인 → STEP 5·6(데이터→prim) → STEP 7(VPS 연결).
스모크 테스트로 0~2·4연결은 자동 통과했고, **3·5·6은 화면(GUI)에서 봐야** 확정됨.

---

## 0. 환경 사실 (검증 완료, 2026-06-06)

| 항목 | 값 | 검증 |
|---|---|---|
| Kit 앱 | Windows `C:\dev\kit-app-template` (앱 110.1.1) | 빌드 완료 |
| 브로커 | WSL mosquitto, **`0.0.0.0` 바인딩** | `ss` LISTEN 확인 ✅ |
| 브로커 TCP | `tcp://localhost:9883` (extension 파이썬 구독) | LISTEN ✅ |
| 브로커 WS | `ws://localhost:9003` (VPS 브라우저 publish) | LISTEN ✅ |
| 인증 | `allow_anonymous true` | conf 확인 ✅ |
| **VPS MQTT** | **이미 `mqtt@5.10.1` + 라이브 클라(`ws://9003`) 보유** | package.json/mqttConfig.ts ✅ |
| 변환 정본 | `C:\dev\vps_omniverse` (converter/out/exts) | 세팅 완료 ✅ |
| 좌표 규약 | **Z-up, identity** (editor_x→x, editor_y→y, z=3.8) | converter 확정 ✅ |

### 핵심 원칙 (불변)
- **수신(MQTT)과 렌더링(prim 갱신)을 절대 한 번에 붙이지 않는다.** 따로 검증 후 마지막에 합친다.
- 막히면 "어느 STEP에서 깨졌는지" 즉시 알 수 있게 단계를 쪼갠다.
- UI(메뉴/버튼)는 데모 필수 아님. 자동 연결로 생략 가능.

### 리뷰로 바뀐 점 (v1 대비)
1. **STEP 0-2 리스크 ↓**: 브로커가 `0.0.0.0` 바인딩 확인 → Windows에서 WSL IP로 붙는 경로 확실.
2. **STEP 7 단축**: VPS에 MQTT 인프라(`mqtt@5.10.1`, 클라이언트, 토픽규약) 이미 있음 → **새 연결 X, 기존 클라이언트로 publish만 추가**.
3. **STEP 3 좌표계 "미정" 닫음**: converter 규약(Z-up identity, z=3.8) 그대로. 차량도 동일.
4. **STEP 3에 맵 USD 로딩 추가**: `out/y_short.usda` 위에 차량 올림 → 좌표검증 공짜 + 데모 설득력↑.
5. **extension 위치 확정**: `C:\dev\vps_omniverse\exts\vps.live.viz` (이미 스켈레톤 있음). kit-app-template은 `--ext-folder`로 경로만 등록, 안 더럽힘.
6. **차량 표현**: 데모는 **prim-per-id**(소수 차량, 단순). 대수 늘면 PointInstancer로 교체.

### 환경 갈림길
- **usdview** = USD 뷰어일 뿐. extension/MQTT/update loop **불가**.
- **Kit 런타임 앱(kit-app-template)** = STEP 1~8 전부 여기서.

---

## STEP 0 — 환경 확인 (코딩 전 1순위 관문)

### 0-1. Kit 버전
- 앱 110.1.1. kit-app-template이 끌어오는 **실제 Kit SDK 버전**도 확인(코드/검색 시 명시).

### 0-2. Windows↔WSL 브로커 연결 ⚠️ — **✅ 통과 (2026-06-06)**
**결과: `localhost:9883` 로 됨.** Windows anaconda python(paho) → `localhost:9883` publish
→ WSL `mosquitto_sub` 수신 성공 (MQTT 왕복 완전 확인). 스키마 `[{id,x,y,rot}]` OK.
- Windows TCP 도달: `localhost:9883` True / WSL_IP 직결(172.x) False → **host=localhost 사용**.
- Windows엔 9883 리스너 없음 → localhost True는 WSL2 localhostForwarding 포워딩.
- extension `MQTT_HOST="localhost"` 확정 (스켈레톤 반영됨).

Kit(Windows) 파이썬이 WSL의 9883에 붙어야 한다. 브로커는 0.0.0.0이므로 경로는 열림.
- 1차: Windows에서 `localhost:9883` 도달 확인 (WSL2 localhostForwarding/mirrored).
  ```powershell
  Test-NetConnection localhost -Port 9883
  ```
- 2차(localhost 실패 시): WSL IP로.
  ```bash
  wsl hostname -I        # WSL IP
  ```
  ```powershell
  Test-NetConnection <WSL_IP> -Port 9883
  ```
- 실제 pub/sub 왕복:
  ```bash
  # WSL (대기)
  mosquitto_sub -h localhost -p 9883 -t test
  ```
  ```powershell
  # Windows (mosquitto 설치돼 있으면)
  mosquitto_pub -h <host> -p 9883 -t test -m hi
  ```
- **결과를 extension `MQTT_HOST`에 박는다** (localhost or WSL IP).

### 0-3. Kit 임베디드 파이썬에 paho (STEP 1에서 같이)
- extension.toml `[python.pipapi] requirements=["paho-mqtt"]` (이미 선언됨).
- 검증: Kit Script Editor `import paho.mqtt.client` 통과.

### 0-4. 브로커 살아있음 (확인 완료 ✅)
```bash
ss -tlnp | grep -E "9883|9003"   # 둘 다 0.0.0.0 LISTEN
```

✅ **STEP 0 완료 기준**: Windows→WSL 9883 도달 OK + Kit에서 `import paho` OK.

---

## STEP 1 — 빈 Extension 켜기  ✅ 완료
- **이미 있는 스켈레톤 사용**: `C:\dev\vps_omniverse\exts\vps.live.viz`.
- kit-app-template `.kit` 실행 시 `--ext-folder "C:/dev/vps_omniverse/exts" --enable vps.live.viz`
  (또는 `.kit`의 `[settings.app.exts.folders] '++'`에 경로 추가).
- 매니저에서 켜고/끄면 `[vps.live.viz] startup/shutdown` 로그.
- 손으로 쓴 `extension.toml`이 Kit 110.x에서 로드되는지 여기서 확인 (안 되면 toml/경로/버전).

**완료기준**: startup/shutdown 로그.
**상태 ✅**: 헤드리스 런치에서 `[ext: vps.live.viz-0.1.0] registered` + `[vps.live.viz] startup` 확인. (toml 의존성에서 `omni.kit.app` 제거가 핵심이었음 — 커널이라 암묵 제공)

---

## STEP 2 — Update Loop 훅 검증 (MQTT 없음)  ✅ 완료
- `omni.kit.app.get_app().get_update_event_stream()` 구독 (스켈레톤에 이미 있음).
- 콜백에서 프레임 카운터++, 60프레임마다 `print(f"tick {n}")`.
- **prim 갱신이 일어나는 유일한 곳**(스레드 안전).

**완료기준**: 주기적 tick 로그.
**상태 ✅**: `get_update_event_stream().create_subscription_to_pop(...)` 구독 생성됨(스켈레톤). ⚠️ deprecation 경고("Use Events 2.0") 뜨지만 동작엔 지장 없음 — 추후 Events 2.0으로 교체 고려.

---

## STEP 3 — Prim 만들고 하드코딩으로 움직이기 (MQTT 없음)  ⬜ 남음 ← **다음**
- **맵 USD 로딩**: `out/y_short.usda`를 스테이지로 열기(or sublayer/reference).
- 차량 prim 1개(Cube) 생성, update 콜백에서 sin/cos로 `translate` 갱신 → 혼자 왕복.
- **좌표 규약 적용**(이미 확정): Z-up, (x, y, z=3.8), rot=Z축. 축 안 바꿈.
- **검증 보너스**: 차량이 레일 위 평면에 딱 올라가면 좌표 변환 맞은 것.

**완료기준**: MQTT 없이 차량이 맵 위에서 스스로 움직인다 (렌더 경로 완성).
**상태 ⬜**: 미완. 헤드리스엔 stage가 없어 instancer 미생성(`no stage open` 로그). → Composer GUI로 `y_short.usda` 열고 확인 필요. (instancer 지연생성은 코드에 반영해둠)

---

## STEP 4 — MQTT 수신만, 로그로만 (prim 안 건드림)  🟡 부분
- paho로 `9883`(STEP 0-2 결과 host) 연결, `VPS/viz/vehicles` 구독.
- on_message에서 payload **print만**.
- 수동 테스트 (VPS 아직 안 붙임):
  ```bash
  mosquitto_pub -h localhost -p 9883 -t VPS/viz/vehicles \
    -m '[{"id":1,"x":1.0,"y":2.0,"rot":0.5}]'
  ```
- ⚠️ on_message는 **별도 스레드**. 지금은 print만 OK. **여기서 USD 절대 안 건드림.**

**완료기준**: 수동 publish가 콘솔에 찍힌다.
**상태 🟡**: Kit이 `localhost:9883` 연결+`VPS/viz/vehicles` 구독까지 확인(`mqtt connected rc=0`). 단 헤드리스 런 중 실제 메시지를 쏘진 않아 **수신 출력(on_message print)은 미관측**. STEP 3 GUI 세션에서 `mosquitto_pub`로 확인.

---

## STEP 5 — Thread-safe 큐 (수신↔렌더 다리)  ⬜ 남음
- `queue.Queue`(또는 lock+버퍼, 스켈레톤은 lock+dict).
- on_message(별도 스레드): 파싱→큐 put만. USD 손 안 댐.
- update 콜백(메인 스레드): 큐 get→로컬 상태 저장 (아직 prim X).

**완료기준**: 데이터가 큐 거쳐 메인 스레드에서 꺼내진다.
**상태 ⬜**: 스켈레톤에 lock+버퍼(on_message put / update get) 구조는 있으나 실제 데이터 통과 미검증.

---

## STEP 6 — 합치기: MQTT 데이터로 prim 움직이기  ⬜ 남음
- update 콜백에서 큐 데이터로 prim translate/orient 갱신.
- STEP 3 sin/cos → 실제 좌표로 교체.
- 차량 여러 대: **id별 prim 매핑**(없으면 생성, 있으면 갱신). [대수 많아지면 PointInstancer]

**완료기준**: `mosquitto_pub` 좌표 → 해당 차량 prim 이동.
**상태 ⬜**: 미완. (스켈레톤 `_on_update`에 positions 갱신 로직 있음, 화면 검증 필요)

---

## STEP 7 — VPS 실데이터 연결 (기존 MQTT 재사용)  ⬜ 남음
- VPS는 이미 `mqtt@5.10.1` 클라이언트(`ws://localhost:9003`) 보유 → **재사용**.
- **publish 지점**: 메인 스레드에서 SharedArrayBuffer 차량 위치를 읽는 곳(렌더 루프/리더)에서 **1Hz 스로틀**로 `VPS/viz/vehicles`에 `[{id,x,y,rot}]` 발행.
- VPS가 보내는 x,y = editor 좌표인지 확인(거의 확실). fab 1개, 차량 일부로 시작.
- 코드 위치: **VPS repo** (송신부). extension(수신부)은 vps_omniverse.

**완료기준**: VPS 돌리면 Omniverse에서 차량이 실제 시뮬 따라 움직인다.
**상태 ⬜**: 미착수. VPS 송신부(SharedArrayBuffer 리더에서 1Hz publish) 추가 필요.

---

## STEP 8 (선택) — 보간으로 부드럽게
- 1Hz 텔레포트 끊김 → update 콜백에서 직전→새 위치 frame별 lerp/slerp.
- 시간 없으면 생략(1초 텔레포트로도 연동 증명됨).

---

## 디버깅 맵
| 증상 | 의심 |
|---|---|
| Windows에서 9883 연결 안 됨 | STEP 0-2 (localhost→WSL IP 교체) |
| extension 인식 안 됨 | STEP 1 (toml/경로/ext-folder/버전) |
| import paho 실패 | STEP 0-3 (pipapi 설치) |
| 브라우저 MQTT 연결 안 됨 | WS 9003 (이미 LISTEN, VPS 클라 설정 확인) |
| tick 로그 안 뜸 | STEP 2 (update stream) |
| 차량 옆으로 누움/안 보임 | STEP 3 (Z-up/스케일/z=3.8) |
| 메시지 받는데 화면 안 움직임 | STEP 5~6 (큐 get/prim 매핑) |
| 랜덤 크래시 | 스레드 위반 (on_message에서 USD 직접 건드림) |

---

## 결정 완료 (v1 미정 항목)
- [x] extension 소스 위치 → `C:\dev\vps_omniverse\exts\vps.live.viz` (--ext-folder 등록)
- [x] 좌표 규약 → Z-up identity, z=3.8 (converter와 동일)
- [x] Windows→WSL host = **localhost** (STEP 0-2 통과, 2026-06-06)
- [ ] VPS publish x,y = editor 좌표 확인 → STEP 7
