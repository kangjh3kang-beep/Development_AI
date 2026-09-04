"""조달청 시설자재가격정보 동기화 서비스."""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.g2b_client import G2BClient
from app.core.config import settings

logger = logging.getLogger(__name__)

# 조달청 품명/규격 키워드 -> 내부 material_code 매핑 (휴리스틱)
G2B_MATERIAL_MAPPING = {
    "레미콘": "RC-001",
    "철근": "RC-004",
    "이형철근": "RC-004",
    "합판거푸집": "RC-008",
    "거푸집": "RC-008",
    "방수": "WP-002",
    "창호": "WW-001",
    "유리": "WW-001",
}

class G2BPriceSyncService:
    def __init__(self, db: AsyncSession):
        self.db = db
        # G2B_SERVICE_KEY가 없으면 settings.OPENAI_API_KEY처럼 None일 수 있으므로 주의
        self.client = G2BClient(service_key=settings.G2B_SERVICE_KEY or "DUMMY")

    async def sync_material_prices(self) -> dict[str, Any]:
        """조달청 API에서 단가 정보를 수집하여 DB에 UPSERT한다."""
        if not settings.G2B_SERVICE_KEY:
            return {"status": "error", "message": "G2B_SERVICE_KEY가 설정되지 않았습니다."}

        try:
            # 주요 카테고리 순회
            categories = ["건축", "토목", "기계설비", "전기통신", "종합"]
            total_fetched = 0
            sync_count = 0
            current_year = datetime.now().year
            
            end_dt = datetime.now()
            start_dt = end_dt.replace(year=end_dt.year - 2)
            start_s = start_dt.strftime("%Y%m%d%H%M")
            end_s = end_dt.strftime("%Y%m%d%H%M")

            for category in categories:
                for page in range(1, 11): # 최대 10페이지 (약 1만 건)
                    items = await self.client.fetch_material_prices(category=category, page=page, num_rows=1000)
                    if not items:
                        break # 더 이상 데이터가 없으면 다음 카테고리로 넘어감
                    
                    total_fetched += len(items)

                    for item in items:
                        name = item.get("prdctClsfcNoNm") or item.get("prdctClsfcNm") or item.get("itemNm") or item.get("품명") or ""
                        spec = item.get("krnPrdctNm") or item.get("prdctStndrd") or item.get("stndrd") or item.get("규격") or ""
                        unit = item.get("unit") or item.get("prdctUnit") or item.get("단위") or ""
                        
                        # 가격 필드 파싱 (보통 재료비 위주로 제공됨)
                        price_str = item.get("prce") or item.get("prdctUprc") or item.get("uprc") or item.get("단가") or "0"
                        try:
                            mat_price = float(str(price_str).replace(",", ""))
                        except ValueError:
                            mat_price = 0.0

                        if not name or mat_price == 0:
                            continue

                        # 매핑 시도
                        target_code = None
                        for keyword, code in G2B_MATERIAL_MAPPING.items():
                            if keyword in name or keyword in spec:
                                target_code = code
                                break

                        if target_code:
                            # UPSERT (PostgreSQL 문법)
                            await self.db.execute(
                                text("""
                                INSERT INTO material_unit_prices (
                                    material_code, spec, unit, material_price, labor_price, expense_price,
                                    price_source, price_basis_year, region, is_current, updated_at
                                ) VALUES (
                                    :code, :spec, :unit, :mat_price, 0, 0,
                                    '조달청 G2B', :year, '전국', true, CURRENT_TIMESTAMP
                                )
                                ON CONFLICT (material_code) DO UPDATE SET
                                    spec = EXCLUDED.spec,
                                    unit = EXCLUDED.unit,
                                    material_price = EXCLUDED.material_price,
                                    price_source = EXCLUDED.price_source,
                                    price_basis_year = EXCLUDED.price_basis_year,
                                    updated_at = CURRENT_TIMESTAMP
                                """)
                            , {
                                "code": target_code,
                                "spec": f"{name} {spec}".strip(),
                                "unit": unit,
                                "mat_price": mat_price,
                                "year": current_year
                            })
                            sync_count += 1

            await self.db.commit()
            return {
                "status": "success",
                "message": f"조달청 가격정보 동기화 완료. (매핑 반영 건수: {sync_count}건)",
                "total_items_fetched": total_fetched,
                "synced_count": sync_count
            }

        except Exception as e:
            logger.exception("조달청 가격 동기화 중 오류")
            return {"status": "error", "message": f"오류 발생: {str(e)}"}
        finally:
            await self.client.close()
