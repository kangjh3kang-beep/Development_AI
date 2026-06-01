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

import structlog

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

        try:
            f = ifcopenshell.open(path)
            settings = ifcopenshell.geom.settings()
            settings.set(settings.USE_WORLD_COORDS, True)

            all_verts: list[float] = []
            all_indices: list[int] = []
            vert_offset = 0

            it = ifcopenshell.geom.iterator(settings, f)
            if it.initialize():
                while True:
                    geom = it.get().geometry
                    verts = geom.verts  # [x0,y0,z0, x1,y1,z1, ...] (IFC: +Z up)
                    faces = geom.faces  # [i0,i1,i2, ...]
                    n_v = len(verts) // 3
                    # 축 변환: IFC(x,y,z) → glTF(x, z, -y)  (+Z up → +Y up)
                    for vi in range(n_v):
                        x = verts[vi * 3]
                        y = verts[vi * 3 + 1]
                        z = verts[vi * 3 + 2]
                        all_verts.extend([x, z, -y])
                    all_indices.extend(idx + vert_offset for idx in faces)
                    vert_offset += n_v
                    if not it.next():
                        break
        finally:
            import os

            os.unlink(path)

        if not all_verts or not all_indices:
            raise ValueError("IFC에서 추출된 mesh가 없습니다.")

        positions = np.array(all_verts, dtype=np.float32).reshape(-1, 3)
        indices = np.array(all_indices, dtype=np.uint32)

        # 모델 중심을 원점으로 이동(뷰어 카메라 정렬 용이)
        center = positions.mean(axis=0)
        positions = positions - center

        glb = self._pack_glb(positions, indices)
        logger.info(
            "IFC→glTF 변환 완료",
            verts=len(positions), tris=len(indices) // 3, glb_bytes=len(glb),
        )
        return glb

    def _pack_glb(self, positions, indices) -> bytes:
        """positions(Nx3 float32) + indices(uint32) → glTF binary(.glb)."""
        import numpy as np
        import pygltflib

        idx_bytes = indices.astype(np.uint32).tobytes()
        pos_bytes = positions.astype(np.float32).tobytes()
        # 4바이트 정렬
        idx_pad = (4 - len(idx_bytes) % 4) % 4
        blob = idx_bytes + b"\x00" * idx_pad + pos_bytes

        gltf = pygltflib.GLTF2(
            scene=0,
            scenes=[pygltflib.Scene(nodes=[0])],
            nodes=[pygltflib.Node(mesh=0)],
            meshes=[
                pygltflib.Mesh(
                    primitives=[
                        pygltflib.Primitive(
                            attributes=pygltflib.Attributes(POSITION=1),
                            indices=0,
                            mode=4,  # TRIANGLES
                        )
                    ]
                )
            ],
            accessors=[
                # 0: indices
                pygltflib.Accessor(
                    bufferView=0,
                    componentType=pygltflib.UNSIGNED_INT,
                    count=int(indices.size),
                    type=pygltflib.SCALAR,
                    max=[int(indices.max())],
                    min=[int(indices.min())],
                ),
                # 1: positions
                pygltflib.Accessor(
                    bufferView=1,
                    componentType=pygltflib.FLOAT,
                    count=int(positions.shape[0]),
                    type=pygltflib.VEC3,
                    max=positions.max(axis=0).tolist(),
                    min=positions.min(axis=0).tolist(),
                ),
            ],
            bufferViews=[
                pygltflib.BufferView(
                    buffer=0, byteOffset=0, byteLength=len(idx_bytes),
                    target=pygltflib.ELEMENT_ARRAY_BUFFER,
                ),
                pygltflib.BufferView(
                    buffer=0, byteOffset=len(idx_bytes) + idx_pad, byteLength=len(pos_bytes),
                    target=pygltflib.ARRAY_BUFFER,
                ),
            ],
            buffers=[pygltflib.Buffer(byteLength=len(blob))],
        )
        gltf.set_binary_blob(blob)
        return b"".join(gltf.save_to_bytes())


def ifc_bytes_to_glb(ifc_bytes: bytes) -> bytes:
    """편의 함수: IFC bytes → glb bytes."""
    return IfcToGltfService().convert(ifc_bytes)
