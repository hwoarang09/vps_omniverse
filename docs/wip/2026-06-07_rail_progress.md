# 레일 렌더링 작업 진행 (2026-06-07 임시저장)

> 다음 세션에서 이어서. 정본 코드: `C:\dev\vps_omniverse\converter\` (geometry.py, convert_map_to_usd.py, build_rail_hide.py).
> 실행: `converter/.venv/bin/python ...` (WSL python엔 pxr 없음, venv에 usd-core).
> 워크플로: `build_rail_hide.py ../input/y_short` → `convert_map_to_usd.py ../input/y_short ../out/y_short.usda` → Composer에서 out/y_short.usda Reload.

## 현재 상태 (= "여기 근처", 곡선만 trim, 깔끔)
- **2줄 레일**(dual-rail): edge 중심선 ±gauge/2(0.2) 오프셋. 곡선 바깥 자동 큰 반경. 박스 세그먼트 PointInstancer 1개. `RAIL_GAUGE=0.4`, `RAIL_RAIL_W=0.1`, `RAIL_SEG_MULT=1.6`(연속), 곡선분할 `RAIL_CURVE_SEGS`(90:20,180:40,CSC:40,S:36), 렌더 densify `RAIL_DRAW_MAXLEN=0.5`.
- **분기/합류 겹침 제거 = `compute_rail_hide` (geometry.py)**:
  - **곡선 edge만** trim (직선은 메인레일이라 안 자름).
  - 각 곡선 레일을 **자기 끝 노드에서 안쪽으로 걸으며**, 노드 공유 다른 edge 밴드(중심선±gauge/2) 안인 동안 가리고 벗어나면 멈춤. `RAIL_BAND_TOL = gauge/2 + 1e-6` (**정확히 gauge/2**; +0.05 로 키우면 walk 이 옆 어슬렁대다 엉뚱한 곳 과지움). 정밀 `RAIL_TRIM_FINE=0.1` densify, 후보 노드 `RAIL_CAND_NEAR=3.5` 근처.
  - 결과를 `input/y_short/rail_hide.map`(edge별 left/right 정규화 인터벌)에 저장. 렌더(`dual_rail_segments`)는 그 인터벌만 적용.
  - **자동·universal**: edge이름/라벨 하드코딩 0. 새 맵도 build_rail_hide.py 한번이면 됨. **rail_hide.map 손편집 금지(캐시)**.
- 현재 373곡선 trim, 24,276 세그먼트. 사용자 평가: 곡선쪽 깔끔(image #9).

## 다음 단계: 직선이 곡선 덮는 경우 직선쪽 삭제 (미완)
- 곡선↔직선 겹침에서 지금은 **곡선쪽만** 지움. 직선이 곡선 속으로 파고든 경우 **직선쪽도** 지워야 완성.
- **주의: 지난 시도들 다 과지움(개판) 났음** — 이유:
  - 직선도 trim 풀면 곡선의 lead-in/out(직선영역)까지 의미없이 다 지워짐.
  - 단일 tol=정확히 gauge/2 = junction마다 들쭉날쭉(칼날).
  - GEN 넉넉히(0.28)+interior 2-임계 = run 이 너무 길게 확장돼 과지움.
- **다음 세션 접근 제안**:
  - 직선 trim 은 **strict interior(dist < gauge/2 − margin)** 에서만, 그리고 **run 종료를 정확히 밴드 경계(gauge/2)** 로 (GEN 으로 늘리지 말 것).
  - 또는 직선↔곡선 **선분∩호 해석적 교점**으로 정확한 trim point 계산(진짜 A안). 일직선 직선 연속은 끝점 투영(dist>gauge/2)이라 자동 제외됨.
  - 검증: 일직선 직선에 stub 안 생기고, 직선이 곡선 덮던 곳만 지워지고, 곡선쪽 그대로인지.

## 실패 로그 (반복 금지)
degree>=3 게이트(합류 텅 빔) / collinear-straight 게이트(전부 날아감) / 거리+near-junction 마진(U턴 중간 오지움·직선 stub) / 곡선타입별 arc-clear%(케이스마다 깨짐) / 직선 trim+interior 2-임계(과지움). → **곡선만 + 노드에서 밴드 걷기 + tol gauge/2+0.05** 가 현재 베스트.

## 같이 한 다른 작업 (완료)
- EQ/LPS/NTB/STK 장비 모델(models.py, station_body.map), OHB 거치대, 조명(돔+태양, 형광등 제거), 메모리 [[omniverse-eq-equipment]] [[omniverse-rail-rendering]] [[omniverse-workspace]].
- fps: RTX Real-Time 2.0 + DLSS Performance로 60fps. 반사/GI/해상도 설정은 "Real-Time 2.0" 탭(옛 Ray Tracing 탭 없음).
