"""
라인끊기(line-cut) 기하 그림 생성기 — geometry.py 의 실제 좌표를 matplotlib 로 plot → SVG.

drawio 같은 손그림 대신, build_base/build_line_cut 가 쓰는 그 함수
(geo.dual_rail_segments_tagged + hidden_seg_indices) 를 그대로 호출해
좌(before): raw 2줄 레일 전부(회색), 우(after): 숨겨지는 세그먼트를 '삭제'한 결과
(line_cut invisibleIds 가 가린 그대로). → 그림이 실제 USD 결과와 1:1 (지어내지 않음).

실행: converter/ 안에서
  <venv>/bin/python ../docs/html/assets/_plot_linecut.py
출력: docs/html/assets/linecut-*.svg
"""
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D

# 한글 제목/범례용 폰트 (Windows 맑은 고딕). 없으면 기본 폰트(두부 가능).
for _fp in ("/mnt/c/Windows/Fonts/malgun.ttf",
            "/mnt/c/나눔 글꼴/나눔고딕/NanumFontSetup_TTF_GOTHIC/NanumGothic.ttf"):
    if os.path.exists(_fp):
        font_manager.fontManager.addfont(_fp)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=_fp).get_name()
        break
plt.rcParams["axes.unicode_minus"] = False

# converter/ 를 import path 에 (이 스크립트는 docs/html/assets 에 있으므로)
HERE = os.path.dirname(os.path.abspath(__file__))
CONV = os.path.normpath(os.path.join(HERE, "..", "..", "..", "converter"))
sys.path.insert(0, CONV)

import geometry as geo                                    # noqa: E402
from mapio import parse_edges, parse_nodes                # noqa: E402

MAP_DIR = os.path.normpath(os.path.join(CONV, "..", "input", "fab_map"))
OUT_DIR = HERE


def seg_endpoints(s):
    """tagged seg (pos,yaw,scale,...) → 실제 레일 선분 양끝 (p0,p1).
    scale[0] 은 length*RAIL_SEG_MULT 라 mult 로 되돌려 진짜 길이로."""
    (cx, cy, _cz), yaw, (slen, _w, _h) = s[0], s[1], s[2]
    half = (slen / geo.RAIL_SEG_MULT) / 2.0
    dx, dy = math.cos(yaw) * half, math.sin(yaw) * half
    return (cx - dx, cy - dy), (cx + dx, cy + dy)


def neighbors(focus, edges):
    """focus edge 와 노드를 공유하는 edge 들(1-hop) + focus 자신의 edge_name 집합."""
    ebn = {e.edge_name: e for e in edges}
    f = ebn[focus]
    fnodes = {f.from_node, f.to_node}
    out = {focus}
    for e in edges:
        if {e.from_node, e.to_node} & fnodes:
            out.add(e.edge_name)
    return out, ebn


def view_box(focus, ebn, nodes, keep, tagged, hidden_set,
             pad_frac=0.18, pad_min=2.0, reach_mult=3.5):
    """뷰 정사각 (cx,cy,half). focus 곡선 중심에서 reach_mult×(곡선 반경) 안에 드는
    keep 레일 세그먼트(보임+숨김)를 모두 담는다 → 겹치는 영역과 안 겹치는 주변이
    함께 보임. 긴 직선 이웃은 reach 로 잘라 화면을 통째로 먹지 않게 함.
    그 위에 bbox 의 pad_frac(18%) (최소 pad_min m) 여백."""
    fpts = geo._edge_clean_points(ebn[focus], nodes)
    fxs = [p[0] for p in fpts]
    fys = [p[1] for p in fpts]
    fcx, fcy = (min(fxs) + max(fxs)) / 2.0, (min(fys) + max(fys)) / 2.0
    fspan = max(max(fxs) - min(fxs), max(fys) - min(fys)) / 2.0
    reach = max(fspan * reach_mult, pad_min * 2.0)
    xs, ys = list(fxs), list(fys)
    for i, s in enumerate(tagged):
        if s[4] not in keep:
            continue
        (x0, y0), (x1, y1) = seg_endpoints(s)
        for x, y in ((x0, y0), (x1, y1)):
            if abs(x - fcx) <= reach and abs(y - fcy) <= reach:
                xs.append(x)
                ys.append(y)
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    half = max(max(xs) - min(xs), max(ys) - min(ys)) / 2.0
    half += max(half * pad_frac, pad_min)
    return cx, cy, half


