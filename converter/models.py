"""
models.py — 장비 타입별 3D 모델 빌더 라이브러리 (전부 인스턴싱).

아키텍처: 맵(station_body.map)은 device 의 타입/모델 이름만 지정, 형상은 여기 빌더가 그림.

성능: 장비는 "박스 복붙"이라 메쉬를 일일이 굽지 않고 **Instances 수집기**에 박스
요청만 쌓아둔다. convert 가 끝에서 PointInstancer 1개(= THREE.InstancedMesh)로 전부 그림.
본체/포트/창문/신호등/밴딩/행어/**테두리 빔**까지 전부 박스 → 통째로 인스턴싱.
(테두리도 곡선 튜브 대신 얇은 직육면체 빔이라 인스턴싱됨.)

빌더 시그니처: build(coll, dev)
  dev: {center(x,y), dir(ux,uy), outward(ox,oy), width, depth, height, port_xy:[(x,y)], ...}
  coll: Instances 수집기. coll.box(mat_key, center3, yaw, size3)
박스는 대칭이라 위치 + yaw(Z회전) + per-instance scale 이면 충분 (outward 부호 무관).

형상은 Downloads 레퍼런스(eq1=EFEM, lps.png=LPS, ntb.png=NTB, 스토커, OHB)를 박스로 근사.
"""
import math

import geometry as geo


def make_palette(stage, ub):
    """공유 머티리얼 1회 생성 → 프로토타입 큐브에 바인딩됨."""
    P = {}

    def m(name, **kw):
        P[name] = ub.add_preview_material(stage, f"/World/Looks/{name}", **kw)
        return P[name]

    m("body_sage", diffuse=geo.EQ_BODY_COLOR, metallic=0.1, roughness=0.5)
    m("body_white", diffuse=(0.87, 0.88, 0.89), metallic=0.05, roughness=0.45)
    m("edge", diffuse=(0.28, 0.30, 0.34), metallic=0.3, roughness=0.5)  # 테두리 빔(회색)
    m("metal", diffuse=(0.55, 0.57, 0.60), metallic=0.65, roughness=0.4)
    # OHB 거치대: 실제처럼 어두운 철제 프레임 (다크 스틸 회청색).
    #   따뜻한 흰/세이지 장비와 색온도 달라 겹쳐도 구분, 공장 느낌 유지.
    m("ohb", diffuse=(0.30, 0.34, 0.41), metallic=0.45, roughness=0.4)
    m("port", diffuse=geo.EQ_PORT_COLOR, metallic=0.2, roughness=0.5)
    # 유리: 투명(refraction)은 RTX 에서 매우 비쌈 → 불투명 청색 패널로 (창문처럼만 보이게)
    m("glass", diffuse=(0.50, 0.66, 0.78), metallic=0.1, roughness=0.18)
    m("screen", diffuse=(0.07, 0.09, 0.13), metallic=0.3, roughness=0.3)
    # 신호등: emissive(=광원) 빼고 밝은 diffuse 만 → GI 비용 0, 색은 유지
    m("sig_r", diffuse=(0.95, 0.15, 0.15), metallic=0.0, roughness=0.4)
    m("sig_y", diffuse=(0.97, 0.82, 0.15), metallic=0.0, roughness=0.4)
    m("sig_g", diffuse=(0.15, 0.85, 0.25), metallic=0.0, roughness=0.4)
    return P


class Instances:
    """박스 인스턴스 수집기 → convert 가 PointInstancer 1개로 굽는다."""
    def __init__(self):
        self.items = []   # (mat_key, (cx,cy,cz), yaw_rad, (sx,sy,sz))

    def box(self, mat, center, yaw, size):
        self.items.append((mat, center, yaw, size))


def _yaw(u):
    return math.atan2(u[1], u[0])


