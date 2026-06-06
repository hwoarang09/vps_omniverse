"""
트랙 지오메트리 — VPS 의 points_calculator + EdgeRenderer 매트릭스 로직을 파이썬으로 번역.

VPS 흐름 (출력만 USD 로 교체):
  edges.cfg row
    -> EdgePointsCalculator.calculateRenderingPoints  (rail_type 라우팅)
       - LINEAR     : StraightPointsCalculator.calculate            -> [from, to]
       - CURVE_*    : SimpleCurveEdgePointsCalculator -> EdgePathGenerator.generate
       - S_CURVE    : SCurvePointsCalculator
    -> EdgeRenderer setLinear/CurveEdgeMatrices  (점들 -> 평면 인스턴스 변환)

좌표: editor_x/y/z -> world x/y/z (identity, Z-up). VPS 와 동일.
평면: THREE.PlaneGeometry(1,1) = XY 평면 1x1, 법선 +Z.
  LINEAR  세그먼트 스케일 = (length,   0.25, 1)
  CURVE   세그먼트 스케일 = (length*2, 0.25, 1)   # 곡선 조각 겹침으로 틈 메움 (VPS 그대로)
  회전    = Z축 atan2(dy, dx)
"""
import math
from mapio import Node

DEFAULT_SEGMENTS = 100
RAIL_WIDTH = 0.25                      # EdgeRenderer scale.y
CURVE_LEN_MULT = 2.0                   # 곡선 세그먼트 length*2
MIN_SEG_LEN = 1e-4                     # 0 길이 degenerate 평면 스킵

CURVE_CONFIGS = {                      # _SimpleCurveEdgePointsCalculator.CURVE_CONFIGS
    "CURVE_90":  {"waypointCount": 4, "angles": [90],     "zOffset": 0.001},
    "CURVE_180": {"waypointCount": 4, "angles": [180],    "zOffset": 0.001},
    "CURVE_CSC": {"waypointCount": 6, "angles": [90, 90], "zOffset": 0.003},
}


# ----------------------------------------------------------------------------
# 거리 유틸 (utils/geometry/calculateDistance.ts)
# ----------------------------------------------------------------------------
def straight_distance(a: Node, b: Node):
    return math.hypot(b.editor_x - a.editor_x, b.editor_y - a.editor_y,
                      b.editor_z - a.editor_z)


def curve_length(radius, angle_deg):
    return abs(radius) * (angle_deg * math.pi / 180.0)


# ----------------------------------------------------------------------------
# DirectionUtils (_DirectionUtils.ts)  — 점은 (x,y,z) 튜플로 반환
# ----------------------------------------------------------------------------
def get_line_direction(a: Node, b: Node):
    dx = b.editor_x - a.editor_x
    dy = b.editor_y - a.editor_y
    if abs(dx) > abs(dy):
        return "+x" if dx > 0 else "-x"
    return "+y" if dy > 0 else "-y"


def _arc_center(b: Node, c: Node, from_dir, radius):
    cx, cy, cz = b.editor_x, b.editor_y, b.editor_z
    if from_dir in ("+x", "-x"):
        sign = 1 if c.editor_y > b.editor_y else -1
        cy += sign * radius
    else:
        sign = 1 if c.editor_x > b.editor_x else -1
        cx += sign * radius
    return cx, cy, cz


def _curve_rotation_direction(straight_dir, start: Node, end: Node):
    dx = end.editor_x - start.editor_x
    dy = end.editor_y - start.editor_y
    if straight_dir == "+x":
        return 1 if dy > 0 else -1
    if straight_dir == "-x":
        return 1 if dy < 0 else -1
    if straight_dir == "+y":
        return 1 if dx < 0 else -1
    if straight_dir == "-y":
        return 1 if dx > 0 else -1
    return 1


def calculate_curve_area_points(start: Node, end: Node, straight_dir,
                                radius=0.5, rotation_deg=90, segments=16):
    cx, cy, _cz = _arc_center(start, end, straight_dir, radius)
    start_angle = math.atan2(start.editor_y - cy, start.editor_x - cx)
    rot_dir = _curve_rotation_direction(straight_dir, start, end)
    rot_rad = rotation_deg * math.pi / 180.0
    pts = []
    for i in range(segments + 1):
        t = i / segments
        angle = start_angle + rot_rad * rot_dir * t
        x = cx + math.cos(angle) * radius
        y = cy + math.sin(angle) * radius
        z = start.editor_z + (end.editor_z - start.editor_z) * t
        pts.append((x, y, z))
    return pts


# ----------------------------------------------------------------------------
# StraightPointsCalculator (_StraightPointsCalculator.ts)
# ----------------------------------------------------------------------------
def straight_two_points(from_node: Node, to_node: Node):
    return [(from_node.editor_x, from_node.editor_y, from_node.editor_z),
            (to_node.editor_x, to_node.editor_y, to_node.editor_z)]


def straight_segmented_points(a: Node, b: Node, segments):
    if segments < 2:
        segments = 2
    pts = []
    for i in range(segments):
        t = i / (segments - 1)
        pts.append((a.editor_x + (b.editor_x - a.editor_x) * t,
                    a.editor_y + (b.editor_y - a.editor_y) * t,
                    a.editor_z + (b.editor_z - a.editor_z) * t))
    return pts


# ----------------------------------------------------------------------------
# EdgePathGenerator (EdgePathGenerator.ts)
# seg defs: {"type":"STRAIGHT","from":Node,"to":Node} |
#           {"type":"CURVE","from":Node,"to":Node,"radius":r,"angle":a}
# ----------------------------------------------------------------------------
def edge_path_generate(seg_defs, total_segments, z_offset):
    lengths = [straight_distance(s["from"], s["to"]) if s["type"] == "STRAIGHT"
               else curve_length(s["radius"], s["angle"]) for s in seg_defs]
    total = sum(lengths)
    if total <= 0:
        return []
    counts = [max(1, round(total_segments * (L / total))) for L in lengths]
    diff = total_segments - sum(counts)
    if diff != 0:
        counts[lengths.index(max(lengths))] += diff

    all_pts = []
    last_dir = None
    for s, cnt in zip(seg_defs, counts):
        if s["type"] == "STRAIGHT":
            all_pts.extend(straight_segmented_points(s["from"], s["to"], cnt))
            last_dir = get_line_direction(s["from"], s["to"])
        else:
            d = last_dir if last_dir is not None else get_line_direction(s["from"], s["to"])
            all_pts.extend(calculate_curve_area_points(
                s["from"], s["to"], d, s["radius"], s["angle"], cnt))
    return [(x, y, z + z_offset) for (x, y, z) in all_pts]


