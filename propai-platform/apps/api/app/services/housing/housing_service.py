"""분양/주택 관리 서비스."""


class HousingService:
    """분양 세대 생성 + 관리."""

    def create_units(self, project_id: str, type_counts: dict[str, int]) -> list[dict]:
        units = []
        seq = 1
        for unit_type, count in type_counts.items():
            for _i in range(count):
                units.append({
                    "unit_id": f"UNIT-{seq:04d}",
                    "project_id": project_id,
                    "unit_type": unit_type,
                    "status": "available",
                })
                seq += 1
        return units
