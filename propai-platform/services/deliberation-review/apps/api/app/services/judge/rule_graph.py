"""R3 — 룰 의존 DAG(WB14). 위상정렬로 평가순서 산출. 순환 탐지 시 crash 금지 → 위원 판단 degrade(INV-17).

엣지: depends_on(전제) → 룰. 전제가 의존 룰보다 먼저 평가되도록 위상정렬(Kahn).
"""
from __future__ import annotations

from app.contracts.rule import Rule


class RuleGraph:
    def __init__(self, rules: list[Rule]) -> None:
        self.rules = {r.rule_id: r for r in rules}
        self._order, self._cycle = self._topo_sort()

    def _topo_sort(self) -> tuple[list[str], bool]:
        # 진입차수 = 전제(depends_on) 개수. 전제 → 룰 순.
        indeg = {rid: 0 for rid in self.rules}
        adj: dict[str, list[str]] = {rid: [] for rid in self.rules}
        for rid, rule in self.rules.items():
            for dep in rule.depends_on:
                if dep in self.rules:
                    adj[dep].append(rid)
                    indeg[rid] += 1

        queue = sorted([rid for rid, d in indeg.items() if d == 0])
        order: list[str] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for nxt in sorted(adj[node]):
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    queue.append(nxt)
            queue.sort()

        has_cycle = len(order) < len(self.rules)
        if has_cycle:
            # 순환 룰군은 정렬 불가 — crash 대신 나머지를 뒤에 덧붙여 비차단 반환.
            remaining = [rid for rid in self.rules if rid not in order]
            order = order + remaining
        return order, has_cycle

    def has_cycle(self) -> bool:
        return self._cycle

    def degraded_to_committee(self) -> bool:
        """순환 의존 시 해당 룰군은 '상호의존 → 위원 판단'으로 degrade."""
        return self._cycle

    def eval_order(self) -> list[str]:
        return list(self._order)

    def cyclic_rule_ids(self) -> list[str]:
        """순환에 연루된(위상정렬에서 진입차수 0에 도달 못한) 룰들."""
        if not self._cycle:
            return []
        indeg = {rid: 0 for rid in self.rules}
        for rule in self.rules.values():
            for dep in rule.depends_on:
                if dep in self.rules:
                    indeg[rule.rule_id] += 1
        # 단순화: 진입차수>0 이면서 위상정렬 전반부에 못 들어간 노드군.
        resolved: set[str] = set()
        changed = True
        while changed:
            changed = False
            for rid, rule in self.rules.items():
                if rid in resolved:
                    continue
                if all(dep in resolved or dep not in self.rules for dep in rule.depends_on):
                    resolved.add(rid)
                    changed = True
        return [rid for rid in self.rules if rid not in resolved]
