"""
VPS Live Viz — MQTT 차량 위치 → Omniverse PointInstancer 실시간 갱신.

VPS(웹) 아키텍처 대응:
  VPS:        Worker → SharedArrayBuffer(Float32Array) → useFrame → InstancedMesh
  여기(Kit):  MQTT  → 위치 버퍼(dict)               → update tick → PointInstancer.positions

스레드 안전:
  paho-mqtt 콜백은 네트워크 스레드에서 돈다. USD 스테이지 편집은 메인(앱) 스레드에서만
  해야 하므로, on_message 는 latest 위치만 버퍼에 적재하고, 실제 USD 쓰기는
  omni.kit.app 의 update 콜백(메인 스레드)에서 flush 한다.

뼈대 상태:
  - MQTT 연결/구독/해제, instancer 보장/갱신 루프까지 동작.
  - TODO 표시된 곳(토픽, payload 파싱)은 실제 VPS 송신 포맷에 맞춰 채울 것.
"""
from __future__ import annotations
import json
import threading
import time

import numpy as np
import omni.ext
import omni.usd
import omni.kit.app
from pxr import Usd, UsdGeom, Gf, Vt, Sdf

# === 설정 (omniverse_mqtt_demo_plan.md 기준) ============================
# 브로커: WSL mosquitto, 0.0.0.0 바인딩. extension(파이썬)은 TCP 9883 구독.
# Windows→WSL localhost 안 되면 `wsl hostname -I` IP로 교체 (plan STEP 0-2).
MQTT_HOST = "localhost"
MQTT_PORT = 9883                 # plan: tcp://localhost:9883
# VPS 는 fab 별로 VPS/viz/{fabId}/vehicles 로 쏨. 멀티팹이면 fab 마다 id 가 0,1,2…
# 로 겹치므로 반드시 **한 fab 만** 구독 (와일드카드 쓰면 차량이 fab 사이로 튐).
# 좌표는 fab-local(editor) 이라 fab 하나만 받으면 y_short USD 에 딱 맞음.
# 다른 fab 보려면 VIZ_FAB 만 바꾸면 됨 (예: "fab_2_1"). 단일팹이면 "default".
VIZ_FAB = "fab_0_0"
MQTT_TOPIC = f"VPS/viz/{VIZ_FAB}/vehicles"

VEHICLE_INSTANCER_PATH = "/World/Vehicles"
# 프로토타입을 인스턴서 하위에 둔다 → Hydra 가 PointInstancer 하위를 prune 하므로
# 원본이 원점에 standalone 으로 안 그려지고 instance 로만 그려진다.
# JobState 색마다 프로토타입 1개(Vehicle_{jobState}) → protoIndex 로 차량 색 전환.
VEHICLE_PROTOS_PARENT = "/World/Vehicles/Protos"

RAIL_Z = 3.8        # 레일(edge) 높이 (converter 와 동일, node editor_z)
VEHICLE_Z = RAIL_Z  # 인스턴스는 레일 점에 둠 — OHT 형상이 자체 z오프셋(바퀴=레일)을 가짐
RAIL_GAUGE = 0.4    # 두 레일 간격 (geometry.RAIL_GAUGE) — 바퀴를 Y=±gauge/2 에 얹음

# 렌더 지연(ms, 시뮬시간 단위) — "받은 최신 sim-time - 이만큼" 시점을 그림.
# 클수록 버퍼 여유↑(지터/배속에 강함) 대신 화면 지연↑. 3초 = 넉넉한 버퍼.
# (더 부드럽게 원하면 5000, 더 실시간이면 1000~2000 로)
RENDER_DELAY_MS = 3000.0

# OHT 형상 색 — 레일에 걸쳐진 대차(뚜껑)만 JobState 색으로 칠해
# "픽업하러 가는놈/드롭하러 가는놈/대기중인놈"을 멀리서도 구분. 본체+FOUP 는 회색 고정.
OHT_WHEEL_COLOR = (0.22, 0.22, 0.25)  # 바퀴 — 진회색(상태무관)
OHT_BODY_COLOR  = (1.0, 1.0, 1.0)     # 매달린 본체(veh) — 강한 흰색(상태무관)
OHT_FOUP_COLOR  = (1.0, 1.0, 1.0)     # FOUP(veh) — 강한 흰색(상태무관)

