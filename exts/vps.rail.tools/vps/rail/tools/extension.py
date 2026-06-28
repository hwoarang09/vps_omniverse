"""
VPS Rail Tools — 레일 색 토글 UI (omni.ui).

converter 가 USD 에 구운 타입별 머티리얼 `/World/Looks/Rail_{green,pink,red}` 의
셰이더 입력값(diffuseColor/metallic/roughness)을 버튼으로 직접 바꿔서 색을 토글.
  - realistic: 알루미늄 그레이 메탈 (현실 OHT 트랙) — 셋 다 동일 그레이
  - debug    : 직선=초록 / 곡선 직선영역=분홍 / 곡선 호=빨강

variantSet 으로 '바인딩'을 갈아끼우는 방식은 PointInstancer(/World/Rails) 인스턴스
색이 런타임에 dirty 처리 안 돼 화면 갱신이 안 됐음. 그래서 머티리얼 '값'을 바꾼다
(Hydra 가 값 변경은 인스턴서에도 반영).

MQTT 차량 viz(vps.live.viz)와 분리 — 색 토글은 MQTT 와 무관하므로 별도 확장.
"""
from __future__ import annotations

import omni.ext
import omni.ui as ui
import omni.usd
from pxr import Gf, UsdShade

# 타입별 머티리얼 경로 — converter(build_base.py)가 author 하는 prim 경로와 일치.
RAIL_MAT_PATHS = {
    "green": "/World/Looks/Rail_green",
    "pink":  "/World/Looks/Rail_pink",
    "red":   "/World/Looks/Rail_red",
}

# 색/PBR 값 — build_base.py 의 realistic 기본값 및 debug 색과 반드시 일치해야 함.
#   realistic: 셋 다 알루미늄 그레이 (빌드 직후 기본값).
RAIL_REALISTIC = {
    "green": {"diffuseColor": (0.52, 0.57, 0.64), "metallic": 0.65, "roughness": 0.35},
    "pink":  {"diffuseColor": (0.52, 0.57, 0.64), "metallic": 0.65, "roughness": 0.35},
    "red":   {"diffuseColor": (0.52, 0.57, 0.64), "metallic": 0.65, "roughness": 0.35},
}
#   debug: 타입별 색, 셋 다 metallic 0.10 / roughness 0.50.
RAIL_DEBUG = {
    "green": {"diffuseColor": (0.15, 0.85, 0.25), "metallic": 0.10, "roughness": 0.50},
    "pink":  {"diffuseColor": (1.00, 0.45, 0.75), "metallic": 0.10, "roughness": 0.50},
    "red":   {"diffuseColor": (0.95, 0.12, 0.12), "metallic": 0.10, "roughness": 0.50},
}


class VpsRailToolsExtension(omni.ext.IExt):
    def on_startup(self, ext_id: str):
        print("[vps.rail.tools] startup")
        self._win = None
        self._label = None
        self._debug = False   # 현재 모드: False=realistic, True=debug
        self._win = ui.Window("VPS Rail", width=240, height=96)
        with self._win.frame:
            with ui.VStack(spacing=6, height=0):
                self._label = ui.Label(f"railColor: {self._mode_name()}")
                ui.Button("레일 색 토글 (realistic ↔ debug)",
                          clicked_fn=self._toggle, height=32)

    def on_shutdown(self):
        print("[vps.rail.tools] shutdown")
        self._win = None
        self._label = None

    # --- 머티리얼 셰이더 입력값 토글 헬퍼 ---
    def _mode_name(self):
        return "debug" if self._debug else "realistic"

    def _surface_shader(self, stage, mat_path):
        """머티리얼 prim 의 surface output 에 연결된 셰이더를 반환 (없으면 None)."""
        prim = stage.GetPrimAtPath(mat_path)
        if not prim:
            return None
        mat = UsdShade.Material(prim)
        if not mat:
            return None
        src = mat.GetSurfaceOutput().GetConnectedSource()
        if src:
            return UsdShade.Shader(src[0].GetPrim())
        # 폴백: 관례상 {mat}/Shader 에 셰이더가 있음.
        sh_prim = stage.GetPrimAtPath(mat_path + "/Shader")
        return UsdShade.Shader(sh_prim) if sh_prim else None

    def _apply(self, values):
        """values[key] = {diffuseColor, metallic, roughness} 를 3개 머티리얼에 적용."""
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return False
        applied = 0
        for key, mat_path in RAIL_MAT_PATHS.items():
            sh = self._surface_shader(stage, mat_path)
            if sh is None:
                continue
            v = values[key]
            di = sh.GetInput("diffuseColor")
            mi = sh.GetInput("metallic")
            ri = sh.GetInput("roughness")
            if di:
                di.Set(Gf.Vec3f(*v["diffuseColor"]))
            if mi:
                mi.Set(v["metallic"])
            if ri:
                ri.Set(v["roughness"])
            applied += 1
        return applied > 0

    def _toggle(self):
        nxt_debug = not self._debug
        values = RAIL_DEBUG if nxt_debug else RAIL_REALISTIC
        if not self._apply(values):
            print("[vps.rail.tools] Rail_{green,pink,red} 머티리얼 없음 — base/composed.usda 열렸는지 확인")
            if self._label is not None:
                self._label.text = "railColor: (스테이지/머티리얼 없음)"
            return
        self._debug = nxt_debug
        if self._label is not None:
            self._label.text = f"railColor: {self._mode_name()}"
        print(f"[vps.rail.tools] railColor -> {self._mode_name()}")
