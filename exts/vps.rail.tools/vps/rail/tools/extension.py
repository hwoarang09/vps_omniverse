"""
VPS Rail Tools — 레일 색 토글 UI (omni.ui).

converter 가 USD 에 구운 `railColor` variantSet(realistic/debug)을 버튼으로 전환.
  - realistic: 알루미늄 그레이 메탈 (현실 OHT 트랙)
  - debug    : 직선=초록 / 곡선 직선영역=분홍 / 곡선 호=빨강

MQTT 차량 viz(vps.live.viz)와 분리 — 색 토글은 MQTT 와 무관하므로 별도 확장.
"""
from __future__ import annotations

import omni.ext
import omni.ui as ui
import omni.usd

RAIL_VARIANT_PRIM = "/World/Protos"     # converter 가 variantSet 을 여기에 author
RAIL_VARIANT_SET = "railColor"


class VpsRailToolsExtension(omni.ext.IExt):
    def on_startup(self, ext_id: str):
        print("[vps.rail.tools] startup")
        self._win = None
        self._label = None
        self._win = ui.Window("VPS Rail", width=240, height=96)
        with self._win.frame:
            with ui.VStack(spacing=6, height=0):
                self._label = ui.Label(f"railColor: {self._variant() or '(스테이지 미로드)'}")
                ui.Button("레일 색 토글 (realistic ↔ debug)",
                          clicked_fn=self._toggle, height=32)

    def on_shutdown(self):
        print("[vps.rail.tools] shutdown")
        self._win = None
        self._label = None

    # --- railColor variantSet 헬퍼 ---
    def _vset(self):
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return None
        prim = stage.GetPrimAtPath(RAIL_VARIANT_PRIM)
        if not prim:
            return None
        vs = prim.GetVariantSet(RAIL_VARIANT_SET)
        return vs if vs and vs.GetVariantNames() else None

    def _variant(self):
        vs = self._vset()
        return vs.GetVariantSelection() if vs else None

    def _toggle(self):
        vs = self._vset()
        if vs is None:
            print("[vps.rail.tools] railColor variantSet 없음 — y_short.usda 열렸는지 확인")
            if self._label is not None:
                self._label.text = "railColor: (스테이지/variantSet 없음)"
            return
        nxt = "debug" if vs.GetVariantSelection() == "realistic" else "realistic"
        vs.SetVariantSelection(nxt)
        if self._label is not None:
            self._label.text = f"railColor: {nxt}"
        print(f"[vps.rail.tools] railColor -> {nxt}")