# JobState(VPS) → 대차(뚜껑) 색. 인덱스 = JobState enum 값(0..6) = PointInstancer protoIndex.
# 색은 VPS src/config/colors.ts (VEHICLE_JOB_STATE_COLORS) 와 동일 hex 를 0~1 RGB 로 변환.
#   0 INITIALIZING #374151 / 1 IDLE #ffffff / 2 MOVE_TO_LOAD #ec4899 / 3 LOADING #06b6d4
#   4 MOVE_TO_UNLOAD #3b82f6 / 5 UNLOADING #f97316 / 6 ERROR #ef4444
JOB_STATE_COLORS = [
    (0.216, 0.255, 0.318),  # 0 INITIALIZING — 회색 (#374151)
    (1.000, 1.000, 1.000),  # 1 IDLE         — 흰색 (#ffffff) 대기/그냥 움직이는 놈
    (0.925, 0.282, 0.600),  # 2 MOVE_TO_LOAD — 분홍 (#ec4899) 픽업하러 가는놈
    (0.024, 0.714, 0.831),  # 3 LOADING      — 청록 (#06b6d4) 픽업 중
    (0.231, 0.510, 0.965),  # 4 MOVE_TO_UNLOAD — 파랑 (#3b82f6) 드롭하러 가는놈
    (0.976, 0.451, 0.086),  # 5 UNLOADING    — 주황 (#f97316) 드롭 중
    (0.937, 0.267, 0.267),  # 6 ERROR        — 빨강 (#ef4444)
]
NUM_JOB_STATES = len(JOB_STATE_COLORS)
DEFAULT_JOB_STATE = 1  # 상태정보 없는(구버전 payload) 차량 = IDLE(흰색)


