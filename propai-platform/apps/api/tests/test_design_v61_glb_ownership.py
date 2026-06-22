"""MEDIUM 감사(HIGH): GET /{design_version_id}/bim/model.glb IDOR 차단.

배경: GET glb 라우트가 design_version_id(UUID)만으로 design_versions 행(저장된 건물 매스·
design_data_json: 폭/깊이/층수)을 인증·소유권 검사 없이 복원해, 누구나 타인의 UUID로 설계
데이터를 조회 가능(IDOR). 수선: _load_mass_from_design_version에 데이터층 소유권 게이트 —
행에 tenant 소유권이 분명하면 요청자 tenant와 일치할 때만 저장 매스를 복원하고, 불일치/무인증은
None(폴백 절차매스로 강등 → 타 설계 데이터 무유출). GLTFLoader(무헤더 GET) 경로 무파괴.
"""
import uuid

import pytest

from app.routers.design_v61 import _load_mass_from_design_version

TENANT_A = str(uuid.uuid4())
TENANT_B = str(uuid.uuid4())
VID = str(uuid.uuid4())
DESIGN_JSON = {"building_width_m": 30.0, "building_depth_m": 12.0,
               "num_floors": 8, "floor_height_m": 3.2}


class _User:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


class _Res:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _Sess:
    """design_versions 행을 (tenant_id, floor_count, max_height_m, design_data_json) 4-튜플로 반환."""
    def __init__(self, row):
        self._row = row

    async def execute(self, statement, params=None):  # noqa: ANN001
        return _Res(self._row)


def _row(owner_tenant):
    return (owner_tenant, 8, 25.6, DESIGN_JSON)


@pytest.mark.asyncio
async def test_owner_match_restores_design():
    mass = await _load_mass_from_design_version(VID, _Sess(_row(TENANT_A)), _User(TENANT_A))
    assert mass is not None and mass["building_width_m"] == 30.0  # 소유 일치 → 저장 매스 복원


@pytest.mark.asyncio
async def test_other_tenant_returns_none():
    mass = await _load_mass_from_design_version(VID, _Sess(_row(TENANT_B)), _User(TENANT_A))
    assert mass is None  # ★IDOR 차단 — 타 tenant 설계 미복원


@pytest.mark.asyncio
async def test_unauthenticated_returns_none():
    mass = await _load_mass_from_design_version(VID, _Sess(_row(TENANT_A)), None)
    assert mass is None  # 무인증 → 강등(폴백)


@pytest.mark.asyncio
async def test_legacy_no_owner_restores():
    mass = await _load_mass_from_design_version(VID, _Sess(_row(None)), None)
    assert mass is not None and mass["building_width_m"] == 30.0  # 무소유 레거시 → 무파괴 복원


@pytest.mark.asyncio
async def test_no_row_returns_none():
    mass = await _load_mass_from_design_version(VID, _Sess(None), _User(TENANT_A))
    assert mass is None  # 행 없음 → 기존 계약 유지
