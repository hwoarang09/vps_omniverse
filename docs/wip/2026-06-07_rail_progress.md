# 레일 trim 작업 — 완료 (2026-06-07)

✅ **완료. 정본 문서로 이동:** [`../concepts/01_rail_trim.md`](../concepts/01_rail_trim.md)

요약:
- 2줄 레일 + 디버그 컬러(직선=초록 / 곡선 직선영역=분홍 / 호=빨강).
- trim = `compute_rail_hide` = 호 outer(`compute_curve_hide`, 곡선영역 ratio 0.7)
  + 직선영역 방해(`compute_straight_block_hide`, transverse>30°).
- 핵심 원칙: **겹침 ≠ 방해. 길 가로막는 것만 삭제, 평행은 보존.** 직선은 본선이라 보존.

남은 검수: CURVE_180 / S_CURVE (S 는 호 2개 반대방향이라 outer 호별 재판정 필요할 수 있음).
