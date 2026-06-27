"""
build_line_cut.py — base.usda 위에 얹는 '겹침 정리' 오버라이드 레이어만 생성.

USD 레이어 합성(LIVRPS) 데모에서 이 스크립트의 책임은 단 하나: line_cut.usda.
  base.usda      : raw 2줄 레일 전부 (build_base.py)
  line_cut.usda  : ★ 이 스크립트 ★  over "/World/Rails" 에 invisibleIds 만 적어
                   교차점 겹침 세그먼트를 '비파괴'로 숨김. base 는 손도 안 댐.
  composed.usda  : subLayers=[line_cut.usda, base.usda] 정적 stitch (out/composed.usda,
                   손으로 쓴 5줄. 맵 데이터와 무관해 코드가 생성 안 함).

핵심: invisibleIds 의 인덱스는 base PointInstancer 의 인스턴스 순서와 1:1.
  → 양쪽 다 geo.dual_rail_segments_tagged(edges, nodes) 를 같은 순서로 돌려 정렬 보장.
  make_instancer 가 ids 를 안 박으므로 instance id == 배열 인덱스.
"""
import os
import sys

import geometry as geo
from mapio import parse_edges, parse_nodes
from pxr import Usd, UsdGeom, Vt


def build(map_dir, out_dir):
    nodes = parse_nodes(f"{map_dir}/nodes.map")
    edges = parse_edges(f"{map_dir}/edges.map")

    # base 와 '동일 순서'의 모든 레일 세그먼트 → 그 중 가릴 인덱스 계산.
    tagged = geo.dual_rail_segments_tagged(edges, nodes)
    hide = geo.merge_hide(geo.hide_curve_edges(edges, nodes),       # 곡선 호/직선방해 trim
                          geo.hide_linear_edges(edges, nodes))   # 직선 라인끊기(2×r)
    hidden = geo.hidden_seg_indices(tagged, hide)

    # override 레이어 하나만: over /World/Rails { invisibleIds = [...] }
    path = f"{out_dir}/line_cut.usda"
    if os.path.exists(path):
        os.remove(path)
    lc = Usd.Stage.CreateNew(path)
    over = lc.OverridePrim("/World/Rails")                  # 'over' specifier(비파괴)
    UsdGeom.PointInstancer(over).CreateInvisibleIdsAttr(Vt.Int64Array(hidden))
    lc.GetRootLayer().Save()

    print(f"WROTE {path}")
    print(f"  hidden : {len(hidden)} / {len(tagged)} rail segments (invisibleIds)")
    print(f"  합성해서 보기: usdview {out_dir}/composed.usda")
    print("  비파괴 확인: 이 파일의 invisibleIds 비우면 raw 2줄로 복귀")
    return path


if __name__ == "__main__":
    map_dir = sys.argv[1] if len(sys.argv) > 1 else "../input/fab_map"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "../out"
    build(map_dir, out_dir)
