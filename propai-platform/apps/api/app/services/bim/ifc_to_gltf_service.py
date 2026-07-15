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
from typing import TYPE_CHECKING, Any

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


def _mass_for_ir(mass: dict[str, Any]) -> dict[str, Any]:
    """매스 dict에서 '_' 접두 전이(transient) 부기 키를 제거한 사본 — BimIR 정체 해시 안정화.

    왜(★결정성 봉합): 라우터 매스에는 _resolve_mass가 붙이는 '_cache_hit'처럼 '호출 시점마다
      바뀌는' 부기 플래그(캐시 미스=False·히트=True)가 섞일 수 있다. 이 값이 design_input_hash
      (설계 정체 해시)에 들어가면 같은 설계인데 캐시 상태에 따라 해시가 갈린다(멱등·재현 위반·
      엔드포인트 간 provenance 발산). '_' 접두 키는 설계 기하가 아니라 내부 부기이므로 IR 산출 전에
      제거한다 — 실제 매스 기하 키(building_width_m 등)는 '_'로 시작하지 않아 무손실이다. 원본 dict는
      훼손하지 않는다(사본 반환).
    """
    return {k: v for k, v in mass.items() if not k.startswith("_")}


def _bimir_meta(model: BimModel) -> dict[str, Any]:
    """BimModel → 산출 메타(provenance triad 연계) 단일출처 — 라우터가 응답에 additive로 부착.

    ★provenance 일치 계약(이중 해시 발산 방지): design_input_hash는 어댑터 내부에서
      compute_input_hash(mass)로 파생되므로 기존 provenance input_hash와 '동일 값'이다.
      run_id는 make_run_id(design_input_hash)로 결정적 파생 → 같은 설계면 언제나 같은 run_id.
    ★이 dict를 두 소비 헬퍼(bimir_meta_from_mass·glb_from_mass_with_bimir)가 공유해 메타 모양이
      한 곳에서만 정의된다(발산 방지 — CLAUDE.md 전역 공용화 정책).
    """
    from app.services.cad.provenance import make_run_id

    return {
        "bimir_version": model.ir_version,
        "element_count": len(model.elements),
        "design_input_hash": model.design_input_hash,
        "run_id": make_run_id(model.design_input_hash),
    }


def bimir_meta_to_headers(meta: dict[str, Any]) -> dict[str, str]:
    """BimIR 산출 메타 → HTTP 응답 헤더(additive·라이브 검증용) 단일출처.

    glb는 바이너리라 본문에 메타를 실을 수 없으므로 헤더로 표기한다(기존 X-BIM-Source 선례와 동형).
    값은 전부 ASCII(버전 문자열·정수·hex 해시·bimir/fallback)라 latin-1 헤더에 안전하다. 폴백 경로에는
    정체 메타가 없으므로 경로 표기(X-BIMIR-Path)만 붙는다(무날조 — 없는 해시를 지어내지 않음).

    ★라우터가 아니라 서비스층에 두는 이유: 메타 모양 SSOT(_bimir_meta)와 그 헤더 사영을 한 곳에
      모아, 무거운 라우터 import 체인 없이도 순수 단위테스트가 가능하게 한다(발산 방지·테스트 용이).
    """
    headers: dict[str, str] = {"X-BIMIR-Path": "bimir" if meta.get("bimir_path") else "fallback"}
    if meta.get("bimir_version") is not None:
        headers["X-BIMIR-Version"] = str(meta["bimir_version"])
    if meta.get("element_count") is not None:
        headers["X-BIMIR-Element-Count"] = str(meta["element_count"])
    if meta.get("design_input_hash") is not None:
        headers["X-BIMIR-Input-Hash"] = str(meta["design_input_hash"])
    if meta.get("run_id") is not None:
        headers["X-BIMIR-Run-Id"] = str(meta["run_id"])
    return headers


def bimir_meta_from_mass(mass: dict[str, Any]) -> dict[str, Any]:
    """매스 dict → BimIR 산출 메타(bimir_version·element_count·design_input_hash·run_id).

    쉬운 설명: glb를 만들지 않는 JSON 응답(예: /bim/generate)이 BimIR 정체·provenance를
      additive로 표기할 수 있게 하는 순수 메타 헬퍼다(ifcopenshell 불필요 — 어댑터만 호출).
    ★결정성: 같은 매스면 같은 메타(어댑터·provenance 모두 입력 결정적 파생).
    """
    from app.services.bim.bimir_adapters import bimir_from_mass

    return _bimir_meta(bimir_from_mass(_mass_for_ir(mass)))


def glb_from_mass_with_bimir(
    mass: dict[str, Any], project_name: str = "PropAI Project"
) -> tuple[bytes, dict[str, Any]]:
    """매스 dict → (glb bytes, BimIR 메타) — WP-D 세션3 glb 산출 배선용 공용 헬퍼.

    쉬운 설명: 3D 뷰어용 .glb를 이제 'BimIR 경유'로 만들되, 실패하면 기존 직접 경로로 안전 폴백한다.

    ★배선(신규 경로): bimir_from_mass(mass) → build_gltf_from_bimir(model). BimIR가 매스 왕복으로
      '동일 IFC'를 내므로 glb 구조는 기존 경로와 동등하다(세션2 구조 동등성 게이트가 근거).
    ★무회귀 폴백(예외격리): BimIR 경로가 어떤 이유로든 실패하면 기존 직접 경로
      (build_ifc_from_mass → ifc_bytes_to_glb)로 폴백한다. 폴백도 실패하면 그 예외를 그대로
      올려 호출부(라우터)의 기존 오류 처리(HTTP 500)가 동작한다.
    ★반환 메타: 성공 시 bimir 메타 + {"bimir_path": True}, 폴백 시 {"bimir_path": False}.
      라우터는 이 메타를 응답 헤더/본문에 additive로 붙인다(기존 산출물 바이트는 불변).
    """
    from app.services.bim.bimir_adapters import bimir_from_mass
    from app.services.bim.ifc_generator_service import build_ifc_from_mass

    try:
        # ★_mass_for_ir: '_cache_hit' 등 전이 부기 키 제거 → 정체 해시 안정(무손실·geometry 불변).
        model = bimir_from_mass(_mass_for_ir(mass))
        glb = build_gltf_from_bimir(model, project_name=project_name)
        return glb, {**_bimir_meta(model), "bimir_path": True}
    except Exception as e:  # noqa: BLE001 — BimIR 경로 실패 시 기존 직접 경로로 폴백(무회귀)
        logger.warning("BimIR glb 경로 실패 — 직접 경로 폴백", error=str(e)[:150])
        # 폴백은 원본 매스 그대로(기존 직접 경로와 바이트 동일 — build_ifc는 '_' 키를 무시).
        ifc_bytes = build_ifc_from_mass(mass, project_name=project_name)
        glb = ifc_bytes_to_glb(ifc_bytes)
        return glb, {"bimir_path": False}
