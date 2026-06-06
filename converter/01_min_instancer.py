"""
2단계: 최소 PointInstancer 테스트.
Three.js로 치면: 큐브 BufferGeometry 1개(prototype)를 InstancedMesh로 만들어
setMatrixAt 으로 여러 위치에 찍는 것과 동일.

USD 대응:
  - prototype  = /World/Protos/Cube (UsdGeom.Cube, 또는 Mesh)
  - instancer  = UsdGeom.PointInstancer
      positions     <- 각 인스턴스 위치 (= instanceMatrix 의 translation)
      protoIndices  <- 어떤 prototype 을 쓸지 (여기선 전부 0)
      (orientations / scales 는 생략 = identity)
"""
from pxr import Usd, UsdGeom, Gf, Vt, Sdf

OUT = "out/01_min_instancer.usda"

stage = Usd.Stage.CreateNew(OUT)

# --- stage 기본 설정 (Three.js엔 없는 개념: 업축/단위를 파일에 명시) ---
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)   # USD 기본 Z-up 사용
UsdGeom.SetStageMetersPerUnit(stage, 1.0)         # 1 unit = 1 m
stage.SetDefaultPrim(stage.DefinePrim("/World", "Xform"))

# --- prototype 큐브 (씬 그래프에서 숨김 위치에 보관) ---
protos_scope = UsdGeom.Scope.Define(stage, "/World/Protos")
cube = UsdGeom.Cube.Define(stage, "/World/Protos/Cube")
cube.CreateSizeAttr(1.0)                            # 1m 큐브
UsdGeom.Imageable(cube).CreateVisibilityAttr(UsdGeom.Tokens.invisible)  # 원본은 숨김

# --- PointInstancer = InstancedMesh ---
inst = UsdGeom.PointInstancer.Define(stage, "/World/Cubes")
# prototypes 릴레이션: protoIndices가 가리킬 prototype 목록
inst.CreatePrototypesRel().SetTargets([cube.GetPath()])

# 4x4 그리드로 16개 인스턴스 (간격 3m)
positions = []
for ix in range(4):
    for iy in range(4):
        positions.append(Gf.Vec3f(ix * 3.0, iy * 3.0, 0.0))

inst.CreatePositionsAttr(Vt.Vec3fArray(positions))
inst.CreateProtoIndicesAttr(Vt.IntArray([0] * len(positions)))  # 전부 prototype 0

stage.GetRootLayer().Save()
print(f"WROTE {OUT}  ({len(positions)} instances)")
