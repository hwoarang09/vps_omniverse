# 레일 렌더링 작업 진행 (2026-06-07)

> 정본 코드: `C:\dev\vps_omniverse\converter\` (geometry.py, convert_map_to_usd.py).
> 빌드: `converter/.venv/bin/python convert_map_to_usd.py ../input/y_short ../out/y_short.usda`
>   → Composer에서 out/y_short.usda Reload. (build_rail_hide.py / rail_hide.map 제거됨)
> 로컬 커밋 6b830d4 (vps_omniverse, remote 없음).

## 현재 규칙 (타입별 정복 중)
**디버그 색**: 직선=초록 / 곡선 직선영역(lead-in·out)=분홍 / 곡선 호=빨강. (`_arc_t_intervals`)

**겹침 trim = `compute_curve_hide` (geometry.py)** — 단일 규칙:
- **곡선의 바깥(outer) 레일만** 숨김. inner·직선은 안 건드림 (직선=본선).
- outer = `_outer_rail_key` = `_turn_sign` (CCW→R, CW→L).
- **끝 노드 degree>=3 (합류/분기)일 때만** 적용. 단일(degree2)은 보존.
- 각 곡선은 **자기 outer 만** 처리 → 파트너 안 지움. 곡선끼리 만나도 각자 패스에서 자기 것.

**CSC (완료)**: 90호+직선+90호. 각 호에서 노드쪽 `RAIL_CSC_ARC_HIDE=0.7` 비율 + lead-in/out 을 outer 에서 숨김. 14개 중 분기/합류 8개 trim, 단일 6개 keep.

## 다음 단계
1. **CURVE_90** — 호 1개. degree>=3 인 노드 쪽 호의 노드쪽 비율만큼 outer. `types` 에 CURVE_90 추가 + 호1개 케이스.
2. CURVE_180, S_CURVE.
3. 다 되면 공통 로직 합치기 + 비율 상수 타입별 튜닝.

## 폐기 (반복 금지)
중심선 band-walk(compute_rail_hide, 과지움 뭉텅) / rail-to-rail 전체스캔(outer corridor 가로질러 조각깨짐) / 곡선 양쪽 레일 trim(inner 깨짐) / degree>1 가드(단일 CSC 과지움). → outer만 + degree>=3 + 호비율.
