"""
build_station_body.py — station(EQ/OHB/STK) 을 device(장비) 로 묶어 station_body.map 생성.

클러스터링 + bay-PCA 로 "그릴 방향(outward)" 결정 + EQ 충돌 clamp + 타입별 기본 모델 배정
을 한 번에 계산해서 MapTool 스타일 .map 파일로 떨군다. 이후 손으로 고쳐도 됨.
(특히 model 컬럼을 바꿔 장비 형상을 EFEM/LPS/NTB 등으로 교체 가능.)
컨버터(convert_map_to_usd.py)는 이 파일이 있으면 그대로 읽어서 장비를 그린다.

usage: python build_station_body.py <map_dir> [out.map]
       out 기본값 = <map_dir>/station_body.map
"""
import sys
from collections import Counter

from mapio import parse_nodes, parse_edges, parse_stations
import geometry as geo

HEADER = (
    "# station_body.map — station(EQ/OHB/STK) → device(장비) 묶음 + 그리기 정보\n"
    "# build_station_body.py 자동생성 (클러스터 + bay-PCA). 손수정 가능.\n"
    "# type  : 대분류 (EQ/OHB/STK)\n"
    "# model : 형상 모델 (EFEM/LPS/NTB/STOCKER/OHB_RACK) — models.py 빌더 키. 바꿔도 됨\n"
    "# center_x,center_y : 본체 중심 (editor 좌표)\n"
    "# dir_x,dir_y       : 본체 폭 축(=bay 진행방향) 단위벡터\n"
    "# out_x,out_y       : 바깥 축(본체가 뻗는 방향, 통로 반대) 단위벡터\n"
    "# width,depth,height: 본체 크기(m)\n"
    "# stations          : 소속 station_name 리스트\n"
)
COLS = ("device_id,type,model,bay,center_x,center_y,dir_x,dir_y,out_x,out_y,"
        "width,depth,height,stations\n")


def _n(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


def main(map_dir, out_path):
    nodes = parse_nodes(f"{map_dir}/nodes.map")
    edges = parse_edges(f"{map_dir}/edges.map")
    stations = parse_stations(f"{map_dir}/station.map")

    devs, clamped = geo.compute_devices(stations, nodes, edges)

    lines = [HEADER, COLS]
    for d in devs:
        cx, cy = d["center"]
        ux, uy = d["dir"]
        ox, oy = d["outward"]
        st = "[" + ", ".join(d["stations"]) + "]"
        lines.append(",".join([
            d["device_id"], d["type"], d["model"], d["bay"], _n(cx), _n(cy),
            _n(ux), _n(uy), _n(ox), _n(oy),
            _n(d["width"]), _n(d["depth"]), _n(d["height"]),
            f'"{st}"',
        ]) + "\n")

    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    nport = sum(len(d["stations"]) for d in devs)
    by_type = Counter(d["type"] for d in devs)
    by_model = Counter(d["model"] for d in devs)
    print(f"WROTE {out_path}")
    print(f"  devices : {len(devs)}  (from {nport} stations)")
    print(f"  by type : {dict(by_type)}")
    print(f"  by model: {dict(by_model)}")
    print(f"  clamped : {clamped} EQ bodies (depth/폭 축소 = 충돌 회피)")


if __name__ == "__main__":
    map_dir = sys.argv[1] if len(sys.argv) > 1 else "../input/fab_map"
    out_path = sys.argv[2] if len(sys.argv) > 2 else f"{map_dir}/station_body.map"
    main(map_dir, out_path)
