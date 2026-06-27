"""
VPS 맵 파일 파서 — VPS/src/store/system/cfgStore.ts 의 파싱 로직을 파이썬으로 번역.
입력 파싱은 VPS 그대로, 출력만 나중에 USD 로 교체한다.

파일:
  nodes.map   : node_name,barcode,editor_x,editor_y,editor_z   (TMP_* 웨이포인트 포함)
  edges.map   : edge_name,from_node,to_node,distance,vos_rail_type,bay_name,waypoints,radius,waiting_offset
  station.map : station_name,editor_x,editor_y,barcode_x,barcode_y,barcode_r,bay_name,station_type,nearest_edge,nearest_edge_distance
"""
import csv
import io
import json
from dataclasses import dataclass

# nodes.map 의 editor_z 누락 시 기본값 (renderConfig MARKER Z = 3.8)
DEFAULT_NODE_Z = 3.8


@dataclass
class Node:
    node_name: str
    barcode: int
    editor_x: float
    editor_y: float
    editor_z: float


@dataclass
class Edge:
    edge_name: str
    from_node: str
    to_node: str
    distance: float
    vos_rail_type: str
    bay_name: str
    waypoints: list          # ["N0001", "TMP_FROM_N_E0002", ...]
    radius: float
    waiting_offset: int = -1


@dataclass
class Station:
    station_name: str
    editor_x: float
    editor_y: float
    barcode_x: float
    barcode_y: float
    barcode_r: float          # yaw (deg)
    bay_name: str
    station_type: str
    nearest_edge: str
    nearest_edge_distance: float


@dataclass
class StationBody:
    """station_body.map 한 줄 = device(장비) 1대. type=대분류(EQ/OHB/STK), model=형상모델."""
    device_id: str
    type: str
    model: str
    bay: str
    center_x: float
    center_y: float
    dir_x: float
    dir_y: float
    out_x: float
    out_y: float
    width: float
    depth: float
    height: float
    stations: list           # 소속 로드포트 station_name 리스트


def _read_csv_rows(path):
    """
    cfgStore.parseCSV 대응: '#' 주석줄 제거 후 헤더 기준 dict 행 반환.
    PapaParse(헤더 모드)와 동일하게 헤더/값 trim.
    """
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln for ln in f if not ln.lstrip().startswith("#")]
    text = "".join(lines)
    reader = csv.DictReader(io.StringIO(text), skipinitialspace=True)
    rows = []
    for row in reader:
        rows.append({(k.strip() if k else k): (v.strip() if isinstance(v, str) else v)
                     for k, v in row.items()})
    return rows


def _parse_waypoints(s):
    """
    cfgStore.parseWaypoints 대응:
      "[N0001, TMP_FROM_N_E0002, TMP_TO_N_E0002, N0002]" -> [...4개...]
    앞뒤 따옴표/대괄호 제거 후 콤마 split + trim.
    """
    if not s:
        return []
    cleaned = s.strip().strip('"').strip("'")
    if cleaned.startswith("["):
        cleaned = cleaned[1:]
    if cleaned.endswith("]"):
        cleaned = cleaned[:-1]
    if not cleaned:
        return []
    return [w.strip() for w in cleaned.split(",") if w.strip()]


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def parse_nodes(path):
    """parseNodesCFG 대응. TMP_* 노드도 그대로 포함 (좌표가 cfg에 들어있음)."""
    nodes = {}
    for r in _read_csv_rows(path):
        name = r.get("node_name")
        if not name:
            continue
        nodes[name] = Node(
            node_name=name,
            barcode=_i(r.get("barcode")),
            editor_x=_f(r.get("editor_x")),
            editor_y=_f(r.get("editor_y")),
            editor_z=_f(r.get("editor_z"), DEFAULT_NODE_Z),
        )
    return nodes


def parse_edges(path):
    """parseEdgesCFG 대응."""
    edges = []
    for r in _read_csv_rows(path):
        name = r.get("edge_name")
        if not name:
            continue
        edges.append(Edge(
            edge_name=name,
            from_node=r.get("from_node", ""),
            to_node=r.get("to_node", ""),
            distance=_f(r.get("distance")),
            vos_rail_type=r.get("vos_rail_type", "LINEAR") or "LINEAR",
            bay_name=r.get("bay_name", ""),
            waypoints=_parse_waypoints(r.get("waypoints")),
            radius=_f(r.get("radius"), -1.0),
            waiting_offset=_i(r.get("waiting_offset"), -1),
        ))
    return edges


def parse_stations(path):
    """parseStationMap 대응."""
    stations = []
    for r in _read_csv_rows(path):
        name = r.get("station_name")
        if not name or name == "station_name":
            continue
        stations.append(Station(
            station_name=name,
            editor_x=_f(r.get("editor_x")),
            editor_y=_f(r.get("editor_y")),
            barcode_x=_f(r.get("barcode_x")),
            barcode_y=_f(r.get("barcode_y")),
            barcode_r=_f(r.get("barcode_r")),
            bay_name=r.get("bay_name", ""),
            station_type=r.get("station_type", ""),
            nearest_edge=r.get("nearest_edge", ""),
            nearest_edge_distance=_f(r.get("nearest_edge_distance")),
        ))
    return stations


def parse_station_body(path):
    """station_body.map 파서. EQ device(본체) 정의 + 소속 포트."""
    out = []
    for r in _read_csv_rows(path):
        did = r.get("device_id")
        if not did or did == "device_id":
            continue
        out.append(StationBody(
            device_id=did,
            type=r.get("type", "EQ"),
            model=r.get("model", "EFEM"),
            bay=r.get("bay", ""),
            center_x=_f(r.get("center_x")),
            center_y=_f(r.get("center_y")),
            dir_x=_f(r.get("dir_x"), 1.0),
            dir_y=_f(r.get("dir_y")),
            out_x=_f(r.get("out_x")),
            out_y=_f(r.get("out_y"), 1.0),
            width=_f(r.get("width"), 1.0),
            depth=_f(r.get("depth"), 1.3),
            height=_f(r.get("height"), 2.0),
            stations=_parse_waypoints(r.get("stations")),
        ))
    return out


def parse_rail_hide(path):
    """rail_hide.map 파서. edge_name -> (left_intervals, right_intervals).
    각 인터벌은 [[a,b],...] (edge 따라 0~1 정규화). 그 구간 레일 세그먼트는 안 그림."""
    out = {}

    def pj(v):
        v = (v or "").strip()
        if not v or v == "[]":
            return []
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return []

    for r in _read_csv_rows(path):
        en = r.get("edge_name")
        if not en or en == "edge_name":
            continue
        out[en] = (pj(r.get("left_hide")), pj(r.get("right_hide")))
    return out


if __name__ == "__main__":
    import sys
    base = sys.argv[1] if len(sys.argv) > 1 else \
        "../input/fab_map"
    nodes = parse_nodes(f"{base}/nodes.map")
    edges = parse_edges(f"{base}/edges.map")
    stations = parse_stations(f"{base}/station.map")
    print(f"nodes   : {len(nodes)}  (TMP_*: {sum(1 for n in nodes if n.startswith('TMP_'))})")
    print(f"edges   : {len(edges)}")
    from collections import Counter
    print("  by type:", dict(Counter(e.vos_rail_type for e in edges)))
    print(f"stations: {len(stations)}")
    print("  by type:", dict(Counter(s.station_type for s in stations)))
    e = edges[3]
    print("sample edge:", e.edge_name, e.vos_rail_type, "wp=", e.waypoints, "r=", e.radius)