# ----------------------------------------------------------------------------
# 내부 헬퍼 (전부 coll.box 인스턴스만 emit)
# ----------------------------------------------------------------------------
def _edge_frame(coll, center, u, o, half, ew, mat="edge"):
    """직육면체 12 모서리를 얇은 빔(박스)으로 = 테두리. 본체보다 살짝(E) 크게 띄워
    바깥면이 본체면보다 약간 proud → z-fighting 없이 윗면 테두리까지 보임. 인스턴싱됨."""
    cx, cy, cz = center
    E = 0.05                       # 본체보다 키워 z-fight 회피 + 위아래좌우 테두리 또렷
    hw, hd, hh = half[0] + E, half[1] + E, half[2] + E
    ux, uy = u
    ox, oy = o
    yaw = _yaw(u)
    ih = ew / 2.0
    for sy in (-1, 1):             # u 방향 빔 4개
        for sz in (-1, 1):
            c = (cx + ox * (hd - ih) * sy, cy + oy * (hd - ih) * sy, cz + (hh - ih) * sz)
            coll.box(mat, c, yaw, (2 * hw, ew, ew))
    for sx in (-1, 1):            # outward 방향 빔 4개
        for sz in (-1, 1):
            c = (cx + ux * (hw - ih) * sx, cy + uy * (hw - ih) * sx, cz + (hh - ih) * sz)
            coll.box(mat, c, yaw, (ew, 2 * hd, ew))
    for sx in (-1, 1):            # 수직 빔 4개
        for sy in (-1, 1):
            c = (cx + ux * (hw - ih) * sx + ox * (hd - ih) * sy,
                 cy + uy * (hw - ih) * sx + oy * (hd - ih) * sy, cz)
            coll.box(mat, c, yaw, (ew, ew, 2 * hh))


def _edge_rect(coll, center, u, o, hw, hd, ew, mat="edge"):
    """수평 사각 테두리(4 변 빔), inset 으로 코너 flush. OHB footprint."""
    cx, cy, cz = center
    ux, uy = u
    ox, oy = o
    yaw = _yaw(u)
    ih = ew / 2.0
    for sy in (-1, 1):
        coll.box(mat, (cx + ox * (hd - ih) * sy, cy + oy * (hd - ih) * sy, cz),
                 yaw, (2 * hw, ew, ew))
    for sx in (-1, 1):
        coll.box(mat, (cx + ux * (hw - ih) * sx, cy + uy * (hw - ih) * sx, cz),
                 yaw, (ew, 2 * hd, ew))


def _body(coll, dev, mat="body_white", htop=None):
    """본체 박스 + 굵은 테두리 빔. 반환: 기하 정보."""
    u, o = dev["dir"], dev["outward"]
    h = dev["height"] if htop is None else htop
    hw, hd, hh = dev["width"] / 2.0, dev["depth"] / 2.0, h / 2.0
    cx, cy = dev["center"]
    yaw = _yaw(u)
    coll.box(mat, (cx, cy, hh), yaw, (2 * hw, 2 * hd, 2 * hh))
    _edge_frame(coll, (cx, cy, hh), u, o, (hw, hd, hh), geo.EQ_EDGE_WIDTH)
    return hw, hd, hh, cx, cy, u, o, yaw


def _loadports(coll, dev, z=None, mat="port", half=None):
    """앞면(통로쪽)으로 돌출한 로드포트 모듈 인스턴스."""
    u, o = dev["dir"], dev["outward"]
    yaw = _yaw(u)
    ph = half or geo.EQ_PORT_HALF
    pz = geo.EQ_PORT_Z if z is None else z
    for (px, py) in dev["port_xy"]:
        pc = (px - o[0] * geo.EQ_PORT_PROTRUDE,
              py - o[1] * geo.EQ_PORT_PROTRUDE, pz)
        coll.box(mat, pc, yaw, (2 * ph[0], 2 * ph[1], 2 * ph[2]))


def _signal_tower(coll, base, yaw, pole_h=0.25):
    """신호등 타워: 얇은 기둥 + R/Y/G 램프 3단. 낮게(OHB z=3.0 에 안 걸리게)."""
    px, py, pz = base
    coll.box("metal", (px, py, pz + pole_h / 2.0), yaw, (0.07, 0.07, pole_h))
    top = pz + pole_h
    for i, col in enumerate(("sig_r", "sig_y", "sig_g")):
        coll.box(col, (px, py, top + 0.05 + i * 0.09), yaw, (0.1, 0.1, 0.08))


def _front_xy(cx, cy, o, hd, extra=0.01):
    return cx - o[0] * (hd + extra), cy - o[1] * (hd + extra)


# ----------------------------------------------------------------------------
# 모델 빌더 — build(coll, dev)
# ----------------------------------------------------------------------------
def build_efem(coll, dev):
    """EFEM (eq1): 세이지 본체 + 앞 하단 돌출 로드포트."""
    _body(coll, dev, mat="body_sage")
    _loadports(coll, dev)