# ----------------------------------------------------------------------------
# SimpleCurveEdgePointsCalculator (_SimpleCurveEdgePointsCalculator.ts)
# ----------------------------------------------------------------------------
def simple_curve_points(edge, nodes, total_segments=DEFAULT_SEGMENTS):
    cfg = CURVE_CONFIGS.get(edge.vos_rail_type)
    if not cfg:
        return []
    resolved = [nodes.get(n) for n in edge.waypoints]
    if any(n is None for n in resolved):
        return []
    seg_defs = []
    idx = 0
    seg_defs.append({"type": "STRAIGHT", "from": resolved[idx], "to": resolved[idx + 1]})
    idx += 1
    for angle in cfg["angles"]:
        seg_defs.append({"type": "CURVE", "from": resolved[idx], "to": resolved[idx + 1],
                         "radius": edge.radius, "angle": angle})
        idx += 1
        seg_defs.append({"type": "STRAIGHT", "from": resolved[idx], "to": resolved[idx + 1]})
        idx += 1
    return edge_path_generate(seg_defs, total_segments, cfg["zOffset"])


# ----------------------------------------------------------------------------
# SCurvePointsCalculator (_SCurvePointsCalculator.ts)
# ----------------------------------------------------------------------------
def s_curve_points(edge, nodes, total_segments=DEFAULT_SEGMENTS):
    rotation = 43
    wp = edge.waypoints
    if len(wp) < 6:
        return []
    n = [nodes.get(name) for name in wp[:6]]
    if any(x is None for x in n):
        return []
    n1, n2, n3, n4, n5, n6 = n
    r = edge.radius
    lengths = [straight_distance(n1, n2), curve_length(r, rotation),
               straight_distance(n3, n4), curve_length(r, rotation),
               straight_distance(n5, n6)]
    total = sum(lengths)
    if total <= 0:
        return []
    counts = [max(1, round(total_segments * (L / total))) for L in lengths]
    diff = total_segments - sum(counts)
    if diff != 0:
        counts[lengths.index(max(lengths))] += diff
    s1, s2, s3, s4, s5 = counts

    forward = []
    forward.extend(straight_segmented_points(n1, n2, s1))
    forward.extend(calculate_curve_area_points(n2, n3, get_line_direction(n1, n2), r, rotation, s2))
    forward.extend(straight_segmented_points(n3, n4, s3)[:-1])   # 마지막 점 제외

    backward = []
    backward.extend(straight_segmented_points(n6, n5, s5))
    backward.extend(calculate_curve_area_points(n5, n4, get_line_direction(n6, n5), r, rotation, s4))
    backward.reverse()

    z_off = 0.001
    return [(x, y, z + z_off) for (x, y, z) in (forward + backward)]


# ----------------------------------------------------------------------------
# 라우터 (EdgePointsCalculator.calculateRenderingPoints)
# ----------------------------------------------------------------------------
# 곡선 타입별 분할 수 (100 → 적응적. 작은 반경 곡선은 8~16 이면 충분히 매끄러움)
RAIL_CURVE_SEGS = {"CURVE_90": 40, "CURVE_180": 40, "CURVE_CSC": 40, "S_CURVE": 36}


def edge_points(edge, nodes):
    t = edge.vos_rail_type
    if t in ("CURVE_90", "CURVE_180", "CURVE_CSC"):
        return simple_curve_points(edge, nodes, total_segments=RAIL_CURVE_SEGS[t])
    if t == "S_CURVE":
        return s_curve_points(edge, nodes, total_segments=RAIL_CURVE_SEGS["S_CURVE"])
    # LINEAR + default
    fn, tn = nodes.get(edge.from_node), nodes.get(edge.to_node)
    if fn is None or tn is None:
        return []
    return straight_two_points(fn, tn)


# ----------------------------------------------------------------------------
# EdgeRenderer 매트릭스 (EdgeRenderer.tsx) -> rail 인스턴스 변환 리스트
#   반환: [(pos(x,y,z), yaw_rad, scale(sx,sy,sz)), ...]
# ----------------------------------------------------------------------------
def _segment_instance(p0, p1, length_mult):
    length = math.dist(p0, p1)
    if length < MIN_SEG_LEN:
        return None
    cx = (p0[0] + p1[0]) / 2
    cy = (p0[1] + p1[1]) / 2
    cz = (p0[2] + p1[2]) / 2
    yaw = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    return ((cx, cy, cz), yaw, (length * length_mult, RAIL_WIDTH, 1.0))


def rail_instances(edge, nodes):
    """한 엣지를 평면 인스턴스 변환 리스트로. (LINEAR=1개, 곡선=세그먼트별)"""
    pts = edge_points(edge, nodes)
    if len(pts) < 2:
        return []
    if edge.vos_rail_type in ("LINEAR", "") or edge.vos_rail_type not in (
            "CURVE_90", "CURVE_180", "CURVE_CSC", "S_CURVE"):
        inst = _segment_instance(pts[0], pts[-1], 1.0)   # LINEAR: length*1
        return [inst] if inst else []
    out = []
    for p0, p1 in zip(pts[:-1], pts[1:]):                # 곡선: length*2
        inst = _segment_instance(p0, p1, CURVE_LEN_MULT)
        if inst:
            out.append(inst)
    return out


def all_rail_instances(edges, nodes):
    out = []
    for e in edges:
        out.extend(rail_instances(e, nodes))
    return out


# ----------------------------------------------------------------------------
# 2줄 레일 + 가로 침목 (실제 OHT 트랙 느낌)
# ----------------------------------------------------------------------------
RAIL_GAUGE = 0.4          # 두 레일 간격
RAIL_RAIL_W = 0.1         # 각 레일 폭 (얇게)
RAIL_H = 0.14             # 레일 높이
RAIL_TIE_SPACING = 1.6    # 가로 침목 간격
RAIL_TIE_W = 0.07         # 침목 폭
RAIL_SEG_MULT = 1.6       # 조각을 길게 겹쳐 연속 리본으로(곡선 툭툭 끊김 방지). densify(0.5m)
                          # 덕에 끝 overhang 은 작음(~0.18m, 분기 hide 가 처리)


def _perp_offsets(pts):
    """폴리라인 각 점의 단위 수직벡터 (로컬 접선 기준 90도). 곡선 좌우 오프셋용."""
    n = len(pts)
    res = []
    for i in range(n):
        if i == 0:
            tx, ty = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
        elif i == n - 1:
            tx, ty = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
        else:
            tx, ty = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        L = math.hypot(tx, ty) or 1.0
        res.append((-ty / L, tx / L))
    return res


