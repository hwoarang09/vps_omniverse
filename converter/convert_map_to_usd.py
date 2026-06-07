"""
convert_map_to_usd.py — VPS 맵(nodes.cfg/edges.cfg/station.map) -> USD.

VPS 의 파싱 + 지오메트리 로직을 그대로 쓰고(=mapio.py, geometry.py),
출력 레이어만 USD 로 교체:
  THREE.InstancedMesh.setMatrixAt  ->  UsdGeom.PointInstancer (positions/orientations/scales)
  THREE.PlaneGeometry / BoxGeometry ->  UsdGeom.Mesh prototype

씬 구조:
  /World (Z-up, m)
    /Protos/RailPlane                  (회색 평면, invisible)
    /Protos/Station_{EQ,OHB,STK,DEFAULT} (타입별 색 큐브, invisible)
    /Rails     PointInstancer  (레일 세그먼트 ~37k)
    /Stations  PointInstancer  (스테이션 ~4.3k, protoIndices=타입)
"""
import os
import sys
from pxr import Gf

from pxr import UsdGeom, UsdShade

import usd_build as ub
import json
from mapio import (parse_nodes, parse_edges, parse_stations, parse_station_body,
                   parse_rail_hide)


def load_or_make_line_cut(path, edges, nodes):
    """직선 끊기: **2×radius 공식(compute_line_cut_hide)이 기본**. line_cut.map 이 있으면
    그 안의 non-empty 항목만 수동 오버라이드로 덮어씀(특수 케이스 손조정용).
    반환 {linear_edge:(left_iv, right_iv)}."""
    import geometry as geo
    line_hide = geo.compute_line_cut_hide(edges, nodes)        # 공식 기본
    if os.path.exists(path):
        n = 0
        for en, (L, R) in parse_rail_hide(path).items():
            if L or R:                                         # 값 있는 것만 오버라이드
                line_hide[en] = (L, R)
                n += 1
        if n:
            print(f"  line_cut: {n} edges overridden by {os.path.basename(path)}")
    return line_hide
import geometry as geo
import models


def add_top_down_camera(stage, positions, path="/World/TopCam", margin=1.08):
    """
    XY평면 맵을 위에서 내려다보는 직교(orthographic) 카메라.
    Z-up 에서 identity 회전 카메라는 로컬 -Z(=world -Z, 아래)를 바라보고
    +Y 가 화면 위 -> 그대로 탑뷰. 높은 +Z 에 올려두고 내려다본다.
    usdview 에서 Camera 메뉴 > TopCam 선택하면 이 뷰로 잡힘.
    반환: (aspect, world_width, world_height)
    """
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    w = (xmax - xmin) * margin
    h = (ymax - ymin) * margin

    cam = UsdGeom.Camera.Define(stage, path)
    cam.CreateProjectionAttr(UsdGeom.Tokens.orthographic)
    # 직교: 가시 월드 크기 = aperture * APERTURE_UNIT(0.1) -> aperture = 월드크기 * 10
    cam.CreateHorizontalApertureAttr(w * 10.0)
    cam.CreateVerticalApertureAttr(h * 10.0)
    cam.CreateClippingRangeAttr((1.0, 100000.0))
    # 카메라를 맵 위 높은 곳에 올림 (직교라 높이는 크기에 무관, 클리핑만 충족)
    UsdGeom.XformCommonAPI(cam).SetTranslate((cx, cy, 5000.0))
    return (w / h if h else 1.0, w, h)