def build_lps(coll, dev):
    """LPS (lps.png): 흰 본체 + 유리창 + 제어스크린 + 신호등 타워 2개 + 로드포트."""
    hw, hd, hh, cx, cy, u, o, yaw = _body(coll, dev, "body_white")
    fx, fy = _front_xy(cx, cy, o, hd)
    coll.box("glass", (fx, fy, hh * 1.25), yaw, (2 * hw * 0.8, 0.04, 2 * hh * 0.4))
    coll.box("screen", (fx, fy, hh * 1.55), yaw, (0.5, 0.06, 0.36))
    for sgn in (-1, 1):
        bx = cx + u[0] * sgn * (hw - 0.15) - o[0] * (hd - 0.15)
        by = cy + u[1] * sgn * (hw - 0.15) - o[1] * (hd - 0.15)
        _signal_tower(coll, (bx, by, 2 * hh), yaw)
    _loadports(coll, dev)


def build_ntb(coll, dev):
    """NTB (ntb.png): 흰 버퍼 + 앞면 창문 그리드(2x2) + 신호등 1개 + 로드포트."""
    hw, hd, hh, cx, cy, u, o, yaw = _body(coll, dev, "body_white")
    fx, fy = _front_xy(cx, cy, o, hd)
    for sgn in (-1, 1):
        for zf in (0.62, 1.32):
            wx = fx + u[0] * sgn * hw * 0.42
            wy = fy + u[1] * sgn * hw * 0.42
            coll.box("glass", (wx, wy, hh * zf), yaw, (2 * hw * 0.30, 0.04, 2 * hh * 0.28))
    bx = cx + u[0] * (hw - 0.15) - o[0] * (hd - 0.15)
    by = cy + u[1] * (hw - 0.15) - o[1] * (hd - 0.15)
    _signal_tower(coll, (bx, by, 2 * hh), yaw)
    _loadports(coll, dev)


def build_stocker(coll, dev):
    """STOCKER (STK): 위아래 길쭉한 흰 타워 + 가로 메탈 밴딩 + 앞 하단 작은 로드포트."""
    hw, hd, hh, cx, cy, u, o, yaw = _body(coll, dev, "body_white")
    bands = 4
    for i in range(1, bands):
        z = 2 * hh * i / bands
        coll.box("metal", (cx, cy, z), yaw, (2 * hw * 1.02, 2 * hd * 1.02, 0.08))
    _loadports(coll, dev, z=0.4)


def build_ohb_rack(coll, dev):
    """OHB_RACK: 바닥 사각 테두리 + port 자리마다 칸막이(슬롯 구분) + 얇은 행어 2개.
    청록색으로 다른 장비와 겹쳐도 보이게. 책장처럼 안 채움."""
    u, o = dev["dir"], dev["outward"]
    yaw = _yaw(u)
    hw, hd = dev["width"] / 2.0, dev["depth"] / 2.0
    cx, cy = dev["center"]
    z = geo.OHB_Z
    ew = geo.OHB_EDGE_WIDTH
    _edge_rect(coll, (cx, cy, z), u, o, hw, hd, ew, mat="ohb")
    # port 자리마다 가로 칸막이(깊이 방향 빔) → 슬롯으로 나뉨
    for (px, py) in dev["port_xy"]:
        coll.box("ohb", (px, py, z), yaw, (ew, 2 * hd, ew))
    # 얇은 행어 2개
    hz = (z + geo.OHB_HANGER_TOP) / 2.0
    sh = geo.OHB_HANGER_TOP - z
    for sgn in (-1, 1):
        hx = cx + u[0] * sgn * (hw - 0.1)
        hy = cy + u[1] * sgn * (hw - 0.1)
        coll.box("ohb", (hx, hy, hz), yaw, (0.05, 0.05, sh))


MODEL_BUILDERS = {
    "EFEM": build_efem,
    "LPS": build_lps,
    "NTB": build_ntb,
    "STOCKER": build_stocker,
    "OHB_RACK": build_ohb_rack,
}


def build_device(coll, dev):
    """dev['model'] 빌더 호출 (없으면 EFEM 폴백). 전부 coll 에 박스 인스턴스로."""
    MODEL_BUILDERS.get(dev.get("model"), build_efem)(coll, dev)