def _seg_box(p0, p1, width, mult=RAIL_SEG_MULT):
    """두 점 사이 박스 세그먼트 (pos, yaw, scale)."""
    length = math.dist(p0, p1)
    if length < MIN_SEG_LEN:
        return None
    c = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, (p0[2] + p1[2]) / 2)
    yaw = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    return (c, yaw, (length * mult, width, RAIL_H))


def _edge_clean_points(e, nodes):
    pts = edge_points(e, nodes)
    clean = []
    for p in pts:
        if not clean or math.dist(clean[-1], p) > 1e-6:
            clean.append(p)
    return clean


def _arc_total(pts):
    return sum(math.dist(pts[i - 1], pts[i]) for i in range(1, len(pts)))


def _turn_sign(pts):
    """곡선 회전방향: +1=CCW(좌회전, 안쪽=left/+perp), -1=CW(우회전)."""
    s = 0.0
    for i in range(1, len(pts) - 1):
        ax, ay = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
        bx, by = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
        s += ax * by - ay * bx
    return 1.0 if s >= 0 else -1.0


def _in_intervals(t, intervals):
    return any(a <= t <= b for (a, b) in intervals)


def _densify(pts, max_len):
    """폴리라인을 max_len 이하 간격으로 잘게 (직선도 끝부분 세그먼트가 개별로 숨겨지게)."""
    out = [pts[0]]
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        d = math.dist(a, b)
        n = max(1, int(math.ceil(d / max_len)))
        for k in range(1, n + 1):
            t = k / n
            out.append((a[0] + (b[0] - a[0]) * t,
                        a[1] + (b[1] - a[1]) * t,
                        a[2] + (b[2] - a[2]) * t))
    return out


