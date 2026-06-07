# 레일 trim 진행 (2026-06-07)

정본 개념: [`../concepts/01_rail_trim.md`](../concepts/01_rail_trim.md)

## ✅ Stage 2 — 곡선 4타입 outer 호 trim (완료)
- CSC/90/180/S. `compute_curve_hide` (호별 `_arc_turn_sign` outer 판정).
- **모든 곡선 fn=분기(outdeg≥2)/tn=합류(indeg≥2)일 때만** 호 outer 삭제. (S 도 한쪽 끝이
  단순연속이면 그쪽 안 지움.) `compute_straight_block_hide`: 곡선 직선영역 방해.
- exact-clip: hide 인터벌을 정확한 t 에서 잘라 박스단위 snap 제거(`_keep_subsegs`).
- **emissive 절대 금지** (37k 레일 emissive→RTX GI 폭주→HydraEngine error code 6).

## ✅ Stage 3 — 직선(LINEAR) 라인 끊기 (90 케이스 완료)
`compute_line_cut_hide` — 직선 **안쪽 레일 1줄**을 분기/합류 90곡선 기준 **노드에서
2×radius** 만큼 자동 삭제. (`RAIL_LINE_CUT_K=2.0`, E0006 수동 캘리브레이션 [0,0.325]/
[0.675,1.0] ≈ 2r 역산으로 검증.)
  - 방향매칭: 라인 fn=분기(curve.from==node) / tn=합류(curve.to==node) 90 만.
  - 안쪽 레일 = 라인진행 × 곡선 far-end cross 부호.
  - line_cut.map 있으면 non-empty 항목만 수동 오버라이드.

## ⬜ Stage 3 남은 케이스 (다음)
- **CURVE_180** 이 직선에 분기/합류할 때 라인 끊기 (지금 작업 시작).
- 그담 CURVE_CSC, S_CURVE.
- 각 타입별로 "노드에서 얼마" 공식 역산 (90=2r 처럼).