def _draw_panel(ax, tagged, hidden_set, keep, ebn, nodes, focus,
                cx, cy, half, mode):
    """한 패널 그리기. mode='before' → raw 2줄 전부 회색.
    mode='after' → 숨김(line_cut) 세그먼트는 아예 안 그림(=실제로 지워진 결과).
    보이는 레일만 회색으로."""
    for i, s in enumerate(tagged):
        if s[4] not in keep:
            continue
        if mode == "after" and i in hidden_set:   # line_cut 으로 지워진 건 안 그림
            continue
        (x0, y0), (x1, y1) = seg_endpoints(s)
        cls = s[3]
        col = "#7a8290" if cls == geo.RAIL_CLS_GREEN else "#9aa3b0"
        ax.plot([x0, x1], [y0, y1], color=col, lw=2.0,
                solid_capstyle="round", zorder=3)
    for en in keep:
        pts = geo._edge_clean_points(ebn[en], nodes)
        if len(pts) >= 2:
            ax.plot([p[0] for p in pts], [p[1] for p in pts],
                    color="#c9d2e0", lw=0.8, ls=":", zorder=1)
    fe = ebn[focus]
    for nm in (fe.from_node, fe.to_node):
        nd = nodes.get(nm)
        if nd:
            ax.plot(nd.editor_x, nd.editor_y, "o", ms=4, color="#3355cc", zorder=6)
    ax.set_xlim(cx - half, cx + half)
    ax.set_ylim(cy - half, cy + half)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, color="#eef1f6", lw=0.6)
    ax.tick_params(labelsize=7)


def plot_case(edges, nodes, tagged, hidden_set, focus, title, fname,
              extra_focus=None):
    """좌/우 두 장 — 왼: line_cut 전(raw 2줄 전부), 오른: 후(겹침 세그먼트 삭제됨).
    같은 뷰박스로 겹침/비겹침 영역이 함께 보이게 넉넉히 crop 한다."""
    keep, ebn = neighbors(focus, edges)
    if extra_focus:
        for ef in extra_focus:
            kk, _ = neighbors(ef, edges)
            keep |= kk
    cx, cy, half = view_box(focus, ebn, nodes, keep, tagged, hidden_set)

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(12.8, 6.8))
    _draw_panel(axL, tagged, hidden_set, keep, ebn, nodes, focus,
                cx, cy, half, "before")
    _draw_panel(axR, tagged, hidden_set, keep, ebn, nodes, focus,
                cx, cy, half, "after")
    axL.set_title("line_cut 적용 전 — raw 2줄 전부 (base)", fontsize=10)
    axR.set_title("line_cut 적용 후 — 겹침 세그먼트 삭제됨 (invisibleIds)", fontsize=10)
    fig.suptitle(title, fontsize=12, y=0.985)

    legend = [
        Line2D([0], [0], color="#9aa3b0", lw=2.0, label="raw rail (base)"),
        Line2D([0], [0], color="#c9d2e0", lw=0.8, ls=":", label="edge centerline"),
    ]
    fig.legend(handles=legend, fontsize=8.5, loc="lower center", ncol=2,
               framealpha=0.9, bbox_to_anchor=(0.5, -0.005))

    out = os.path.join(OUT_DIR, fname)
    fig.tight_layout(rect=(0, 0.045, 1, 0.95))
    fig.savefig(out, format="svg")
    plt.close(fig)
    nh = sum(1 for i, s in enumerate(tagged) if s[4] in keep and i in hidden_set)
    nt = sum(1 for s in tagged if s[4] in keep)
    print(f"WROTE {out}  ({nh} hidden / {nt} segs, edges={len(keep)})")
    return nh > 0


def main():
    nodes = parse_nodes(os.path.join(MAP_DIR, "nodes.map"))
    edges = parse_edges(os.path.join(MAP_DIR, "edges.map"))

    # build_line_cut.py 와 '완전히 동일'한 hide 조합
    tagged = geo.dual_rail_segments_tagged(edges, nodes)
    hide = geo.merge_hide(geo.hide_curve_edges(edges, nodes),
                          geo.hide_linear_edges(edges, nodes))
    hidden_set = set(geo.hidden_seg_indices(tagged, hide))
    print(f"total tagged={len(tagged)}  hidden={len(hidden_set)}")

    cases = [
        # (focus 곡선 edge, 제목, 파일명)
        ("E0606", "CURVE_90 분기/합류 — 호 outer trim + 직선 안쪽레일 라인끊기",
         "linecut-curve90.svg", None),
        ("E0726", "CURVE_180 U턴 — 호 outer(apex 보존) + 직선 안쪽레일 라인끊기",
         "linecut-curve180.svg", None),
        ("E0203", "CURVE_CSC — 호 2개 outer trim + 직선 안쪽레일 라인끊기",
         "linecut-csc.svg", None),
        ("E0548", "S_CURVE — 호별 반대방향 outer trim + 직선 안쪽레일 라인끊기",
         "linecut-scurve.svg", None),
    ]
    for focus, title, fname, extra in cases:
        plot_case(edges, nodes, tagged, hidden_set, focus, title, fname,
                  extra_focus=extra)


if __name__ == "__main__":
    main()
