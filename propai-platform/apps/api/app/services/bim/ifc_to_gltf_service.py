"""IFC → glTF(.glb) 변환 서비스 (v62 BIM).

ifcopenshell.geom으로 IFC 모델을 mesh로 tessellate한 뒤 pygltflib로 단일 binary
glTF(.glb)를 생성한다. 프론트(@react-three/fiber useGLTF)가 직접 로드 가능.

핵심 원칙:
- 모든 shape를 하나의 mesh primitive로 병합(단순·경량). 좌표는 world coords.
- glTF는 +Y up·우수좌표계. IFC는 +Z up이므로 (x,y,z)→(x, z, -y)로 축 변환.
- numpy만 사용(이미 설치). 외부 바이너리 불필요.
"""

from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:  # 타입 힌트 전용 — 런타임 import 회피(무거운 체인 차단)
    from app.services.bim.bimir_schema import BimModel

logger = structlog.get_logger()


class IfcToGltfService:
    """IFC bytes를 glTF binary(.glb) bytes로 변환한다."""

    def convert(self, ifc_bytes: bytes) -> bytes:
        """IFC SPF bytes → .glb bytes.

        Returns:
            glTF 2.0 binary(.glb) bytes. mesh가 비면 ValueError.
        """
        import ifcopenshell
        import ifcopenshell.geom
        import numpy as np

        # ifcopenshell은 파일 경로 기반 — 임시파일 경유
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False, mode="wb") as tf:
            tf.write(ifc_bytes)
            path = tf.name

        # IFC 요소 타입 → 그룹(색상 구분용). 그룹별 verts/indices 누적.
        groups: dict[str, dict] = {}

        try:
            f = ifcopenshell.open(path)
            settings = ifcopenshell.geom.settings()
            settings.set(settings.USE_WORLD_COORDS, True)

            it = ifcopenshell.geom.iterator(settings, f)
            if it.initialize():
                while True:
                    shape = it.get()
                    geom = shape.geometry
                    # 요소 타입 분류(prefix로 그룹핑)
                    try:
                        ifc_type = f.by_id(shape.id).is_a()
                    except Exception:  # noqa: BLE001
                        ifc_type = "IfcBuildingElement"
                    grp = self._group_of(ifc_type)
                    g = groups.setdefault(grp, {"verts": [], "indices": [], "offset": 0})

                    verts = geom.verts
                    faces = geom.faces
                    n_v = len(verts) // 3
                    # 축 변환: IFC(x,y,z) → glTF(x, z, -y)  (+Z up → +Y up)
                    for vi in range(n_v):
                        g["verts"].extend([verts[vi * 3], verts[vi * 3 + 2], -verts[vi * 3 + 1]])
                    g["indices"].extend(idx + g["offset"] for idx in faces)
                    g["offset"] += n_v
                    if not it.next():
                        break
        finally:
            import os

            os.unlink(path)

        if not groups:
            raise ValueError("IFC에서 추출된 mesh가 없습니다.")

        # 전체 중심 계산(모든 그룹 공통 이동 — 상대 위치 보존)
        all_pos = np.concatenate(
            [np.array(g["verts"], dtype=np.float32).reshape(-1, 3) for g in groups.values()]
        )
        center = all_pos.mean(axis=0)

        prims = []
        total_v = total_t = 0
        for name, g in groups.items():
            pos = np.array(g["verts"], dtype=np.float32).reshape(-1, 3) - center
            idx = np.array(g["indices"], dtype=np.uint32)
            prims.append((name, pos, idx))
            total_v += len(pos)
            total_t += len(idx) // 3

        glb = self._pack_glb_multi(prims)
        logger.info(
            "IFC→glTF 변환 완료",
            groups=list(groups.keys()), verts=total_v, tris=total_t, glb_bytes=len(glb),
        )
        return glb

    @staticmethod
    def _group_of(ifc_type: str) -> str:
        """IFC 타입을 색상 그룹으로 매핑."""
        t = ifc_type.lower()
        if "stair" in t:
            return "stair"
        if "door" in t:
            return "door"
        if "window" in t:
            return "window"
        if "wallstandardcase" in t:  # 세대 분할 내벽
            return "partition"
        if "wall" in t:
            return "wall"
        if "column" in t or "space" in t:  # 코어(IfcColumn)
            return "core"
        if "slab" in t:
            return "slab"
        return "other"

    # 요소 그룹별 색상(RGBA, 0~1) — 프론트 색 구분
    _GROUP_COLORS = {
        "wall": [0.78, 0.78, 0.80, 1.0],       # 회색(외벽)
        "partition": [0.88, 0.84, 0.74, 1.0],  # 베이지(세대 분할 내벽)
        "slab": [0.55, 0.58, 0.62, 1.0],       # 진회색(슬래브)
        "core": [0.95, 0.62, 0.20, 0.95],      # 주황(코어벽)
        "stair": [0.85, 0.85, 0.88, 1.0],      # 밝은회색(계단참)
        "window": [0.40, 0.70, 0.95, 0.55],    # 반투명 청색(창호)
        "door": [0.45, 0.30, 0.18, 1.0],       # 갈색(현관문)
        "other": [0.60, 0.65, 0.70, 1.0],
    }

    def _pack_glb_multi(self, prims: list) -> bytes:
        """[(group_name, positions Nx3, indices)] → 그룹별 색상 머티리얼 glTF(.glb)."""
        import numpy as np
        import pygltflib

        blob = b""
        buffer_views = []
        accessors = []
        materials = []
        primitives = []

        def _append(data: bytes) -> tuple[int, int]:
            nonlocal blob
            offset = len(blob)
            pad = (4 - len(data) % 4) % 4
            blob += data + b"\x00" * pad
            return offset, len(data)

        for name, pos, idx in prims:
            if len(pos) == 0 or len(idx) == 0:
                continue
            # indices
            idx_off, idx_len = _append(idx.astype(np.uint32).tobytes())
            bv_idx = len(buffer_views)
            buffer_views.append(pygltflib.BufferView(
                buffer=0, byteOffset=idx_off, byteLength=idx_len,
                target=pygltflib.ELEMENT_ARRAY_BUFFER,
            ))
            acc_idx = len(accessors)
            accessors.append(pygltflib.Accessor(
                bufferView=bv_idx, componentType=pygltflib.UNSIGNED_INT,
                count=int(idx.size), type=pygltflib.SCALAR,
                max=[int(idx.max())], min=[int(idx.min())],
            ))
            # positions
            pos_off, pos_len = _append(pos.astype(np.float32).tobytes())
            bv_pos = len(buffer_views)
            buffer_views.append(pygltflib.BufferView(
                buffer=0, byteOffset=pos_off, byteLength=pos_len,
                target=pygltflib.ARRAY_BUFFER,
            ))
            acc_pos = len(accessors)
            accessors.append(pygltflib.Accessor(
                bufferView=bv_pos, componentType=pygltflib.FLOAT,
                count=int(pos.shape[0]), type=pygltflib.VEC3,
                max=pos.max(axis=0).tolist(), min=pos.min(axis=0).tolist(),
            ))
            # material(그룹 색상)
            color = self._GROUP_COLORS.get(name, self._GROUP_COLORS["other"])
            mat_idx = len(materials)
            materials.append(pygltflib.Material(
                name=name,
                pbrMetallicRoughness=pygltflib.PbrMetallicRoughness(
                    baseColorFactor=color, metallicFactor=0.1, roughnessFactor=0.7,
                ),
                alphaMode="BLEND" if color[3] < 1.0 else "OPAQUE",
                doubleSided=True,
            ))
            primitives.append(pygltflib.Primitive(
                attributes=pygltflib.Attributes(POSITION=acc_pos),
                indices=acc_idx, material=mat_idx, mode=4,
            ))

        gltf = pygltflib.GLTF2(
            scene=0,
            scenes=[pygltflib.Scene(nodes=[0])],
            nodes=[pygltflib.Node(mesh=0)],
            meshes=[pygltflib.Mesh(primitives=primitives)],
            materials=materials,
            accessors=accessors,
            bufferViews=buffer_views,
            buffers=[pygltflib.Buffer(byteLength=len(blob))],
        )
        gltf.set_binary_blob(blob)
        return b"".join(gltf.save_to_bytes())


