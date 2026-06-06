"""
재사용 USD 빌더 — 맵→USD 변환의 코어 헬퍼.
Three.js 멘탈 모델 매핑을 주석으로 달아둠.

핵심 아이디어: 모든 형상을 단위 큐브(-0.5..0.5) 1개 prototype로 만들고,
PointInstancer 의 (positions / orientations / scales) 로 변형해서 찍는다.
= Three.js 에서 BoxGeometry(1,1,1) 하나를 InstancedMesh 로 만들고
  setMatrixAt(i, compose(pos, quat, scale)) 하는 것과 1:1 대응.
"""
import math
from pxr import Usd, UsdGeom, UsdShade, UsdLux, Gf, Vt, Sdf


def make_stage(path, up="Z", meters_per_unit=1.0, root="/World"):
    """빈 stage 생성 + 업축/단위/defaultPrim 세팅."""
    stage = Usd.Stage.CreateNew(path)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z if up == "Z" else UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, meters_per_unit)
    stage.SetDefaultPrim(stage.DefinePrim(root, "Xform"))
    UsdGeom.Scope.Define(stage, root + "/Protos")  # prototype 보관 scope
    return stage


def add_unit_cube_proto(stage, path, color=(0.8, 0.8, 0.8)):
    """
    단위 큐브 Mesh prototype (-0.5..0.5). 원본은 invisible.
    UsdGeom.Cube 대신 Mesh 를 쓰는 이유: 비균등 스케일(긴 레일)이 깔끔.
    = THREE.BoxGeometry(1,1,1).
    """
    mesh = UsdGeom.Mesh.Define(stage, path)
    # 8 정점
    pts = [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
           (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)]
    mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in pts]))
    # 6면 * 4정점 (quad), 바깥쪽 CCW winding
    faces = [4, 5, 6, 7,   # top    +Z
             0, 3, 2, 1,   # bottom -Z
             0, 1, 5, 4,   # front  -Y
             2, 3, 7, 6,   # back   +Y
             1, 2, 6, 5,   # right  +X
             3, 0, 4, 7]   # left   -X
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([4] * 6))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(faces))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)  # 각진 박스 (smoothing 끔)
    # 면별 바깥 법선 명시 (없으면 조명이 어둡게 계산 -> 색이 검게 보임)
    fn = [(0, 0, 1), (0, 0, -1), (0, -1, 0), (0, 1, 0), (1, 0, 0), (-1, 0, 0)]
    normals = [Gf.Vec3f(*n) for n in fn for _ in range(4)]
    nattr = mesh.CreateNormalsAttr(Vt.Vec3fArray(normals))
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
    mesh.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*color)]))
    # 주의: PointInstancer prototype 은 invisible 로 두면 안 됨.
    # 인스턴스가 prototype 의 visibility 를 상속 -> 전부 사라짐.
    # prototypes 릴레이션 대상은 어차피 단독 렌더되지 않으므로 visible 로 둔다.
    return mesh


def add_box(stage, path, center, size, material=None, color=(0.5, 0.5, 0.5)):
    """
    월드 좌표에 단독 박스 Mesh 1개 (center/size 를 정점에 베이크 -> xformOp 불필요).
    이름 있는 prim 이라 Composer 에서 클릭 선택됨. = 장비 본체 1대.
    """
    cx, cy, cz = center
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    pts = [(cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz),
           (cx + hx, cy + hy, cz - hz), (cx - hx, cy + hy, cz - hz),
           (cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz),
           (cx + hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz + hz)]
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in pts]))
    faces = [4, 5, 6, 7,  0, 3, 2, 1,  0, 1, 5, 4,
             2, 3, 7, 6,  1, 2, 6, 5,  3, 0, 4, 7]
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([4] * 6))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(faces))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    fn = [(0, 0, 1), (0, 0, -1), (0, -1, 0), (0, 1, 0), (1, 0, 0), (-1, 0, 0)]
    mesh.CreateNormalsAttr(Vt.Vec3fArray([Gf.Vec3f(*n) for n in fn for _ in range(4)]))
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
    if material is not None:
        bind_material(mesh, material)
    else:
        mesh.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*color)]))
    return mesh


