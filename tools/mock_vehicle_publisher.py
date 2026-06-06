#!/usr/bin/env python3
"""
Mock vehicle publisher — VPS 없이 Omniverse live viz 파이프라인 테스트용.

가짜 OHT 차량을 **실제 rail(edge) 위로** 이동시키며 MQTT 로 쏜다.
converter 의 곡선 로직(geometry.edge_points)을 그대로 재사용 → 차량이 진짜
레일(직선/커브)을 따라간다. Omniverse extension(vps.live.viz)이 구독해서 렌더.

  [이 스크립트] --(VPS/viz/vehicles)--> mosquitto(9883) --> Omniverse extension

contract (extension.py 와 일치):
  topic   : VPS/viz/vehicles
  payload : JSON 배열  [{"id":1,"x":..,"y":..,"rot":..}, ...]
            x,y = editor 좌표(맵과 동일). z 는 extension 이 rail 높이로 고정.
            rot = heading(도, +X 기준 진행방향). extension 이 Z축 회전으로 적용.

실행:
  python3 mock_vehicle_publisher.py                 # 기본 (rail 따라 8대)
  python3 mock_vehicle_publisher.py --count 20 --speed 10
  python3 mock_vehicle_publisher.py --map ../input/y_short

사전 준비: pip install paho-mqtt
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import sys
import time
from collections import defaultdict

import paho.mqtt.client as mqtt

# converter 모듈(mapio/geometry) import — pxr 의존 없음, plain python3 OK
_HERE = os.path.dirname(os.path.abspath(__file__))
_CONVERTER = os.path.abspath(os.path.join(_HERE, "..", "converter"))
sys.path.insert(0, _CONVERTER)
import mapio      # noqa: E402
import geometry   # noqa: E402

DEFAULT_MAP = os.path.abspath(os.path.join(_HERE, "..", "input", "y_short"))


def _close(a, b, eps=1e-6):
    return abs(a[0] - b[0]) < eps and abs(a[1] - b[1]) < eps


def build_route(nodes, edges):
    """edge 들을 인접관계(to_node→from_node)로 이어붙여 연속 rail polyline 생성.
    분기에선 첫 미방문 edge 를 따라가는 단순 walk — 데모용 한 바퀴 경로."""
    out = defaultdict(list)
    for e in edges:
        out[e.from_node].append(e)

    start = edges[0].from_node
    cur = start
    visited: set[str] = set()
    pts: list[tuple[float, float, float]] = []

    while True:
        nexts = [e for e in out.get(cur, []) if e.edge_name not in visited]
        if not nexts:
            break
        e = nexts[0]
        visited.add(e.edge_name)
        ep = geometry.edge_points(e, nodes)  # [(x,y,z), ...]
        if ep:
            if pts and _close(pts[-1], ep[0]):
                pts.extend(ep[1:])  # 이음새 중복점 제거
            else:
                pts.extend(ep)
        cur = e.to_node
        if cur == start:
            break

    return pts


def cumulative(pts):
    cum = [0.0]
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        cum.append(cum[-1] + math.hypot(dx, dy))
    return cum


def sample(pts, cum, s):
    """경로 시작에서 호길이 s 만큼 진행한 지점의 (x, y, heading_deg)."""
    total = cum[-1]
    s %= total
    i = bisect.bisect_right(cum, s) - 1
    i = max(0, min(i, len(pts) - 2))
    seg = cum[i + 1] - cum[i]
    t = 0.0 if seg <= 0 else (s - cum[i]) / seg
    x0, y0 = pts[i][0], pts[i][1]
    x1, y1 = pts[i + 1][0], pts[i + 1][1]
    x = x0 + (x1 - x0) * t
    y = y0 + (y1 - y0) * t
    heading = math.degrees(math.atan2(y1 - y0, x1 - x0))
    return x, y, heading


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mock OHT publisher — moves along real rails")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=9883)
    p.add_argument("--topic", default="VPS/viz/fab_0/vehicles")
    p.add_argument("--map", default=DEFAULT_MAP, help="맵 폴더 (nodes.cfg/edges.cfg)")
    p.add_argument("--count", type=int, default=8, help="차량 수")
    p.add_argument("--period", type=float, default=0.5, help="주기 publish 간격(s) — VPS 0.5s 모사")
    p.add_argument("--speed", type=float, default=6.0, help="차량 속도 (m/s)")
    p.add_argument("--move", type=float, default=4.0, help="이동 구간 길이(s)")
    p.add_argument("--stop", type=float, default=2.0, help="정지 구간 길이(s, 0이면 정지 없음)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    nodes = mapio.parse_nodes(os.path.join(args.map, "nodes.cfg"))
    edges = mapio.parse_edges(os.path.join(args.map, "edges.cfg"))
    pts = build_route(nodes, edges)
    if len(pts) < 2:
        print(f"[mock] route 생성 실패 (pts={len(pts)}) — 맵 경로 확인: {args.map}")
        return
    cum = cumulative(pts)
    total = cum[-1]
    print(f"[mock] rail route: {len(pts)} pts, length={total:.1f}m")

    client = mqtt.Client()
    print(f"[mock] connecting {args.host}:{args.port} ...")
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()
    print(f"[mock] {args.count} OHT, speed={args.speed}m/s, periodic={args.period}s, "
          f"move/stop={args.move}/{args.stop}s, topic='{args.topic}'")
    print("[mock] 포맷: {t: sim_ms, v: [[id,x,y,rot,spd],...]}  / Ctrl+C to stop")

    spacing = total / args.count  # 차량 균등 배치
    traveled = 0.0                # 누적 주행거리 (move 구간에서만 증가)

    def publish(sim_ms, spd):
        v = []
        for i in range(args.count):
            x, y, heading = sample(pts, cum, traveled + i * spacing)
            v.append([i + 1, round(x, 3), round(y, 3), round(heading, 1), round(spd, 2)])
        client.publish(args.topic, json.dumps({"t": round(sim_ms, 1), "v": v}), qos=0)

    t0 = time.time()
    last = t0
    phase = "move"
    phase_start = t0
    last_pub_ms = -1e9  # 시작 즉시 publish
    try:
        while True:
            now = time.time()
            dt = now - last
            last = now
            sim_ms = (now - t0) * 1000.0  # sim-time (항상 진행)

            # phase 전환
            if phase == "move" and (now - phase_start) >= args.move and args.stop > 0:
                phase = "stop"
                phase_start = now
                publish(sim_ms, 0.0)       # ← 정지 이벤트 (speed 0, 멈춘 위치)
            elif phase == "stop" and (now - phase_start) >= args.stop:
                phase = "move"
                phase_start = now
                last_pub_ms = -1e9          # 재개 즉시 publish

            if phase == "move":
                # 가속/감속 램프 — 등속 대신 출발/정지를 부드럽게 (실 VPS 감속 모사)
                tp = now - phase_start
                ramp = min(1.0, args.move / 2.0)
                if tp < ramp:
                    spd = args.speed * (tp / ramp)                      # 가속
                elif tp > args.move - ramp:
                    spd = args.speed * max(0.0, (args.move - tp) / ramp)  # 감속
                else:
                    spd = args.speed                                    # 등속
                traveled += spd * dt
                if sim_ms - last_pub_ms >= args.period * 1000.0:
                    publish(sim_ms, spd)
                    last_pub_ms = sim_ms
            # stop 구간엔 아무것도 안 보냄 → 수신측 freeze (last 샘플 유지)

            time.sleep(0.03)
    except KeyboardInterrupt:
        print("\n[mock] stopped")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