def ifc_bytes_to_glb(ifc_bytes: bytes) -> bytes:
    """편의 함수: IFC bytes → glb bytes."""
    return IfcToGltfService().convert(ifc_bytes)


def build_gltf_from_bimir(model: BimModel, project_name: str = "PropAI Project") -> bytes:
    """BimIR(propai.bimir/1.0) → glTF(.glb) (WP-D 세션2 소비처 전환).

    쉬운 설명: 3D 뷰어가 쓰는 .glb를 이제 BimIR 하나만 보고 만들 수 있게 하는 '추가' 경로다.

    ★무회귀: 기존 ifc_bytes_to_glb(IFC bytes 직접 경로)는 그대로 둔다. 이 함수는 '추가' 경로로,
      BimIR → IFC(build_ifc_from_bimir) → glb(ifc_bytes_to_glb) 로 이어 붙인다. 기존 소비처는 무변경.
    ★구조 동등성: build_ifc_from_bimir가 매스 왕복으로 '동일 IFC'를 내므로(요소·기하 동일), 이 glb 경로는
      기존 매스 경로(ifc_bytes_to_glb(build_ifc_from_mass(mass)))와 '동일 mesh 그룹·정점·삼각형'을 낸다.
      (IFC의 GlobalId는 매 호출 랜덤이라 IFC 바이트 동일은 불가하지만, glb 지오메트리에는 GlobalId가
       실리지 않아 mesh 구조는 동등하다.)
    """
    # ★선행조건: build_ifc_from_bimir와 동일하게 매스 기원 IR 전용 — cad/ingest 기원 IR을 넣으면
    #   매스 키가 없어 10×10 기본값으로 무음 퇴화하므로 glb 경로에서도 명시적으로 거부한다(정직 실패).
    if model.source_kind != "mass_geometry":
        raise ValueError(
            f"build_gltf_from_bimir는 mass_geometry 기원 IR 전용입니다(입력={model.source_kind!r}) — "
            "cad/ingest 기원 IR의 glb 산출 전환은 WP-D 후속 세션 범위"
        )
    from app.services.bim.ifc_generator_service import build_ifc_from_bimir

    ifc_bytes = build_ifc_from_bimir(model, project_name=project_name)
    return ifc_bytes_to_glb(ifc_bytes)