def add_oriented_box(stage, path, center, u2d, v2d, half, material=None, color=(0.5, 0.5, 0.5)):
    """
    XY 평면에서 회전된 박스 Mesh. u2d=폭축, v2d=깊이축(단위벡터 2D), z 는 수직.
    half=(hw,hd,hh). 정점을 월드좌표로 베이크 -> xformOp 불필요, 이름있는 prim.
    bay 진행방향(u) / 통로 바깥방향(v) 으로 장비 본체·포트를 정렬하는 데 사용.
    """
    cx, cy, cz = center
    ux, uy = u2d
    vx, vy = v2d
    hw, hd, hh = half

    def c(a, b, h):
        return (cx + ux * a + vx * b, cy + uy * a + vy * b, cz + h)

    pts = [c(-hw, -hd, -hh), c(hw, -hd, -hh), c(hw, hd, -hh), c(-hw, hd, -hh),
           c(-hw, -hd, hh), c(hw, -hd, hh), c(hw, hd, hh), c(-hw, hd, hh)]
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in pts]))
    faces = [4, 5, 6, 7,  0, 3, 2, 1,  0, 1, 5, 4,
             2, 3, 7, 6,  1, 2, 6, 5,  3, 0, 4, 7]
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([4] * 6))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(faces))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    fn = [(0, 0, 1), (0, 0, -1), (-vx, -vy, 0), (vx, vy, 0), (ux, uy, 0), (-ux, -uy, 0)]
    mesh.CreateNormalsAttr(Vt.Vec3fArray([Gf.Vec3f(*n) for n in fn for _ in range(4)]))
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
    if material is not None:
        bind_material(mesh, material)
    else:
        mesh.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*color)]))
    return mesh


def add_box_edges(stage, path, center, u2d, v2d, half,
                  color=(0.22, 0.22, 0.24), width=0.03):
    """
    회전박스의 12 모서리를 BasisCurves(linear) 로 그림 = 박스 윤곽선.
    장비 본체 모서리마다 회색선 → 인접 장비끼리 경계가 또렷 (실제 fab 장비 외곽 느낌).
    add_oriented_box 와 동일한 (center,u,v,half) 로 호출.
    """
    cx, cy, cz = center
    ux, uy = u2d
    vx, vy = v2d
    hw, hd, hh = half

    def c(a, b, h):
        return (cx + ux * a + vx * b, cy + uy * a + vy * b, cz + h)

    P = [c(-hw, -hd, -hh), c(hw, -hd, -hh), c(hw, hd, -hh), c(-hw, hd, -hh),
         c(-hw, -hd, hh), c(hw, -hd, hh), c(hw, hd, hh), c(-hw, hd, hh)]
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
             (0, 4), (1, 5), (2, 6), (3, 7)]
    pts = []
    for a, b in edges:
        pts.append(P[a])
        pts.append(P[b])
    bc = UsdGeom.BasisCurves.Define(stage, path)
    bc.CreateTypeAttr(UsdGeom.Tokens.linear)
    bc.CreateCurveVertexCountsAttr(Vt.IntArray([2] * len(edges)))
    bc.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in pts]))
    bc.CreateWidthsAttr(Vt.FloatArray([width]))
    bc.SetWidthsInterpolation(UsdGeom.Tokens.constant)
    bc.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*color)]))
    return bc


def add_rect_outline(stage, path, center, u2d, v2d, hw, hd,
                     color=(0.30, 0.32, 0.36), width=0.06):
    """수평 사각형 테두리(4 변)만 BasisCurves 로. = 박스 바닥면 윤곽선. OHB 거치대 footprint."""
    cx, cy, cz = center
    ux, uy = u2d
    vx, vy = v2d

    def c(a, b):
        return (cx + ux * a + vx * b, cy + uy * a + vy * b, cz)

    P = [c(-hw, -hd), c(hw, -hd), c(hw, hd), c(-hw, hd)]
    seg = [P[0], P[1], P[1], P[2], P[2], P[3], P[3], P[0]]
    bc = UsdGeom.BasisCurves.Define(stage, path)
    bc.CreateTypeAttr(UsdGeom.Tokens.linear)
    bc.CreateCurveVertexCountsAttr(Vt.IntArray([2, 2, 2, 2]))
    bc.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in seg]))
    bc.CreateWidthsAttr(Vt.FloatArray([width]))
    bc.SetWidthsInterpolation(UsdGeom.Tokens.constant)
    bc.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*color)]))
    return bc


def add_unit_plane_proto(stage, path, color=(0.8, 0.8, 0.8), double_sided=True):
    """
    단위 평면 prototype = THREE.PlaneGeometry(1,1).
    XY 평면 1x1 quad, 법선 +Z, 원점 중심 (-0.5..0.5). 원본은 invisible.
    레일 한 조각이 이 평면을 (length, width, 1) 스케일 + Z회전한 것.
    """
    mesh = UsdGeom.Mesh.Define(stage, path)
    pts = [(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0)]
    mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in pts]))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([4]))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray([0, 1, 2, 3]))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*color)]))
    if double_sided:
        mesh.CreateDoubleSidedAttr(True)
    # prototype 은 invisible 금지 (인스턴스가 상속 -> 사라짐).
    return mesh