def _pt_seg_dist(px, py, ax, ay, bx, by):
    """점(px,py)에서 선분 (a,b) 까지 거리."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / L2
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + dx * t), py - (ay + dy * t))


RAIL_DRAW_MAXLEN = 0.5    # 그릴 때 레일 세그먼트 최대 길이(겹침 끝부분 개별 숨김용)
RAIL_TRIM_FINE = 0.1      # trim 계산용 정밀 샘플 간격
RAIL_CAND_NEAR = 3.5      # 이웃 직선영역 레일을 모으는 노드 반경(국소성)
# "딱 겹치는" 판정 = 곡선 레일이 이웃의 '실제 직선 레일' 위에 얹힌 정도(rail-to-rail).
# rail 폭(0.1) 근처. corridor(중심선±gauge/2) 가 아니라 그려진 레일선과의 거리라,
# 곡선 outer 가 corridor 한가운데를 가로지르는 부분은 안 잡힘(=과지움 방지).
RAIL_RAIL_OVERLAP = RAIL_RAIL_W * 1.2


_CURVE_TYPES = ("CURVE_90", "CURVE_180", "CURVE_CSC", "S_CURVE")
# 디버그 색 클래스: 직선 edge / 곡선 edge 의 직선영역(lead-in·out) / 곡선영역(호)
RAIL_CLS_GREEN = "green"   # LINEAR edge
RAIL_CLS_PINK = "pink"     # 곡선 edge 의 직선 구간
RAIL_CLS_RED = "red"       # 곡선 edge 의 호 구간
RAIL_DEBUG_KEYS = (RAIL_CLS_GREEN, RAIL_CLS_PINK, RAIL_CLS_RED)
RAIL_ARC_TURN_DEG = 1.0    # 정점에서 이 각 이상 꺾이면 '호'로 분류


def _arc_t_intervals(clean, thr_deg=RAIL_ARC_TURN_DEG):
    """곡선 edge 의 원본 중심선에서 '호' 구간을 정규화 t-인터벌로.
    각 정점의 꺾임각이 thr_deg 초과면 그 정점에 인접한 두 세그먼트를 호로 표시.
    (densify 전 원본 정점으로 계산 — chord 꺾임이 직선/호를 가름)."""
    n = len(clean)
    if n < 3:
        return []
    cum = [0.0]
    for i in range(1, n):
        cum.append(cum[-1] + math.dist(clean[i - 1], clean[i]))
    total = cum[-1] or 1.0
    seg_arc = [False] * (n - 1)
    for i in range(1, n - 1):
        ax, ay = clean[i][0] - clean[i - 1][0], clean[i][1] - clean[i - 1][1]
        bx, by = clean[i + 1][0] - clean[i][0], clean[i + 1][1] - clean[i][1]
        la = math.hypot(ax, ay) or 1.0
        lb = math.hypot(bx, by) or 1.0
        cosv = max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))
        if math.degrees(math.acos(cosv)) > thr_deg:
            seg_arc[i - 1] = True
            seg_arc[i] = True
    ivs, i = [], 0
    while i < len(seg_arc):
        if seg_arc[i]:
            j = i
            while j + 1 < len(seg_arc) and seg_arc[j + 1]:
                j += 1
            ivs.append((cum[i] / total, cum[j + 1] / total))
            i = j + 1
        else:
            i += 1
    return ivs


def _edge_rail_seg_list(e, nodes, gauge=RAIL_GAUGE, fine=RAIL_TRIM_FINE):
    """edge 의 좌/우 레일을 fine 간격 세그먼트로.
    반환 {'L':[seg...], 'R':[seg...]}, seg=(x0,y0,x1,y1, tlo, thi, is_arc)."""
    g = gauge / 2.0
    clean = _edge_clean_points(e, nodes)
    cl = _densify(clean, fine)
    out = {"L": [], "R": []}
    if len(cl) < 2:
        return out
    arc = _arc_t_intervals(clean) if e.vos_rail_type in _CURVE_TYPES else []
    perp = _perp_offsets(cl)
    cum = [0.0]
    for i in range(1, len(cl)):
        cum.append(cum[-1] + math.dist(cl[i - 1], cl[i]))
    total = cum[-1] or 1.0
    for sgn, k in ((1, "L"), (-1, "R")):
        poly = [(cl[i][0] + perp[i][0] * g * sgn, cl[i][1] + perp[i][1] * g * sgn)
                for i in range(len(cl))]
        for i in range(len(poly) - 1):
            tlo, thi = cum[i] / total, cum[i + 1] / total
            is_arc = _in_intervals((tlo + thi) / 2.0, arc)
            out[k].append((poly[i][0], poly[i][1], poly[i + 1][0], poly[i + 1][1],
                           tlo, thi, is_arc))
    return out


def _runs_to_intervals_seglist(segs, hid):
    """seg 리스트(각 (.., tlo, thi, ..))와 hid bool 배열 → 연속 True 구간 정규화 인터벌."""
    ivs, i, n = [], 0, len(segs)
    while i < n:
        if hid[i]:
            j = i
            while j + 1 < n and hid[j + 1]:
                j += 1
            ivs.append([round(segs[i][4], 4), round(segs[j][5], 4)])
            i = j + 1
        else:
            i += 1
    return ivs


def _outer_rail_key(clean):
    """곡선 회전방향으로 '바깥(outer)' 레일 키. CCW(+)→ outer=R, CW(-)→ outer=L.
    (_perp 는 진행방향 왼쪽=+ → L. 좌회전이면 안쪽이 L 이므로 바깥은 R.)"""
    return "R" if _turn_sign(clean) > 0 else "L"


RAIL_CSC_ARC_HIDE = 0.7   # CSC 각 90도 호에서 '노드쪽' 이 비율만큼 outer 레일 숨김


def _merge_intervals(ivs):
    """겹치거나 인접한 [a,b] 인터벌 병합."""
    if not ivs:
        return []
    s = sorted([list(v) for v in ivs])
    out = [s[0]]
    for a, b in s[1:]:
        if a <= out[-1][1] + 1e-6:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [[round(a, 4), round(b, 4)] for a, b in out]


def _arc_subpoly(clean, a0, a1):
    """정규화 [a0,a1] 구간의 sub-폴리라인 점들."""
    cum = [0.0]
    for i in range(1, len(clean)):
        cum.append(cum[-1] + math.dist(clean[i - 1], clean[i]))
    total = cum[-1] or 1.0
    return [clean[i] for i in range(len(clean)) if a0 <= cum[i] / total <= a1]


def _arc_turn_sign(clean, a0, a1):
    """호 구간 회전부호 (+1=CCW→outer R, -1=CW→outer L). S커브 호별 outer 판정용."""
    sub = _arc_subpoly(clean, a0, a1)
    return _turn_sign(sub) if len(sub) >= 3 else 1.0


def compute_curve_hide(edges, nodes,
                       types=("CURVE_CSC", "CURVE_90", "CURVE_180", "S_CURVE"),
                       arc_hide=RAIL_CSC_ARC_HIDE):
    """곡선 outer 레일 trim — **각 호(arc)마다 그 호가 '속한'(가까운) edge 끝**이
    합류/분기(degree>=3)면, 그 끝에서 **호 길이의 arc_hide 비율 + 그쪽 lead** 를
    outer 레일에서 숨김. inner·직선은 안 건드림. 호 1개당 1번.
      - CSC: 호 2개 → fn 쪽 호1, tn 쪽 호2 각각.
      - 90 : 호 1개 → 짧은 lead(호가 가까운) 쪽 끝 1번.
      - 180: 호 1개(U턴)를 **apex(중점)에서 반쪽 2개로 쪼개** CSC 처럼 fn/tn 반쪽씩 처리
        (양끝 겹침 제거 + apex 보존). 단일 U턴(degree2)은 자동 제외.
      - 비율은 '곡선영역(arc)' 기준이라 타입 공유. outer=_turn_sign 판정.
    반환 {edge:(left_iv, right_iv)} — outer 쪽만 채워짐."""
    node_deg = {}
    for e in edges:
        node_deg[e.from_node] = node_deg.get(e.from_node, 0) + 1
        node_deg[e.to_node] = node_deg.get(e.to_node, 0) + 1
    out = {}
    for e in edges:
        if e.vos_rail_type not in types:
            continue
        clean = _edge_clean_points(e, nodes)
        arcs = _arc_t_intervals(clean)
        if not arcs:
            continue
        if e.vos_rail_type == "CURVE_180" and len(arcs) == 1:
            a0, a1 = arcs[0]               # 180 단일 호 → apex 에서 반쪽 2개로
            mid = (a0 + a1) / 2.0
            arcs = [(a0, mid), (mid, a1)]
        hide = {"L": [], "R": []}
        is_s = e.vos_rail_type == "S_CURVE"
        for a0, a1 in arcs:
            # outer 호별 판정 (S 는 호 2개가 반대방향 → 서로 다른 레일).
            ao = "R" if _arc_turn_sign(clean, a0, a1) > 0 else "L"
            #  S: 호 작아 통째(frac 1.0) + degree 게이트 없음(차선변경, 양쪽 호 다).
            #  그 외: 90° 호 기하 overlap 비율 arc_hide(0.7), 합류/분기(degree>=3)에서만.
            frac = 1.0 if is_s else arc_hide
            if a0 <= (1.0 - a1):                       # fn 에 더 가까움
                if is_s or node_deg.get(e.from_node, 0) >= 3:
                    hide[ao].append([0.0, round(a0 + frac * (a1 - a0), 4)])
            else:                                      # tn 에 더 가까움
                if is_s or node_deg.get(e.to_node, 0) >= 3:
                    hide[ao].append([round(a1 - frac * (a1 - a0), 4), 1.0])
        L, R = _merge_intervals(hide["L"]), _merge_intervals(hide["R"])
        if L or R:
            out[e.edge_name] = (L, R)
    return out


RAIL_CROSS_ANGLE = 30.0   # 직선영역이 이웃 통로를 이 각(도) 이상 '가로지르면' 방해→삭제


def _angle_deg(ax, ay, bx, by):
    """두 방향 사잇각(0=평행, 90=수직). 부호 무시."""
    la = math.hypot(ax, ay) or 1.0
    lb = math.hypot(bx, by) or 1.0
    c = max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))
    return math.degrees(math.acos(abs(c)))


def compute_straight_block_hide(edges, nodes, gauge=RAIL_GAUGE,
                                angle_thr=RAIL_CROSS_ANGLE):
    """곡선 edge 의 **직선영역(lead-in/out)이 다른 통로를 '가로막는'** 부분 삭제.
    겹침(평행, 나란히)은 보존 — veh 가 나란히 가면 안 막으니까. 가로막음 =
    그 직선영역 레일이 이웃(노드 공유) edge 중심선 corridor(±gauge/2) 안 + 그 이웃과
    이루는 각 > angle_thr(가로지름). 양쪽 레일 다. 반환 {edge:(left_iv,right_iv)}."""
    g = gauge / 2.0
    ne = {}
    for e in edges:
        ne.setdefault(e.from_node, []).append(e.edge_name)
        ne.setdefault(e.to_node, []).append(e.edge_name)
    center = {e.edge_name: _densify(_edge_clean_points(e, nodes), RAIL_TRIM_FINE)
              for e in edges}
    out = {}
    for e in edges:
        if e.vos_rail_type not in _CURVE_TYPES:
            continue
        en = e.edge_name
        nbsegs, seen = [], set()
        for nd in (e.from_node, e.to_node):
            for o in ne.get(nd, []):
                if o == en or o in seen:
                    continue
                seen.add(o)
                cl = center[o]
                for i in range(len(cl) - 1):
                    nbsegs.append((cl[i][0], cl[i][1], cl[i + 1][0], cl[i + 1][1]))
        if not nbsegs:
            continue
        rl = _edge_rail_seg_list(e, nodes)
        sides = []
        for k in ("L", "R"):
            segs = rl[k]
            hid = [False] * len(segs)
            for i, s in enumerate(segs):
                if s[6]:                       # 직선영역만 (호는 compute_curve_hide 담당)
                    continue
                mx, my = (s[0] + s[2]) / 2.0, (s[1] + s[3]) / 2.0
                best = min(nbsegs, key=lambda c: _pt_seg_dist(mx, my, c[0], c[1], c[2], c[3]))
                if _pt_seg_dist(mx, my, best[0], best[1], best[2], best[3]) <= g and \
                        _angle_deg(s[2] - s[0], s[3] - s[1],
                                   best[2] - best[0], best[3] - best[1]) > angle_thr:
                    hid[i] = True
            sides.append(_runs_to_intervals_seglist(segs, hid))
        if sides[0] or sides[1]:
            out[en] = (sides[0], sides[1])
    return out


def compute_rail_hide(edges, nodes):
    """곡선 레일 trim 통합: 호 outer(compute_curve_hide) + 직선영역 방해
    (compute_straight_block_hide). edge별 좌/우 인터벌 병합."""
    out = {}
    for d in (compute_curve_hide(edges, nodes),
              compute_straight_block_hide(edges, nodes)):
        for en, (L, R) in d.items():
            if en in out:
                pL, pR = out[en]
                out[en] = (_merge_intervals(pL + L), _merge_intervals(pR + R))
            else:
                out[en] = (list(L), list(R))
    return out


def dual_rail_segments(edges, nodes, hide=None, gauge=RAIL_GAUGE):
    """엣지 중심선을 좌우 ±gauge/2 오프셋 → 2줄 레일 박스. 곡선 바깥=큰 반경.
    hide={edge:(left_iv,right_iv)} 정규화 인터벌이 있으면 그 구간 레일은 안 그림
    (compute_curve_hide 가 계산). 디버그 색 유지. 반환: (rail_segs, []).
    각 rail_seg = (pos, yaw, scale, cls) — cls 는 디버그 색 클래스(RAIL_DEBUG_KEYS).
    (pos/yaw/scale 만 쓰는 호출부는 s[0],s[1],s[2] 그대로 호환)."""
    rails = []
    g = gauge / 2.0
    hide = hide or {}
    for e in edges:
        is_curve = e.vos_rail_type in _CURVE_TYPES
        arc_ivs = _arc_t_intervals(_edge_clean_points(e, nodes)) if is_curve else []
        clean = _densify(_edge_clean_points(e, nodes), RAIL_DRAW_MAXLEN)
        if len(clean) < 2:
            continue
        perp = _perp_offsets(clean)
        cum = [0.0]
        for i in range(1, len(clean)):
            cum.append(cum[-1] + math.dist(clean[i - 1], clean[i]))
        total = cum[-1] or 1.0
        left = [(p[0] + perp[i][0] * g, p[1] + perp[i][1] * g, p[2])
                for i, p in enumerate(clean)]
        right = [(p[0] - perp[i][0] * g, p[1] - perp[i][1] * g, p[2])
                 for i, p in enumerate(clean)]
        lh, rh = hide.get(e.edge_name, ([], []))
        for poly, intervals in ((left, lh), (right, rh)):
            for i in range(len(poly) - 1):
                t = (cum[i] + cum[i + 1]) / 2.0 / total
                if _in_intervals(t, intervals):
                    continue
                if not is_curve:
                    cls = RAIL_CLS_GREEN
                elif _in_intervals(t, arc_ivs):
                    cls = RAIL_CLS_RED
                else:
                    cls = RAIL_CLS_PINK
                s = _seg_box(poly[i], poly[i + 1], RAIL_RAIL_W)
                if s:
                    rails.append((s[0], s[1], s[2], cls))
    return rails, []


# ----------------------------------------------------------------------------
# BasisCurves 용 폴리라인 (세그먼트 인스턴싱 대신 곡선 prim 하나로)
#   edge_points() 가 이미 곡선 샘플 점들을 주므로 그대로 쓰되,
#   세그먼트 이음매에서 생기는 연속 중복점만 제거.
# ----------------------------------------------------------------------------
def rail_polylines(edges, nodes):
    """반환: [[(x,y,z),...], ...]  엣지별 폴리라인 (점 2개 미만은 제외)."""
    out = []
    for e in edges:
        pts = edge_points(e, nodes)
        clean = []
        for p in pts:
            if not clean or math.dist(clean[-1], p) > 1e-6:
                clean.append(p)
        if len(clean) >= 2:
            out.append(clean)
    return out


# ----------------------------------------------------------------------------
# 스테이션 (stationStore.ts calculateStationPosition / renderConfig stations)
# ----------------------------------------------------------------------------
# renderConfig.stations.types[*].zHeight  (대문자 매칭, 없으면 DEFAULT)
STATION_Z = {"EQ": 0.0, "OHB": 3.0, "STK": 2.5}
STATION_Z_DEFAULT = 3.8
# 타입별 색 — 뷰어 가시성 위해 VPS 원색보다 밝고 채도 높게 조정.
# (VPS 원색: EQ #4a4a4a, OHB #9a6a3a, STK #ff2211)
STATION_COLOR = {
    "EQ":  (0.10, 0.85, 0.40),    # 밝은 초록
    "OHB": (1.00, 0.55, 0.00),    # 주황
    "STK": (1.00, 0.12, 0.12),    # 빨강
}
STATION_COLOR_DEFAULT = (0.95, 0.90, 0.20)  # 노랑
STATION_BOX = (0.3, 0.3, 0.1)               # 실제 치수 (renderConfig box width,depth + 0.1 height)
# 뷰어 마커용 큐브. RTX Composer 에선 0.8 이 너무 굵어 포트끼리 뭉쳐 보임.
# 0.4 footprint 로 줄여 인접 포트 분리 + height 0.3 으로 3D 입체감 유지.
# (탑뷰 PNG 만 볼 거면 0.8 로 다시 키워도 됨)
STATION_MARKER_BOX = (0.4, 0.4, 0.3)

# protoIndices 용 순서
STATION_PROTO_ORDER = ["EQ", "OHB", "STK", "DEFAULT"]


def station_z(station_type):
    return STATION_Z.get((station_type or "").upper(), STATION_Z_DEFAULT)


def station_position(st, nodes, edges_by_name):
    """stationStore.calculateStationPosition 1:1 포팅."""
    z = station_z(st.station_type)
    edge = edges_by_name.get(st.nearest_edge)
    if edge is None:
        return (0.0, 0.0, z)
    fn = nodes.get(edge.from_node)
    tn = nodes.get(edge.to_node)
    if fn is None or tn is None:
        return (0.0, 0.0, z)

    barcode_diff = tn.barcode - fn.barcode
    if barcode_diff == 0:
        return (fn.editor_x, fn.editor_y, z)

    t = (st.barcode_x - fn.barcode) / barcode_diff
    x_base = fn.editor_x + (tn.editor_x - fn.editor_x) * t
    y_base = fn.editor_y + (tn.editor_y - fn.editor_y) * t

    offset = st.barcode_y / 1000.0   # mm -> m
    edx = tn.editor_x - fn.editor_x
    edy = tn.editor_y - fn.editor_y
    el = math.hypot(edx, edy)
    xf, yf = x_base, y_base
    if el > 0.001 and offset != 0:
        dirx, diry = edx / el, edy / el
        perpx, perpy = -diry, dirx     # 90deg CCW
        xf = x_base + perpx * offset
        yf = y_base + perpy * offset
    return (xf, yf, z)


# --- EQ 장비(로드포트 클러스터 → device) ---
EQ_BODY_HEIGHT = 2.2          # 장비 본체 높이 (바닥 z=0 에서 위로)
EQ_BODY_DEPTH = 2.5           # 본체 깊이 (통로 바깥방향, 앞뒤로 크게)
EQ_CLUSTER_THRESHOLD = 0.6    # 이 거리(m) 이내 EQ 포트는 같은 device
# 본체는 포트보다 넓게: 포트 라인 양옆에 추가 폭. main(컨트롤/도어 섹션)을 크게,
# minor(포트 쏠린 쪽)를 작게 → 포트가 한쪽으로 쏠려 보임 (EFEM 형태).
EQ_SIDE = 0.5                # 포트 양옆 추가 반폭 (좌우 대칭 → 포트가 몸통 중앙 정렬)
EQ_BODY_MIN_DEPTH = 0.6      # 충돌 clamp 최소 깊이
EQ_MIN_SIDE = 0.1           # 충돌 clamp 시 side 최소
EQ_BODY_COLOR = (0.80, 0.83, 0.73)   # 아이보리+연두 파스텔 (장비 본체)
EQ_PORT_COLOR = (0.50, 0.52, 0.55)   # 차분한 회색 (돌출 로드포트 모듈)
# 로드포트 = 장비 앞면 하단에 붙은 "바닥에 선 낮은 받침" (eq_ohb.png 측면도).
# 공중에 띄우지 않음 — 바닥(z=0)에서 EQ_PORT_HEIGHT 까지. EQ 데이터 z=0 과도 일치.
EQ_PORT_HEIGHT = 0.8          # 받침 높이 (본체 2.0 보다 낮은 단)
EQ_PORT_Z = EQ_PORT_HEIGHT / 2.0     # 바닥에 서도록 중심 = 높이/2
EQ_PORT_HALF = (0.22, 0.30, EQ_PORT_HEIGHT / 2.0)   # half (along/depth/height)
EQ_PORT_PROTRUDE = 0.22       # 본체 앞면보다 통로쪽으로 튀어나온 양 (앞면에서 돌출)
EQ_EDGE_WIDTH = 0.2           # 본체 모서리 회색선 굵기 (포트 폭 ~0.44 의 절반)


def _pca2d(pts):
    """2D 점군 → (중심 C, 장축 단위벡터 u, 단축 단위벡터 n). bay 진행/통로가로 방향."""
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    a = b = c = 0.0
    for x, y in pts:
        dx, dy = x - cx, y - cy
        a += dx * dx
        b += dx * dy
        c += dy * dy
    a /= n
    b /= n
    c /= n
    tr = (a + c) / 2.0
    d = math.sqrt(max(((a - c) / 2.0) ** 2 + b * b, 0.0))
    l1 = tr + d
    if abs(b) > 1e-9:
        vx, vy = b, l1 - a
    else:
        vx, vy = (1.0, 0.0) if a >= c else (0.0, 1.0)
    m = math.hypot(vx, vy) or 1.0
    ux, uy = vx / m, vy / m
    return (cx, cy), (ux, uy), (-uy, ux)


def _bay_axes(edges, nodes):
    """bay 이름 → (C, u, n). 그 bay 에 속한 edge 의 노드/waypoint 좌표로 PCA."""
    pts_by_bay = {}
    for e in edges:
        for nm in set([e.from_node, e.to_node] + list(e.waypoints)):
            nd = nodes.get(nm)
            if nd:
                pts_by_bay.setdefault(e.bay_name, []).append((nd.editor_x, nd.editor_y))
    return {bay: _pca2d(pts) for bay, pts in pts_by_bay.items() if len(pts) >= 2}


def _obb_separated(ca, ua, va, ha, cb, ub, vb, hb):
    """2D OBB(중심,축u,축v,half(hw,hd)) 분리축 검사 → True 면 안 겹침."""
    axes = [ua, va, ub, vb]
    dx, dy = cb[0] - ca[0], cb[1] - ca[1]
    for ax, ay in axes:
        ra = ha[0] * abs(ua[0] * ax + ua[1] * ay) + ha[1] * abs(va[0] * ax + va[1] * ay)
        rb = hb[0] * abs(ub[0] * ax + ub[1] * ay) + hb[1] * abs(vb[0] * ax + vb[1] * ay)
        if abs(dx * ax + dy * ay) > ra + rb + 1e-6:
            return True
    return False


def compute_eq_devices(stations, nodes, edges, thr=EQ_CLUSTER_THRESHOLD,
                       height=EQ_BODY_HEIGHT, depth=EQ_BODY_DEPTH):
    """
    EQ 스테이션을 근접 클러스터(=device) 로 묶고, bay-PCA 로 그릴 방향을 결정.
    - 방향: bay 중심에서 바깥(outward = bay 단축 n, 클러스터가 있는 쪽 부호).
            → 통로(중앙)는 비고 맞은편 줄과 안 겹침. (barcode_y 안 씀)
    - 본체: 앞면이 포트 라인에 오고 outward 로 depth 만큼 뻗음.
    - 충돌 clamp: 본체끼리 겹치면(주로 인접 bay) 양쪽 depth 를 줄임.
    반환: device dict 리스트 (station_body.map 으로 직렬화 가능).
      {device_id, bay, center(x,y), dir(ux,uy), outward(ox,oy),
       width, depth, height, stations:[name,...]}
    """
    ebn = {e.edge_name: e for e in edges}
    eq = [s for s in stations if (s.station_type or "").upper() == "EQ"]
    st_by_name = {s.station_name: s for s in eq}
    pos = {s.station_name: station_position(s, nodes, ebn) for s in eq}
    axes = _bay_axes(edges, nodes)
    names = list(pos)

    # union-find (단일연결 근접 클러스터)
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    thr2 = thr * thr
    for i in range(len(names)):
        xi, yi, _ = pos[names[i]]
        for j in range(i + 1, len(names)):
            xj, yj, _ = pos[names[j]]
            dx, dy = xi - xj, yi - yj
            if dx * dx + dy * dy <= thr2:
                ri, rj = find(names[i]), find(names[j])
                if ri != rj:
                    parent[ri] = rj

    groups = {}
    for n in names:
        groups.setdefault(find(n), []).append(n)

    devs = []
    for k, (_root, members) in enumerate(sorted(groups.items())):
        members = sorted(members)
        rep = st_by_name[members[0]]
        bay = rep.bay_name
        bayC, bu, bn = axes.get(bay, ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)))
        pxy = [(pos[m][0], pos[m][1]) for m in members]
        ccx = sum(p[0] for p in pxy) / len(pxy)
        ccy = sum(p[1] for p in pxy) / len(pxy)
        # 몸통 방향 = 클러스터 자체 PCA(실제 포트 줄/레일 방향) → 포트와 정렬(안 틀어짐)
        if len(pxy) >= 2:
            _pc, u, perp = _pca2d(pxy)
        else:
            u, perp = bu, bn
        # outward = 클러스터 단축, bay 중심에서 바깥쪽으로 부호 결정
        side = (ccx - bayC[0]) * perp[0] + (ccy - bayC[1]) * perp[1]
        s = 1.0 if side >= 0 else -1.0
        ox, oy = perp[0] * s, perp[1] * s
        proj = [(p[0] - ccx) * u[0] + (p[1] - ccy) * u[1] for p in pxy]
        half_port = (max(proj) - min(proj)) / 2.0
        devs.append({
            "device_id": f"DEV_{bay}_{k:04d}", "bay": bay,
            "front": (ccx, ccy),       # 포트 라인 중심
            "dir": (u[0], u[1]), "outward": (ox, oy),
            "half_port": half_port, "side": EQ_SIDE,
            "depth": depth, "height": height,
            "stations": members,
        })

    # 본체 OBB: 폭 = 2*(half_port+side) 대칭(포트 중앙정렬), center = 포트중심 + outward*depth/2
    def body_obb(dv):
        hw = dv["half_port"] + dv["side"]
        hd = dv["depth"] / 2.0
        ux, uy = dv["dir"]
        ox2, oy2 = dv["outward"]
        cx = dv["front"][0] + ox2 * hd
        cy = dv["front"][1] + oy2 * hd
        return (cx, cy), dv["dir"], dv["outward"], (hw, hd)

    def sep_along(ax, ay, ca, ua, va, ha, cb, ub, vb, hb):
        ra = ha[0] * abs(ua[0] * ax + ua[1] * ay) + ha[1] * abs(va[0] * ax + va[1] * ay)
        rb = hb[0] * abs(ub[0] * ax + ub[1] * ay) + hb[1] * abs(vb[0] * ax + vb[1] * ay)
        return abs((cb[0] - ca[0]) * ax + (cb[1] - ca[1]) * ay) - (ra + rb)

    # --- 축 인식 충돌 clamp: 겹치면 분리 쉬운 축으로 줄임 (좌우=main폭, 앞뒤=depth) ---
    for _ in range(8):
        changed = False
        for i in range(len(devs)):
            for j in range(i + 1, len(devs)):
                A, B = devs[i], devs[j]
                ca, ua, va, ha = body_obb(A)
                cb, ub, vb, hb = body_obb(B)
                if _obb_separated(ca, ua, va, ha, cb, ub, vb, hb):
                    continue
                # dir(좌우) vs outward(앞뒤) 어느 축 겹침이 더 얕은지 (A 기준)
                sep_u = sep_along(ua[0], ua[1], ca, ua, va, ha, cb, ub, vb, hb)
                sep_v = sep_along(va[0], va[1], ca, ua, va, ha, cb, ub, vb, hb)
                for dv in (A, B):
                    if sep_u >= sep_v:    # 좌우 겹침이 더 얕음 → side 폭 대칭 축소
                        nv = max(dv["side"] * 0.7, EQ_MIN_SIDE)
                        if nv < dv["side"]:
                            dv["side"] = nv
                            changed = True
                    else:                 # 앞뒤 겹침 → depth 축소
                        nd = max(dv["depth"] * 0.8, EQ_BODY_MIN_DEPTH)
                        if nd < dv["depth"]:
                            dv["depth"] = nd
                            changed = True
        if not changed:
            break

    clamped = sum(1 for d in devs
                  if d["depth"] < depth - 1e-6 or d["side"] < EQ_SIDE - 1e-6)
    # 최종 center/width/타입/모델 확정해서 반환
    for dv in devs:
        (cx, cy), _u, _o, (hw, _hd) = body_obb(dv)
        dv["center"] = (cx, cy)
        dv["width"] = hw * 2.0
        dv["type"] = "EQ"
        dv["model"] = eq_model_for(len(dv["stations"]))
    return devs, clamped


def eq_model_for(nports):
    """EQ device 의 기본 모델을 포트 수로 추정 (사람이 station_body.map 에서 수정 가능).
    4+포트=EFEM(공정장비), 3포트=NTB(버퍼), 1~2포트=LPS(로드포트 스테이션)."""
    if nports >= 4:
        return "EFEM"
    if nports == 3:
        return "NTB"
    return "LPS"


# --- OHB 거치대(래크) device ---
OHB_Z = 3.0                   # OHB 높이 (천장 부근, station_z 와 일치)
OHB_CLUSTER_THRESHOLD = 0.7   # 0.5 내부간격 묶고 3m 통로에서 끊김
OHB_SHELF_DEPTH = 0.6         # 거치대 footprint 깊이 (기본)
OHB_MIN_DEPTH = 0.5           # 적응형 depth 최소
OHB_WIDTH_MARGIN = 0.25       # 양옆 여유
OHB_EDGE_WIDTH = 0.06         # 바닥 사각 테두리 선 굵기
OHB_HANGER_TOP = 3.8          # 행어 윗끝(레일 높이)까지


def _cluster_by_proximity(pos, thr):
    """{name:(x,y,z)} 를 thr(m) 근접 union-find 로 묶어 [[name,...],...] 반환."""
    names = list(pos)
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    thr2 = thr * thr
    for i in range(len(names)):
        xi, yi, _ = pos[names[i]]
        for j in range(i + 1, len(names)):
            xj, yj, _ = pos[names[j]]
            dx, dy = xi - xj, yi - yj
            if dx * dx + dy * dy <= thr2:
                ri, rj = find(names[i]), find(names[j])
                if ri != rj:
                    parent[ri] = rj
    groups = {}
    for n in names:
        groups.setdefault(find(n), []).append(n)
    return [sorted(v) for v in groups.values()]


def compute_ohb_devices(stations, nodes, edges, thr=OHB_CLUSTER_THRESHOLD):
    """OHB 를 근접 클러스터(=거치대 래크) 로 묶음. 각 래크 = bay축 따라 누운 선반 + FOUP 칸들.
    레일 옆(barcode_y offset)·천장 높이(z=OHB_Z). 행어/천장은 표현 안 함."""
    ebn = {e.edge_name: e for e in edges}
    ohb = [s for s in stations if (s.station_type or "").upper() == "OHB"]
    st_by_name = {s.station_name: s for s in ohb}
    pos = {s.station_name: station_position(s, nodes, ebn) for s in ohb}
    axes = _bay_axes(edges, nodes)
    out = []
    for k, members in enumerate(sorted(_cluster_by_proximity(pos, thr))):
        rep = st_by_name[members[0]]
        bay = rep.bay_name
        pxy = [(pos[m][0], pos[m][1]) for m in members]
        # 클러스터 자체 PCA 로 줄 방향(u) 결정 — bay 장축이 아니라 실제 OHB 줄 방향.
        if len(pxy) >= 2:
            C, u, nrm = _pca2d(pxy)
        else:
            C, u, nrm = (pxy[0][0], pxy[0][1]), (1.0, 0.0), (0.0, 1.0)
        proj_u = [(p[0] - C[0]) * u[0] + (p[1] - C[1]) * u[1] for p in pxy]
        proj_n = [(p[0] - C[0]) * nrm[0] + (p[1] - C[1]) * nrm[1] for p in pxy]
        # rect 가 포트를 항상 감싸도록 width/depth 둘 다 실제 spread 에 맞춤
        width = (max(proj_u) - min(proj_u)) + 2 * OHB_WIDTH_MARGIN
        depth = max((max(proj_n) - min(proj_n)) + 2 * OHB_WIDTH_MARGIN, OHB_MIN_DEPTH)
        cu = (max(proj_u) + min(proj_u)) / 2.0
        cn = (max(proj_n) + min(proj_n)) / 2.0
        cx = C[0] + u[0] * cu + nrm[0] * cn
        cy = C[1] + u[1] * cu + nrm[1] * cn
        out.append({
            "device_id": f"OHB_{bay}_{k:04d}", "type": "OHB", "model": "OHB_RACK",
            "bay": bay, "center": (cx, cy),
            "dir": (u[0], u[1]), "outward": (nrm[0], nrm[1]),
            "width": width, "depth": depth, "height": OHB_Z,
            "stations": members,
        })
    return out


# --- STK 스토커 device (위아래로 길쭉한 타워) ---
STK_WIDTH = 1.6
STK_DEPTH = 1.6
STK_HEIGHT = 4.6              # 키 큰 보관탑
STK_CLEARANCE = 0.4          # 레일에서 옆으로 띄우는 여유 (타워가 레일 안 뚫게)


def compute_stk_devices(stations, nodes, edges):
    """STK(스토커) = 위치마다 키 큰 타워 1개. EQ 처럼 통로 바깥(outward)으로 빼서
    타워가 레일을 안 뚫게 함. 로드포트는 station 위치(레일쪽)에 남아 앞으로 돌출."""
    ebn = {e.edge_name: e for e in edges}
    stk = [s for s in stations if (s.station_type or "").upper() == "STK"]
    axes = _bay_axes(edges, nodes)
    out = []
    for k, s in enumerate(stk):
        p = station_position(s, nodes, ebn)
        bay = s.bay_name
        C, u, nrm = axes.get(bay, ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)))
        side = (p[0] - C[0]) * nrm[0] + (p[1] - C[1]) * nrm[1]
        sg = 1.0 if side >= 0 else -1.0
        ox, oy = nrm[0] * sg, nrm[1] * sg
        # 타워 중심을 바깥으로 (depth/2 + 여유) 만큼 밀어 레일에서 떨어뜨림
        off = STK_DEPTH / 2.0 + STK_CLEARANCE
        out.append({
            "device_id": f"STK_{bay}_{k:04d}", "type": "STK", "model": "STOCKER",
            "bay": bay, "center": (p[0] + ox * off, p[1] + oy * off),
            "dir": (u[0], u[1]), "outward": (ox, oy),
            "width": STK_WIDTH, "depth": STK_DEPTH, "height": STK_HEIGHT,
            "stations": [s.station_name],
        })
    return out


def compute_devices(stations, nodes, edges):
    """모든 타입(EQ/OHB/STK) device 통합 + EQ 충돌 clamp 수."""
    eq, clamped = compute_eq_devices(stations, nodes, edges)
    ohb = compute_ohb_devices(stations, nodes, edges)
    stk = compute_stk_devices(stations, nodes, edges)
    return eq + ohb + stk, clamped


def station_instances(stations, nodes, edges):
    """
    반환: [(pos(x,y,z), yaw_rad, proto_index), ...]
      proto_index -> STATION_PROTO_ORDER (EQ/OHB/STK/DEFAULT)
    """
    edges_by_name = {e.edge_name: e for e in edges}
    type_to_idx = {t: i for i, t in enumerate(STATION_PROTO_ORDER)}
    out = []
    for st in stations:
        pos = station_position(st, nodes, edges_by_name)
        yaw = math.radians(st.barcode_r)
        key = (st.station_type or "").upper()
        idx = type_to_idx.get(key, type_to_idx["DEFAULT"])
        out.append((pos, yaw, idx))
    return out


if __name__ == "__main__":
    from mapio import parse_nodes, parse_edges
    base = "/home/zunxin/vps/public/railConfig/y_short"
    nodes = parse_nodes(f"{base}/nodes.cfg")
    edges = parse_edges(f"{base}/edges.cfg")
    inst = all_rail_instances(edges, nodes)
    print(f"edges: {len(edges)}  -> rail plane instances: {len(inst)}")
    # 타입별 인스턴스 수 점검
    from collections import Counter
    by = Counter()
    for e in edges:
        by[e.vos_rail_type] += len(rail_instances(e, nodes))
    print("instances by type:", dict(by))
    # bbox 점검 (좌표 sanity)
    xs = [p[0][0] for p in inst]; ys = [p[0][1] for p in inst]
    print(f"x range: {min(xs):.1f}..{max(xs):.1f}   y range: {min(ys):.1f}..{max(ys):.1f}")
