# 레일 렌더링 & 분기/합류 trim 로직 (정본)

> 맵→USD 변환에서 **2줄 레일(dual-rail)**을 그리고, 분기/합류에서 겹치거나 길을 막는
> 레일 조각을 자동으로 지우는 기하 로직 정리. 코드: `converter/geometry.py`,
> `converter/convert_map_to_usd.py`. 빌드: `converter/.venv/bin/python
> convert_map_to_usd.py ../input/y_short ../out/y_short.usda` → Composer Reload.
> (WSL 기본 python 엔 pxr 없음. 반드시 `.venv` 사용.)

---

## 0. 한 줄 요약

각 곡선 edge 는 **`직선 - 호(arc) - 직선`** 구조다(`직-곡-직-곡-직` for CSC).
edge 를 좌우 ±gauge/2 로 오프셋해 2줄 레일을 그린 뒤, **합류/분기에서 (1) 호의
바깥(outer) 레일과 (2) 직선영역이 다른 길을 막는 부분**만 잘라낸다.
**핵심 원칙: "겹치는 것"이 아니라 "veh 통로를 가로막는 것"을 지운다.**

---

## 1. 2줄 레일 (dual-rail)

- edge 중심선을 각 점의 수직벡터(`_perp_offsets`)로 ±`RAIL_GAUGE`/2 오프셋 → 좌(L)/우(R) 레일.
- 곡선 바깥 레일은 자동으로 큰 반경. 박스 세그먼트 PointInstancer 1개로 인스턴싱.
- 주요 상수: `RAIL_GAUGE=0.4`, `RAIL_RAIL_W=0.1`, `RAIL_H`, `RAIL_SEG_MULT=1.6`(조각 겹쳐
  연속 리본), 렌더 densify `RAIL_DRAW_MAXLEN=0.5`.
- 곡선 분할 `RAIL_CURVE_SEGS = {90:40, 180:40, CSC:40, S:36}`.
  - **90 이 20→40 으로 올라간 이유**: 호가 렌더 박스 8~11개로만 그려지면 trim 경계가
    박스에 snap 돼 edge 마다 ±12~17% 들쭉날쭉. 40 으로 올려 14~22개 → ±5%, 균일.

## 2. 디버그 컬러링 (trim 디버깅용)

`dual_rail_segments` 가 세그먼트마다 색 클래스를 매겨 3색 proto + `proto_indices` 로 렌더:

| 색 | 의미 |
|---|---|
| 🟢 초록 | **직선 edge** (LINEAR) |
| 🩷 분홍 | **곡선 edge 의 직선영역** (lead-in / lead-out / CSC 중간직선) |
| 🔴 빨강 | **곡선 edge 의 호(arc) 영역** |

- 직선/호 구분 = `_arc_t_intervals(clean)`: **원본 정점**(densify 전)의 꺾임각이
  `RAIL_ARC_TURN_DEG=1°` 초과면 그 정점 인접 2세그를 호로 마킹 → 정규화 t-인터벌.
  (densify 가 직선을 잘게 쪼개도 chord 꺾임 기준이라 안 흔들림. 경계 ±1세그 오차는 있음.)

## 3. trim = `hide_curve_edges` (두 메커니즘 병합)

`hide_curve_edges = hide_curve_arc(호) + hide_curve_lead(직선영역)`,
edge별 (left_iv, right_iv) 정규화 인터벌을 병합(`_merge_intervals`). 렌더는 이 인터벌
구간만 안 그림. **직선 edge(LINEAR)는 본선이라 절대 안 건드림.**

### (A) 호 outer trim — `hide_curve_arc`
- **각 호(arc)마다**, 그 호가 **가까운 edge 끝**(fn/tn 중 lead 가 짧은 쪽)에서 **호 길이의
  비율 + 그쪽 lead** 를 그 호의 **바깥(outer) 레일**에서 삭제. inner 호는 보존.
  - **CSC**(호 2개, 같은 방향): fn 쪽 호1, tn 쪽 호2 각각 → 최대 2번.
  - **CURVE_90**(호 1개): 짧은 lead 쪽 끝 1번.
  - **CURVE_180**(호 1개, U턴): 단일 호를 **apex(중점)에서 반쪽 2개로 쪼개** CSC 처럼 fn/tn
    각각 → 양끝 겹침 제거 + apex(top) 보존.
  - **S_CURVE**(호 2개, **반대 방향**): 호별로 outer 가 다른 레일(`_arc_turn_sign` 으로 호별
    판정). 호각이 작아(≈43° < clear각 60°) 호 전체가 overlap → **비율 1.0(통째)**. 차선변경
    이라 양끝 다 평행 라인 존재 → **degree 게이트 없이 양쪽 호 다 삭제**.