def quat_yaw_rad(rad):
    """Z축(up) 기준 yaw 회전 quaternion (half). 입력 라디안."""
    return _quat_yaw_z(math.degrees(rad))


def make_basis_curves(stage, path, polylines, width=0.25,
                      color=(0.30, 0.55, 0.85), curve_type="linear"):
    """
    여러 폴리라인을 BasisCurves prim '하나'로. = THREE.TubeGeometry / fat-line.
    세그먼트 인스턴싱(수만 개) 대신 곡선 prim 1개 + 폭(width) 리본.
      polylines : [[(x,y,z), ...], ...]
      width     : 리본/튜브 지름 (world). VPS 레일 폭 0.25 대응.
    Hydra 가 점들 사이를 그려줌 (linear=직선 연결, cubic=매끈 보간).
    """
    bc = UsdGeom.BasisCurves.Define(stage, path)
    bc.CreateTypeAttr(UsdGeom.Tokens.linear if curve_type == "linear"
                      else UsdGeom.Tokens.cubic)
    counts = [len(pl) for pl in polylines]
    pts = [Gf.Vec3f(*p) for pl in polylines for p in pl]
    bc.CreateCurveVertexCountsAttr(Vt.IntArray(counts))
    bc.CreatePointsAttr(Vt.Vec3fArray(pts))
    # 폭: prim 전체 단일값 (constant)
    wattr = bc.CreateWidthsAttr(Vt.FloatArray([width]))
    bc.SetWidthsInterpolation(UsdGeom.Tokens.constant)
    bc.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*color)]))
    return bc


def _quat_align_x_to(direction):
    """단위 큐브의 +X축을 주어진 방향벡터로 회전시키는 quaternion (half)."""
    d = Gf.Vec3d(*direction).GetNormalized()
    rot = Gf.Rotation(Gf.Vec3d(1, 0, 0), d)  # +X -> d
    q = rot.GetQuaternion()
    im = q.GetImaginary()
    return Gf.Quath(q.GetReal(), im[0], im[1], im[2])


def _quat_yaw_z(deg):
    """Z축(up) 기준 yaw 회전 quaternion (half)."""
    rot = Gf.Rotation(Gf.Vec3d(0, 0, 1), deg)
    q = rot.GetQuaternion()
    im = q.GetImaginary()
    return Gf.Quath(q.GetReal(), im[0], im[1], im[2])


def add_preview_material(stage, path, diffuse=(0.8, 0.8, 0.8),
                         metallic=0.0, roughness=0.5, emissive=(0.0, 0.0, 0.0),
                         opacity=1.0):
    """
    UsdPreviewSurface 머티리얼 = THREE.MeshStandardMaterial.
    RTX 가 metallic/roughness 로 PBR 음영을 줘서 displayColor 평면색보다 입체감 생김.
    opacity<1 이면 반투명(유리/FOUP). 반환한 Material 을 bind_material 로 묶는다.
    """
    mat = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, path + "/Shader")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*diffuse))
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    if any(emissive):
        sh.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*emissive))
    if opacity < 1.0:
        sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def bind_material(prim_holder, material):
    """mesh/curve(UsdGeom prim 래퍼) 에 머티리얼 바인딩. PointInstancer 프로토에 묶으면 인스턴스 전부 상속."""
    UsdShade.MaterialBindingAPI.Apply(prim_holder.GetPrim()).Bind(material)


def add_ground_plane(stage, path, xmin, xmax, ymin, ymax, z=0.0,
                     color=(0.30, 0.31, 0.34), roughness=0.92, margin=1.1):
    """
    맵 bbox 를 덮는 공장 바닥 평면 (XY, 법선 +Z). z=0 (레일 z=3.8 아래).
    회색 콘크리트/에폭시 느낌 (metallic 0, roughness 높음).
    """
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    hx = (xmax - xmin) / 2 * margin
    hy = (ymax - ymin) / 2 * margin
    pts = [(cx - hx, cy - hy, z), (cx + hx, cy - hy, z),
           (cx + hx, cy + hy, z), (cx - hx, cy + hy, z)]
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in pts]))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([4]))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray([0, 1, 2, 3]))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateNormalsAttr(Vt.Vec3fArray([Gf.Vec3f(0, 0, 1)] * 4))
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
    mesh.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*color)]))
    mesh.CreateDoubleSidedAttr(True)
    mat = add_preview_material(stage, path + "_Mat",
                               diffuse=color, metallic=0.0, roughness=roughness)
    bind_material(mesh, mat)
    return mesh