def convert(map_dir, out_path, station_marker=True):
    nodes = parse_nodes(f"{map_dir}/nodes.cfg")
    edges = parse_edges(f"{map_dir}/edges.cfg")
    try:
        stations = parse_stations(f"{map_dir}/station.map")
    except FileNotFoundError:
        stations = []

    stage = ub.make_stage(out_path, up="Z", meters_per_unit=1.0)

    # --- 조명: 돔(균일 환경광) + 약한 태양. 라이트 2개만 (가벼움) ---
    ub.add_dome_light(stage, intensity=450.0)
    ub.add_distant_light(stage, intensity=900.0)

    # --- rails: instanced 박스 세그먼트 (LINEAR=1개, 곡선=적응적 8~16개) ---
    #   두꺼운 BasisCurves 튜브(37k점 테셀레이션) 대신 박스 세그먼트 PointInstancer.
    polylines = geo.rail_polylines(edges, nodes)   # 바닥 bbox/카메라용
    # 곡선 trim(Stage2: 호 outer + 곡선 직선영역 방해)
    rail_hide = geo.compute_rail_hide(edges, nodes)
    # 직선 trim(Stage3): line_cut.map (per-edge 손편집). 없으면 기본값 자동생성·저장.
    line_hide = load_or_make_line_cut(f"{map_dir}/line_cut.map", edges, nodes)
    rail_hide = geo.merge_hide(rail_hide, line_hide)
    rsegs, _tsegs = geo.dual_rail_segments(edges, nodes, hide=rail_hide)   # 2줄 레일
    # 레일 색: realistic(알루미늄 그레이, 기본) / debug(초록=직선·분홍=곡선직선·빨강=호).
    #   USD railColor variantSet 으로 토글 (Composer Variant UI 또는 omni.ui 버튼).
    #   emissive 금지(37k 면이 GI 광원→HydraEngine error6+fps폭락).
    rail_colors = {
        geo.RAIL_CLS_GREEN: (0.15, 0.85, 0.25),
        geo.RAIL_CLS_PINK:  (1.00, 0.45, 0.75),
        geo.RAIL_CLS_RED:   (0.95, 0.12, 0.12),
    }
    mat_real = ub.add_preview_material(stage, "/World/Looks/Rail_realistic",
                                       diffuse=(0.52, 0.57, 0.64), metallic=0.65, roughness=0.35)
    mat_dbg = {k: ub.add_preview_material(stage, f"/World/Looks/Rail_{k}",
                                          diffuse=rail_colors[k], metallic=0.1, roughness=0.5)
               for k in geo.RAIL_DEBUG_KEYS}
    rail_protos, rail_key_to_idx = [], {}
    for i, key in enumerate(geo.RAIL_DEBUG_KEYS):
        pth = f"/World/Protos/box_rail_{key}"
        ub.bind_material(ub.add_unit_cube_proto(stage, pth, color=rail_colors[key]), mat_real)
        rail_protos.append(pth)
        rail_key_to_idx[key] = i
    ub.make_instancer(stage, "/World/Rails", rail_protos,
                      [Gf.Vec3f(*s[0]) for s in rsegs],
                      orientations=[ub.quat_yaw_rad(s[1]) for s in rsegs],
                      scales=[Gf.Vec3f(*s[2]) for s in rsegs],
                      proto_indices=[rail_key_to_idx[s[3]] for s in rsegs])
    # railColor variantSet: realistic(전부 그레이) / debug(타입별 색). 기본 realistic.
    protos_prim = stage.GetPrimAtPath("/World/Protos")
    vset = protos_prim.GetVariantSets().AddVariantSet("railColor")
    for vname, matof in (("realistic", lambda k: mat_real), ("debug", lambda k: mat_dbg[k])):
        vset.AddVariant(vname)
        vset.SetVariantSelection(vname)
        with vset.GetVariantEditContext():
            for key in geo.RAIL_DEBUG_KEYS:
                UsdShade.MaterialBindingAPI.Apply(
                    stage.GetPrimAtPath(f"/World/Protos/box_rail_{key}")).Bind(matof(key))
    vset.SetVariantSelection("realistic")

    # --- device(장비): station_body.map 있으면 사용, 없으면 자동 계산 ---
    #   형상은 models.py 빌더가 model 이름(EFEM/LPS/NTB/STOCKER/OHB_RACK)으로 분기.
    #   본체/포트/테두리빔까지 전부 박스 인스턴스로 모아 PointInstancer 1개로 그림.
    ebn = {e.edge_name: e for e in edges}
    sb_path = f"{map_dir}/station_body.map"
    if os.path.exists(sb_path):
        bodies = parse_station_body(sb_path)
        devices = [{"device_id": b.device_id, "type": b.type, "model": b.model,
                    "center": (b.center_x, b.center_y),
                    "dir": (b.dir_x, b.dir_y), "outward": (b.out_x, b.out_y),
                    "width": b.width, "depth": b.depth, "height": b.height,
                    "stations": b.stations} for b in bodies]
        src = os.path.basename(sb_path)
    else:
        devices, _clamped = geo.compute_devices(stations, nodes, edges)
        src = "auto (no station_body.map)"

    # 머티리얼 + 박스 프로토타입(머티리얼별 단위큐브). 모든 장비 박스를 이걸로 인스턴싱.
    mats = models.make_palette(stage, ub)
    box_protos = []
    key_to_idx = {}
    for i, (key, mat) in enumerate(mats.items()):
        pth = f"/World/Protos/box_{key}"
        ub.bind_material(ub.add_unit_cube_proto(stage, pth), mat)
        box_protos.append(pth)
        key_to_idx[key] = i

    pos_all = {s.station_name: geo.station_position(s, nodes, ebn) for s in stations}
    coll = models.Instances()
    handled = set()
    for d in devices:
        d["port_xy"] = [pos_all[n][:2] for n in d["stations"] if n in pos_all]
        handled.update(d["stations"])
        models.build_device(coll, d)

    # 장비 전체 = PointInstancer 1개 (= THREE.InstancedMesh). 박스 수만 개여도 사실상 1 draw.
    if coll.items:
        ub.make_instancer(stage, "/World/EquipInstances", box_protos,
                          [Gf.Vec3f(*c) for (_m, c, _y, _s) in coll.items],
                          orientations=[ub.quat_yaw_rad(y) for (_m, _c, y, _s) in coll.items],
                          scales=[Gf.Vec3f(*s) for (_m, _c, _y, s) in coll.items],
                          proto_indices=[key_to_idx[m] for (m, _c, _y, _s) in coll.items])

    # --- 나머지(device 미배정 station, 대개 DEFAULT) 만 별도 마커 인스턴서 ---
    box = geo.STATION_MARKER_BOX if station_marker else geo.STATION_BOX
    sts = geo.station_instances(stations, nodes, edges)
    leftover = [(p, yaw, i) for (p, yaw, i), s in zip(sts, stations)
                if s.station_name not in handled]
    if leftover:
        st_protos = []
        for key in geo.STATION_PROTO_ORDER:
            color = geo.STATION_COLOR.get(key, geo.STATION_COLOR_DEFAULT)
            pth = f"/World/Protos/Station_{key}"
            ub.bind_material(ub.add_unit_cube_proto(stage, pth, color=color),
                             ub.add_preview_material(stage, f"/World/Looks/Station_{key}",
                                                     diffuse=color, metallic=0.1, roughness=0.55))
            st_protos.append(pth)
        ub.make_instancer(stage, "/World/Stations", st_protos,
                          [Gf.Vec3f(*p) for (p, _y, _i) in leftover],
                          orientations=[ub.quat_yaw_rad(y) for (_p, y, _i) in leftover],
                          scales=[Gf.Vec3f(*box) for _ in leftover],
                          proto_indices=[i for (_p, _y, i) in leftover])

    # --- 공장 바닥 (레일 bbox 기준, z=0) ---
    rail_pts_xy = [p for pl in polylines for p in pl]
    rxs = [p[0] for p in rail_pts_xy]
    rys = [p[1] for p in rail_pts_xy]
    # 어두운 산업 콘크리트 → 밝은 포트(노랑/연두/주황)가 대비로 튐
    ub.add_ground_plane(stage, "/World/Floor",
                       min(rxs), max(rxs), min(rys), max(rys), z=0.0,
                       color=(0.13, 0.14, 0.16))
    # (천장 형광등 스트립 제거 — emissive 면이 GI 광원으로 잡혀 fps 폭락했음)

    # --- 탑뷰 카메라 (전체 bbox 기준) ---
    all_pos = [p for pl in polylines for p in pl] + [p for (p, _y, _i) in sts]
    aspect, w, h = add_top_down_camera(stage, all_pos)

    stage.GetRootLayer().Save()
    print(f"WROTE {out_path}")
    print(f"  rails   : {len(rsegs)} rail box segments (2줄, instanced)")
    from collections import Counter
    print(f"  devices : {len(devices)} [{src}]  models={dict(Counter(d['model'] for d in devices))}")
    print(f"  instances: {len(coll.items)} boxes → 1 PointInstancer ({len(box_protos)} protos)")
    print(f"  leftover: {len(leftover)} marker stations (DEFAULT)")
    print(f"  TopCam   : world {w:.1f} x {h:.1f}  aspect {aspect:.3f}")
    return out_path, aspect


if __name__ == "__main__":
    map_dir = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/zunxin/vps/public/railConfig/y_short"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "out/y_short.usda"
    convert(map_dir, out_path)