class VpsLiveVizExtension(omni.ext.IExt):
    def on_startup(self, ext_id: str):
        print("[vps.live.viz] startup")
        self._stage: Usd.Stage | None = omni.usd.get_context().get_stage()
        self._instancer: UsdGeom.PointInstancer | None = None
        self._lock = threading.Lock()
        # 타임스탬프 스냅샷 버퍼 (차량별 시간순) → 렌더지연 보간
        self._buf: dict[int, list[tuple[float, float, float]]] = {}  # id → [(t_ms, x, y, rot), ...]
        #   ↑ 실제로는 (t, x, y, rot, spd) 5-튜플. 주석 타입은 단순화 표기.
        self._job: dict[int, int] = {}  # id → JobState(최신값, 보간 안 함) → protoIndex 색
        self._latest_t = 0.0       # 수신한 최신 sim-time(ms)
        self._render_t: float | None = None  # 현재 렌더 sim-time(ms) — latest_t - DELAY 추종
        self._last_wall: float | None = None  # 직전 _on_update wall clock(monotonic)
        self._sim_rate = 1.0       # sim-ms / wall-ms (EMA) — VPS 시뮬 진행속도(배속) 추정
        self._last_msg_t: float | None = None     # 직전 메시지 sim-time (rate 측정용)
        self._last_msg_wall: float | None = None  # 직전 메시지 수신 wall clock
        self._client = None
        self._got_msg = False  # 첫 MQTT 수신 로그용

        self._ensure_instancer()
        self._start_mqtt()

        # 메인 스레드 업데이트 구독 → 여기서만 USD 편집
        self._sub = (
            omni.kit.app.get_app()
            .get_update_event_stream()
            .create_subscription_to_pop(self._on_update, name="vps.live.viz.update")
        )

    def on_shutdown(self):
        print("[vps.live.viz] shutdown")
        self._sub = None
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception as e:  # noqa: BLE001
                print(f"[vps.live.viz] mqtt stop err: {e}")
            self._client = None

    # --- USD: 차량 instancer 준비 -------------------------------------
    def _ensure_instancer(self):
        stage = self._stage
        if stage is None:
            print("[vps.live.viz] no stage open — y_short.usda 를 먼저 열어주세요")
            return

        # 인스턴서 먼저 생성 (프로토타입을 그 하위에 둘 거라 순서 중요)
        inst_prim = stage.GetPrimAtPath(VEHICLE_INSTANCER_PATH)
        if inst_prim:
            self._instancer = UsdGeom.PointInstancer(inst_prim)
        else:
            self._instancer = UsdGeom.PointInstancer.Define(stage, VEHICLE_INSTANCER_PATH)
            self._instancer.CreatePositionsAttr().Set(Vt.Vec3fArray([]))
            self._instancer.CreateProtoIndicesAttr().Set(Vt.IntArray([]))
            self._instancer.CreateOrientationsAttr().Set(Vt.QuathArray([]))

        # OHT 프로토타입 — JobState 색마다 1개 (인스턴서 하위 → 원점 잔상 안 생김).
        # 리로드마다 형상/색 갱신되게 기존 것 제거 후 재생성 (튜닝 편의).
        # protoIndex == JobState enum 값 이 되도록 인덱스 순서대로 생성.
        if stage.GetPrimAtPath(VEHICLE_PROTOS_PARENT):
            stage.RemovePrim(VEHICLE_PROTOS_PARENT)
        proto_paths = []
        for idx, color in enumerate(JOB_STATE_COLORS):
            p = f"{VEHICLE_PROTOS_PARENT}/Vehicle_{idx}"
            self._build_oht_proto(stage, p, color)
            proto_paths.append(Sdf.Path(p))
        self._instancer.CreatePrototypesRel().SetTargets(proto_paths)

    # --- OHT 형상 (gree1.png): 레일 타는 대차(위) + 매달린 본체 + FOUP(아래) --
    #     carriage_color = JobState 색 (레일에 걸쳐진 대차 "뚜껑"에만 적용).
    #     본체+FOUP(veh) 는 강한 흰색, 바퀴는 진회색 고정.
    def _build_oht_proto(self, stage, path, carriage_color):
        """로컬축 X=진행, Y=좌우, Z=상. 인스턴스가 레일점(z=RAIL_Z)에 놓이므로
        로컬 z=0 = 레일 높이.
          - 대차(바퀴+상판): 두 레일(Y=±g) 위 (z>0) — "바퀴 걸치는 부분"
          - 목: 레일 사이 gauge 틈으로 내려감 (레일 안 건드림)
          - 본체 + FOUP: 레일 아래로 매달림 (z<0)"""
        g = RAIL_GAUGE / 2.0  # 0.20

        UsdGeom.Xform.Define(stage, path)

        def box(name, scale, trans, color):
            c = UsdGeom.Cube.Define(stage, path + "/" + name)
            c.GetSizeAttr().Set(1.0)
            c.CreateDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*color)]))
            api = UsdGeom.XformCommonAPI(c)
            api.SetScale(Gf.Vec3f(*scale))
            api.SetTranslate(Gf.Vec3d(*trans))

        def wheel(name, trans):
            cyl = UsdGeom.Cylinder.Define(stage, path + "/" + name)
            cyl.GetRadiusAttr().Set(0.05)
            cyl.GetHeightAttr().Set(0.04)
            cyl.GetAxisAttr().Set("Y")  # Y축 원통 → 진행(X) 방향으로 구름
            cyl.CreateDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*OHT_WHEEL_COLOR)]))
            UsdGeom.XformCommonAPI(cyl).SetTranslate(Gf.Vec3d(*trans))

        # --- 대차 (레일 위, "바퀴 걸치는 부분") ---
        wheel("wheel_fl", (0.13, +g, 0.05))
        wheel("wheel_fr", (0.13, -g, 0.05))
        wheel("wheel_bl", (-0.13, +g, 0.05))
        wheel("wheel_br", (-0.13, -g, 0.05))
        # 레일에 걸쳐진 대차 "뚜껑" — 여기만 JobState 색으로 칠해 상태 구분
        box("carriage", (0.38, 0.50, 0.06), (0.0, 0.0, 0.09), carriage_color)
        # --- 매달림 목 (레일 사이 gauge 틈으로 하강) ---
        box("neck", (0.10, 0.10, 0.22), (0.0, 0.0, -0.01), OHT_WHEEL_COLOR)
        # --- 본체 + FOUP (레일 아래 매달림, veh) — 강한 흰색 고정 ---
        box("body", (0.40, 0.36, 0.32), (0.0, 0.0, -0.27), OHT_BODY_COLOR)
        box("foup", (0.28, 0.28, 0.24), (0.0, 0.0, -0.54), OHT_FOUP_COLOR)

    # --- MQTT ----------------------------------------------------------
    def _start_mqtt(self):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            print("[vps.live.viz] paho-mqtt 없음 — extension.toml pipapi 로 설치되거나 "
                  "kit python.bat -m pip install paho-mqtt 필요")
            return

        client = mqtt.Client()
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            client.loop_start()  # 네트워크 스레드 시작
            self._client = client
        except Exception as e:  # noqa: BLE001
            print(f"[vps.live.viz] mqtt connect 실패: {e}")

    def _on_connect(self, client, userdata, flags, rc):
        print(f"[vps.live.viz] mqtt connected rc={rc}, subscribe {MQTT_TOPIC}")
        client.subscribe(MQTT_TOPIC)

    def _on_message(self, client, userdata, msg):
        # 네트워크 스레드 — USD 만지지 말 것. 버퍼에만 적재.
        try:
            data = json.loads(msg.payload)
        except Exception:  # noqa: BLE001
            return
        # plan 스키마: bare 배열 [{id, x, y, rot}, ...]. 1Hz.
        # 차량은 레일 위 → z 는 레일 높이(RAIL_Z=3.8) 고정, rot 은 Z축 회전(rad).
        # (Z-up identity 좌표계 — converter 와 동일, 축 안 바꿈)
        # 포맷: {"t": sim_ms, "v": [[id, x, y, rot, spd, job], ...]}
        #   job = JobState enum(0..6) → 색. 없으면(구버전) IDLE.
        try:
            t = float(data["t"])
            rows = data["v"]
        except (KeyError, TypeError, ValueError):
            return
        if not rows:
            return
        if not self._got_msg:
            self._got_msg = True
            print(f"[vps.live.viz] first msg OK: t={t}, {len(rows)} veh, sample={rows[0]}")

        with self._lock:
            for r in rows:
                try:
                    vid = int(r[0])
                    spd = float(r[4]) if len(r) > 4 else 0.0
                    job = int(r[5]) if len(r) > 5 else DEFAULT_JOB_STATE
                    sample = (t, float(r[1]), float(r[2]), float(r[3]), spd)  # (t, x, y, rot, spd)
                except (IndexError, ValueError, TypeError):
                    continue
                self._buf.setdefault(vid, []).append(sample)
                self._job[vid] = job  # 색은 보간 없이 최신 상태로 즉시 반영
            if t > self._latest_t:
                self._latest_t = t
            # sim 진행속도(rate)를 '메시지 도착 간격'으로 측정 → 안정적(프레임마다 X).
            # (프레임마다 재면 메시지 사이엔 latest 안 변해 0 으로 떨어지고 도착시 튐 = 출렁임)
            now = time.monotonic()
            if self._last_msg_wall is not None and self._last_msg_t is not None and t > self._last_msg_t:
                dtw = (now - self._last_msg_wall) * 1000.0  # wall ms
                if dtw > 0:
                    inst = (t - self._last_msg_t) / dtw     # sim-ms / wall-ms
                    if 0.0 < inst < 50.0:
                        self._sim_rate = self._sim_rate * 0.85 + inst * 0.15
            self._last_msg_t = t
            self._last_msg_wall = now

    # --- 메인 스레드: 렌더지연 보간하여 USD flush (60fps) ----------------
    def _on_update(self, _e):
        now_wall = time.monotonic()
        with self._lock:
            latest_t = self._latest_t
            sim_rate = self._sim_rate
            buf = {vid: list(s) for vid, s in self._buf.items()}  # 얕은 복사(읽기용)
            job = dict(self._job)  # id → JobState (색)
        if not buf or latest_t <= 0:
            self._last_wall = now_wall
            return
        # 스테이지를 나중에 열었을 수 있음 → instancer 지연 생성
        if self._instancer is None:
            self._stage = omni.usd.get_context().get_stage()
            self._ensure_instancer()
        if self._instancer is None:
            self._last_wall = now_wall
            return

        # 렌더 sim-time = (latest_t - DELAY) 를 따라가되, '메시지 간격으로 측정한
        # 안정적 sim_rate' 로 등속 전진 → 빨라졌다 느려졌다(출렁임) 없음.
        desired = latest_t - RENDER_DELAY_MS
        if self._render_t is None or self._last_wall is None:
            self._render_t = desired
        else:
            dt_wall = (now_wall - self._last_wall) * 1000.0
            # 안정 rate 로 등속 전진 (프레임마다 rate 재계산 안 함)
            self._render_t += sim_rate * dt_wall
            # 목표 지연으로 '아주 약하게'만 수렴 → 드리프트만 잡고 속도감은 유지
            self._render_t += (desired - self._render_t) * 0.02
            # 안전 클램프 (3초 버퍼라 평소엔 안 걸림)
            self._render_t = min(self._render_t, latest_t)
            self._render_t = max(self._render_t, latest_t - 6.0 * RENDER_DELAY_MS)
        self._last_wall = now_wall
        rt = self._render_t

        ids = sorted(buf.keys())
        n = len(ids)
        # === 차량별 rt 브래킷(왼쪽 a / 오른쪽 b) 샘플을 numpy 배열로 수집 ===
        # 각 차량 samples 는 시간순 (t,x,y,rot,spd). rt 를 감싸는 두 샘플을 고른다.
        #   - 범위 밖이면 a==b (양끝값 유지 = 정지/데이터없음)
        #   - 차량마다 타임스탬프가 달라 '브래킷 탐색'만 차량별(이진탐색), 보간 수식은 일괄.
        at = np.empty(n); ax = np.empty(n); ay = np.empty(n); arot = np.empty(n); aspd = np.empty(n)
        bt = np.empty(n); bx = np.empty(n); by = np.empty(n); brot = np.empty(n); bspd = np.empty(n)
        for k, vid in enumerate(ids):
            s = buf[vid]
            if rt <= s[0][0]:
                a = b = s[0]
            elif rt >= s[-1][0]:
                a = b = s[-1]
            else:  # 이진탐색: s[lo][0] <= rt < s[hi][0]
                lo, hi = 0, len(s) - 1
                while lo + 1 < hi:
                    mid = (lo + hi) // 2
                    if s[mid][0] <= rt:
                        lo = mid
                    else:
                        hi = mid
                a, b = s[lo], s[hi]
            at[k], ax[k], ay[k], arot[k], aspd[k] = a
            bt[k], bx[k], by[k], brot[k], bspd[k] = b

        # === cubic Hermite 보간 (전 차량 일괄) ===
        # 두 샘플의 '속도'까지 존중 → 가감속 부드러움(정지 spd=0 이면 부드러운 감속 정지).
        # 속도벡터 = spd·(cos rot, sin rot), 위치 trajectory 와 일치하면 overshoot 없음.
        # span==0(범위 밖, a==b)이면 dt=0·sp=0 → x=ax(=bx) 로 자연히 끝값 유지.
        span = bt - at
        denom = np.where(span > 0.0, span, 1.0)
        sp = np.clip((rt - at) / denom, 0.0, 1.0)        # 0..1
        dt = span / 1000.0                               # 초 (속도 m/s · dt = 위치단위)
        a_rad = np.radians(arot); b_rad = np.radians(brot)
        v0x = aspd * np.cos(a_rad); v0y = aspd * np.sin(a_rad)
        v1x = bspd * np.cos(b_rad); v1y = bspd * np.sin(b_rad)
        s2 = sp * sp; s3 = s2 * sp
        h00 = 2 * s3 - 3 * s2 + 1
        h10 = s3 - 2 * s2 + sp
        h01 = -2 * s3 + 3 * s2
        h11 = s3 - s2
        xs = h00 * ax + h10 * dt * v0x + h01 * bx + h11 * dt * v1x
        ys = h00 * ay + h10 * dt * v0y + h01 * by + h11 * dt * v1y
        # 회전: 각도(도) 최단경로 보간 (170°→-170° wrap 에서 한 바퀴 안 돌게)
        drot = ((brot - arot + 180.0) % 360.0) - 180.0
        rots = arot + drot * sp

        # === USD attribute 로 일괄 flush (numpy → Vt, 차량당 Gf 객체 생성 없음) ===
        pts = np.empty((n, 3), dtype=np.float32)
        pts[:, 0] = xs; pts[:, 1] = ys; pts[:, 2] = VEHICLE_Z
        # protoIndex = JobState 값(범위 밖이면 IDLE). dict 조회라 이 부분만 차량별.
        proto = np.fromiter(
            (job.get(i, DEFAULT_JOB_STATE) for i in ids), dtype=np.int32, count=n
        )
        np.putmask(proto, (proto < 0) | (proto >= NUM_JOB_STATES), DEFAULT_JOB_STATE)
        # Z축 회전 쿼터니언: (w=cos(θ/2), 0, 0, z=sin(θ/2)), θ 는 도→라디안.
        # 삼각함수는 일괄, Gf.Quath 생성만 남김 (메모리 레이아웃 안전한 명시 생성자).
        half = np.radians(rots) * 0.5
        qw = np.cos(half); qz = np.sin(half)
        quats = Vt.QuathArray([Gf.Quath(float(w), 0.0, 0.0, float(z))
                               for w, z in zip(qw, qz)])

        self._instancer.CreatePositionsAttr().Set(Vt.Vec3fArray.FromNumpy(pts))
        self._instancer.CreateOrientationsAttr().Set(quats)
        self._instancer.CreateProtoIndicesAttr().Set(Vt.IntArray.FromNumpy(proto))

        # 버퍼 트림 — rt 보다 충분히 과거 샘플 제거(왼쪽 앵커 1개는 보존)
        cutoff = rt - 2.0 * RENDER_DELAY_MS
        with self._lock:
            for vid, s in self._buf.items():
                keep = 0
                for k in range(len(s)):
                    if s[k][0] <= cutoff:
                        keep = k
                    else:
                        break
                if keep > 0:
                    self._buf[vid] = s[keep:]