def add_ceiling_strips(stage, path, xmin, xmax, ymin, ymax, z=5.5, spacing=4.0,
                       material=None, color=(1.0, 1.0, 1.0), strip_w=0.3, thick=0.12):
    """
    천장 형광등 줄: X축 방향 긴 발광 박스를 Y 로 spacing 간격으로 다다다 깐다.
    analytic 라이트가 아니라 emissive 지오메트리 → 그림자 계산 0, 거의 공짜.
    실제 조명은 dome 이 담당하고 이건 "형광등처럼 보이게" 하는 용도.
    """
    cx = (xmin + xmax) / 2.0
    length = (xmax - xmin) * 1.02
    n = max(int((ymax - ymin) / spacing), 1)
    for i in range(n + 1):
        y = ymin + i * spacing
        add_box(stage, f"{path}/strip_{i}", (cx, y, z), (length, strip_w, thick),
                material=material, color=color)
    return n + 1


def add_dome_light(stage, path="/World/Lights/Dome", intensity=400.0, color=(1.0, 1.0, 1.0)):
    """전방위 환경광 (IBL). HDRI 없이도 균일 앰비언트 -> 박스가 검게 안 죽음."""
    d = UsdLux.DomeLight.Define(stage, path)
    d.CreateIntensityAttr(intensity)
    d.CreateColorAttr(Gf.Vec3f(*color))
    return d


def add_distant_light(stage, path="/World/Lights/Sun", intensity=1600.0,
                      color=(1.0, 0.97, 0.92), rot_xyz=(-50.0, 0.0, 35.0)):
    """태양광(방향광). 그림자/하이라이트로 입체감. 기본 방향 -Z 를 rot 으로 비스듬히."""
    dl = UsdLux.DistantLight.Define(stage, path)
    dl.CreateIntensityAttr(intensity)
    dl.CreateColorAttr(Gf.Vec3f(*color))
    dl.CreateAngleAttr(0.2)  # 각지름 작게 -> 섀도 샘플↓(가벼움) + 하이라이트 덜 번짐
    UsdGeom.XformCommonAPI(dl).SetRotate(Gf.Vec3f(*rot_xyz))
    return dl


def make_instancer(stage, path, proto_paths, positions, orientations=None,
                   scales=None, proto_indices=None):
    """
    PointInstancer 생성 = THREE.InstancedMesh.
      proto_paths   : prototype prim 경로 리스트 (protoIndices 가 가리킴)
      positions     : [Gf.Vec3f, ...]
      orientations  : [Gf.Quath, ...] or None(=identity)
      scales        : [Gf.Vec3f, ...] or None(=1)
      proto_indices : [int, ...] or None(=전부 0)
    """
    pi = UsdGeom.PointInstancer.Define(stage, path)
    pi.CreatePrototypesRel().SetTargets([Sdf.Path(p) for p in proto_paths])
    pi.CreatePositionsAttr(Vt.Vec3fArray(positions))
    n = len(positions)
    pi.CreateProtoIndicesAttr(Vt.IntArray(proto_indices if proto_indices else [0] * n))
    if orientations:
        pi.CreateOrientationsAttr(Vt.QuathArray(orientations))
    if scales:
        pi.CreateScalesAttr(Vt.Vec3fArray(scales))
    return pi


def rails_from_polylines(polylines, width=0.2, height=0.1):
    """
    폴리라인들(점 리스트의 리스트)을 짧은 직선 세그먼트 인스턴스로 분해.
    각 세그먼트 = 단위 큐브를 (길이, width, height) 스케일 + 방향 회전 + 중점 배치.
    반환: (positions, orientations, scales)  -> make_instancer 에 그대로 투입.

    = Three.js 에서 곡선을 짧은 box 들로 근사해 InstancedMesh 로 까는 것.
    """
    positions, orientations, scales = [], [], []
    for pl in polylines:
        for a, b in zip(pl[:-1], pl[1:]):
            ax, ay, az = a
            bx, by, bz = b
            dx, dy, dz = bx - ax, by - ay, bz - az
            length = math.sqrt(dx * dx + dy * dy + dz * dz)
            if length < 1e-9:
                continue
            positions.append(Gf.Vec3f((ax + bx) / 2, (ay + by) / 2, (az + bz) / 2))
            orientations.append(_quat_align_x_to((dx, dy, dz)))
            scales.append(Gf.Vec3f(length, width, height))  # X=길이
    return positions, orientations, scales


def ports_from_list(ports, default_size=(1.0, 1.0, 0.5)):
    """
    port 리스트 -> (positions, orientations, scales).
      ports: [{pos:(x,y,z), size:(sx,sy,sz)?, yaw_deg:float?}, ...]
    """
    positions, orientations, scales = [], [], []
    for p in ports:
        positions.append(Gf.Vec3f(*p["pos"]))
        orientations.append(_quat_yaw_z(p.get("yaw_deg", 0.0)))
        scales.append(Gf.Vec3f(*p.get("size", default_size)))
    return positions, orientations, scales
