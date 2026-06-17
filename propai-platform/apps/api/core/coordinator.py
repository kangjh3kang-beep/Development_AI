import asyncio
import logging


class AgentCoordinator:
    async def request_domain_agent(self, agent_name: str, payload: dict, retry_count=0):
        try:
            # B04: Circuit Breaker & Exponential Backoff 도입
            pass # 실제 네트워크 호출 로직 대체
            return {"status": "success", "agent": agent_name}
        except Exception as e:
            if retry_count < 3:
                wait_time = 2 ** retry_count
                logging.warning(f"Agent {agent_name} fail. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
                return await self.request_domain_agent(agent_name, payload, retry_count + 1)
            raise e

    async def dispatch(self, domain: str, data: dict, **ctx) -> dict:
        """Phase 3: 도메인 → SpecialistAgent 디스패치(prior read+결정론 도구+citation_gate+원장 cite). W4.

        기존 request_domain_agent(stub)와 별개 경로(하위호환·additive). 미등록 도메인은 정직 에러.
        """
        from app.services.agents.registry import get_specialist
        try:
            agent = get_specialist(domain)
        except KeyError as e:
            return {"ok": False, "message": f"unknown domain: {domain}", "detail": str(e)}
        result = await agent.run(data, **ctx)
        return {"ok": True, "domain": domain, **result}
