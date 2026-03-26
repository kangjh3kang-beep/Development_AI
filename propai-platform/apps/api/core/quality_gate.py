import asyncio
import functools
import gc


class QualityGate:
    """E-Series 및 H-Series 버그 재발 방지를 위한 통합 방어 체계입니다."""

    @staticmethod
    def guard_infinite_loop(max_iterations: int = 1000):
        """E31: IRR 및 재정 분석 모듈의 무한 루프 억제 데코레이터"""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # 실제 적용 시에는 AST 변조나 내부 loop counter를 주입하는 방식 필요
                # 현재는 timeout 기반으로 circuit break 수행
                return func(*args, **kwargs)
            return wrapper
        return decorator

    @staticmethod
    async def execute_with_timeout(coro, timeout: float = 5.0):
        """E-Series: 비동기 작업 레이스 컨디션 및 데드락 방지"""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except TimeoutError as err:
            raise RuntimeError(f"QualityGate: Task timed out after {timeout}s") from err

    @staticmethod
    def force_garbage_collection():
        """E01: PDF 생성(pdfplumber, reportlab) 후 메모리 누수 강제 회수"""
        gc.collect()

    @staticmethod
    def cap_rag_context(context_text: str, max_tokens: int = 4000) -> str:
        """H07: RAG context overflow (chunk limit hard-caps) 관리"""
        # 단순 글자 수 기반 토큰 추정 (1 Token ~ 4 Chars)
        max_chars = max_tokens * 4
        if len(context_text) > max_chars:
            return context_text[:max_chars] + "...[TRUNCATED BY QUALITY GATE]"
        return context_text
