"""
build_cut.py — base.usda 위에 얹는 '정확한 기하 트림' 오버라이드 레이어(cut.usda).

USD 레이어 합성(LIVRPS) 데모. 기존 line_cut.usda(가시성 invisibleIds)를 대체:
  base.usda     : raw 풀길이 2줄 레일 전부 (build_base.py, 트림 없음·invisibleIds 없음)
  cut.usda      : ★ 이 스크립트 ★  over "/World/Rails" 에 **트림된 인스턴스 배열**
                  (positions/orientations/scales/protoIndices) 4개를 통째로 override.
                  트림은 '숨김'이 아니라 박스 길이/위치로 '정확히' 반영(양자화 없음).
  composed.usda : subLayers=[cut.usda, base.usda] 정적 stitch (out/composed.usda).
                  cut 을 mute/제외하면 base 의 raw 원본이 그대로 보인다.

invisibleIds 방식과 달리 직선 트림 길이가 0.5 세그 단위로 양자화되지 않는다
(남는 구간을 정확한 길이의 박스 1개로 다시 굽기 때문 = 이번 리팩터의 핵심).
prototypes 릴레이션·머티리얼은 base 것을 그대로 상속(over 라 새로 안 적음).
protoIndices 는 base 의 프로토타입 순서(RAIL_DEBUG_KEYS: green=0, pink=1, red=2)와 동일.

트림 수학(hide=제거 인터벌)은 base/line_cut 과 완전히 동일한 함수 공유:
  곡선 호/직선방해(hide_curve_edges) + 직선 라인끊기 K×r(hide_linear_edges).
바꾼 건 '적용 방법'뿐 — 숨기는 대신 dual_rail_segments_trimmed 로 남는 구간만 기하 생성.
"""
import os
import sys

import geometry as geo
import usd_build as ub
from mapio import parse_edges, parse_nodes
from pxr import Gf, Usd, UsdGeom, Vt


def build(map_dir, out_dir):
    nodes = parse_nodes(f"{map_dir}/nodes.map")
    edges = parse_edges(f"{map_dir}/edges.map")

    # base/line_cut 과 동일한 trim 수학(제거 인터벌) → 남는 구간만 정확한 기하로.
    hide = geo.merge_hide(geo.hide_curve_edges(edges, nodes),     # 곡선 호/직선방해 trim
                          geo.hide_linear_edges(edges, nodes))    # 직선 라인끊기(K×r)
    rsegs, _ = geo.dual_rail_segments_trimmed(edges, nodes, hide)

    # base 와 동일한 프로토타입 인덱스 규약(RAIL_DEBUG_KEYS 순서: green=0, pink=1, red=2).
    key_to_idx = {k: i for i, k in enumerate(geo.RAIL_DEBUG_KEYS)}

    # override 레이어: over /World/Rails 에 인스턴스 4배열을 통째로 다시 author.
    path = f"{out_dir}/cut.usda"
    if os.path.exists(path):
        os.remove(path)
    cut = Usd.Stage.CreateNew(path)
    over = cut.OverridePrim("/World/Rails")                  # 'over' specifier(비파괴)
    pi = UsdGeom.PointInstancer(over)
    pi.CreatePositionsAttr(Vt.Vec3fArray([Gf.Vec3f(*s[0]) for s in rsegs]))
    pi.CreateOrientationsAttr(Vt.QuathArray([ub.quat_yaw_rad(s[1]) for s in rsegs]))
    pi.CreateScalesAttr(Vt.Vec3fArray([Gf.Vec3f(*s[2]) for s in rsegs]))
    pi.CreateProtoIndicesAttr(Vt.IntArray([key_to_idx[s[3]] for s in rsegs]))
    cut.GetRootLayer().Save()

    print(f"WROTE {path}")
    print(f"  trimmed : {len(rsegs)} rail box segments (정확 기하, over /World/Rails)")
    print(f"  합성해서 보기: usdview {out_dir}/composed.usda")
    print("  비파괴 확인: composed 에서 cut.usda 빼면 base raw 2줄로 복귀")
    return path


if __name__ == "__main__":
    map_dir = sys.argv[1] if len(sys.argv) > 1 else "../input/fab_map"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "../out"
    build(map_dir, out_dir)
