import asyncio
from app.core.database import async_session_factory
from app.services.cost.g2b_price_sync_service import G2BPriceSyncService

async def main():
    async with async_session_factory() as db:
        service = G2BPriceSyncService(db)
        
        total_items = []
        for i in range(1, 11):
            items = await service.client.fetch_material_prices(category="건축", page=i, num_rows=999)
            if items:
                total_items.extend(items)
            else:
                break
                
        print(f"Total fetched: {len(total_items)}")
        
        sync_count = 0
        for item in total_items:
            name = item.get("prdctClsfcNoNm") or item.get("prdctClsfcNm") or item.get("itemNm") or item.get("품명") or ""
            spec = item.get("krnPrdctNm") or item.get("prdctStndrd") or item.get("stndrd") or item.get("규격") or ""
            if "레미콘" in name or "철근" in name or "방수" in name or "창호" in name:
                print(f"Matched keyword! {name} / {spec}")
                sync_count += 1
                
        print(f"Matched count: {sync_count}")

if __name__ == "__main__":
    asyncio.run(main())