- 비율 = `RAIL_CSC_ARC_HIDE`(0.7) = **90° 호의 기하 overlap 비율**(`_arc_clear_frac(r=0.5,
  g)`≈0.718). **곡선영역(arc) 기준**이라 90/180/CSC(90° 호) 전부 0.7 공유. S(작은 호)만 1.0.
- outer = 호별 `_arc_turn_sign`(CCW→R, CW→L). (CSC/90/180 은 호 방향 일관 → edge 단위와 동일)
- **degree 2(단순연결)는 건드리지 않음** (S 제외) — 그 호는 실제 경로라 지우면 U 가 깨짐.

### (B) 직선영역 방해 trim — `hide_curve_lead`
- 곡선의 **직선영역(lead-in/out)이 다른 통로를 "가로막는" 부분**만 삭제(**양쪽 레일**).
- 가로막음 판정 = 그 직선영역 레일이 이웃(노드 공유) edge 중심선 corridor(±gauge/2) **안**이고,
  그 이웃과 이루는 **각 > `RAIL_CROSS_ANGLE`(30°)** = transverse(가로지름).
- **평행(나란히)하면 보존** — veh 가 나란히 가면 안 막으니까(각≈0 → 안 잡힘).

## 4. 핵심 원칙 (반복 금지 — 실패에서 수렴한 결론)

1. **"겹침" ≠ "방해".** 사실 edge 끼리 물리적으로 겹치는 일은 드물다. 평행하게 나란히
   지나는 건 통행을 안 막으므로 **보존**한다. **다른 길을 가로지르며 막는 것만 삭제.**
2. **곡선만 자른다. 직선(LINEAR)은 본선 → 항상 보존.**
3. **호 outer 만, inner 는 보존.** outer 가 회전 바깥쪽이라 직선 위로 swing 하며 길을 막음.
4. **호 1개당 1번** 삭제(그 호가 속한 junction 쪽). CSC 는 호 2개라 최대 2번.
5. **합류/분기(degree≥3)에서만.** 단순연결(degree2)은 같은 경로의 연속이라 안 막음.
6. trim 양은 **곡선영역(arc) 기준 ratio** 라 90/180/CSC/S 가 같은 숫자(0.7) 공유.

### 폐기한 접근 (다시 하지 말 것)
- 중심선 band-walk(corridor 기준): outer 가 corridor 한가운데 가로질러도 다 지워 **과지움(뭉텅)**.
- rail-to-rail 전체 스캔(walk 아님): 들락날락해 **조각조각 깨짐**.
- 곡선 양쪽 레일 다 trim: inner 까지 지워 호가 깨짐.
- 한 ratio 를 **edge 전체** 기준으로: 90(호1개)은 양끝에서 양쪽 적용 시 호 전멸.
- 평행 겹침까지 삭제: 길 안 막는 정상 레일을 지워 **개판**.

## 5. 주요 상수 (튜닝 포인트)

| 상수 | 값 | 역할 |
|---|---|---|
| `RAIL_GAUGE` | 0.4 | 두 레일 간격 |
| `RAIL_CSC_ARC_HIDE` | 0.7 | 호에서 노드쪽 삭제 비율(곡선영역 기준) |
| `RAIL_CROSS_ANGLE` | 30° | 직선영역 '가로막음' 판정 각 |
| `RAIL_CURVE_SEGS[90]` | 40 | 호 박스 수(trim 경계 균일도) |
| `RAIL_ARC_TURN_DEG` | 1° | 직선/호 구분 꺾임각 |

## 6. 상태

- ✅ **Stage 2 완료: 곡선 4타입(CSC/90/180/S) 전부 호 outer trim + 직선영역 방해 trim.**
  outer 는 **호별** `_arc_turn_sign` 판정이라 S(호 2개 반대방향)도 호마다 다른 레일로 처리.
  S 는 inner 보존(연속)이 핵심 — 양쪽 레일 다 지우면 곡이 직들을 잇는 거라 토막남. (2026-06-07)
- ⬜ **Stage 3 (다음): 직선(LINEAR) 처리.** 곡선이 가로지르는 직선 라인에서 라인쪽을 끊어
  교차를 뚫기. 현재 직선영역 방해는 노드 공유 이웃만 검사 → 노드 안 나눈 라인을 가로지르는
  교차(특히 S 가 비스듬히 여러 라인 가로지름)는 미처리. 모든 인접 라인 대상 교차 검출 필요.
