"""
build_rail_hide.py — 분기/합류 노드에서 가릴 레일 구간(rail_hide.map) 자동 생성.

[1단계] CURVE_90 곡선만: 분기노드(degree>=3)에 붙은 90도 곡선의 **바깥 레일 일부**를
노드 쪽에서 가리도록 구간을 계산해 떨군다. 직선/180/CSC/S_CURVE 는 추후.
생성 후 사람이 left_hide/right_hide 의 구간 숫자를 직접 튜닝하면 됨.

usage: python build_rail_hide.py <map_dir> [out.map]
       out 기본값 = <map_dir>/rail_hide.map
"""
import sys
import json

from mapio import parse_nodes, parse_edges
import geometry as geo

HEADER = (
    "# rail_hide.map — 분기/합류에서 안 그릴 레일 구간 (edge 따라 0~1 정규화)\n"
    "# [1단계] CURVE_90 바깥 레일만 자동. left_hide/right_hide = [[a,b],...]\n"
    "# 가리는 건 항상 두 줄 중 바깥쪽. 양끝이 분기+합류면 구간 2개.\n"
    "# 값 직접 수정해서 가리는 양 튜닝 가능.\n"
)
COLS = "edge_name,left_hide,right_hide\n"


def main(map_dir, out_path):
    nodes = parse_nodes(f"{map_dir}/nodes.cfg")
    edges = parse_edges(f"{map_dir}/edges.cfg")
    hide = geo.compute_rail_hide(edges, nodes)

    lines = [HEADER, COLS]
    for e in edges:
        if e.edge_name in hide:
            l, r = hide[e.edge_name]
            lines.append(f'{e.edge_name},"{json.dumps(l)}","{json.dumps(r)}"\n')

    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"WROTE {out_path}")
    print(f"  edges with hidden rail intervals: {len(hide)} (밴드 겹침 정밀계산)")


if __name__ == "__main__":
    map_dir = sys.argv[1] if len(sys.argv) > 1 else "../input/y_short"
    out_path = sys.argv[2] if len(sys.argv) > 2 else f"{map_dir}/rail_hide.map"
    main(map_dir, out_path)
