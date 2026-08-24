import asyncio
import json
from app.core.database import async_session_factory
from app.services.cost.g2b_price_sync_service import G2BPriceSyncService
from app.core.config import settings

async def main():
    async with async_session_factory() as db:
        service = G2BPriceSyncService(db)
        result = await service.sync_material_prices()
        print("Result:", result)

if __name__ == "__main__":
    asyncio.run(main())
