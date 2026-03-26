"""Tenant experience service for G89."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_f_tenant import (
    TenantFinancialHealth,
    TenantSentimentScore,
    TenantTicket,
)

_POSITIVE_KEYWORDS = {"quick", "clean", "helpful", "great", "comfortable", "resolved"}
_NEGATIVE_KEYWORDS = {"delay", "broken", "leak", "noise", "cold", "hot", "unsafe", "angry"}


class TenantExperienceService:
    """Create tenant sentiment and satisfaction records."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _analyze_sentiment(feedback_text: str, satisfaction_rating: int) -> tuple[float, str, str]:
        tokens = {token.strip(".,!?").lower() for token in feedback_text.split()}
        positive_hits = len(tokens & _POSITIVE_KEYWORDS)
        negative_hits = len(tokens & _NEGATIVE_KEYWORDS)

        score = (satisfaction_rating - 3) * 0.22 + positive_hits * 0.14 - negative_hits * 0.18
        bounded_score = round(max(-1.0, min(1.0, score)), 4)

        if bounded_score >= 0.3:
            label = "positive"
            reply = (
                "Thank you for the feedback. The operations team will "
                "preserve the service level and keep you updated."
            )
        elif bounded_score <= -0.3:
            label = "negative"
            reply = "We have logged this issue for immediate follow-up and will respond with an action plan."
        else:
            label = "neutral"
            reply = "Thank you. We have recorded the feedback and will review it in the next service cycle."

        return bounded_score, label, reply

    @staticmethod
    def _calculate_health(
        *,
        promoter_count: int,
        passive_count: int,
        detractor_count: int,
        occupancy_rate: float,
        arrears_ratio: float,
    ) -> tuple[float, float, str]:
        total = promoter_count + passive_count + detractor_count
        nps = 0.0 if total == 0 else ((promoter_count - detractor_count) / total) * 100
        churn_risk_score = round(
            max(0.0, min(1.0, 0.55 - occupancy_rate * 0.35 + arrears_ratio * 0.55 - nps / 250)),
            4,
        )
        health_signal = occupancy_rate * 45 + (1 - arrears_ratio) * 30 + max(0.0, min(25.0, (nps + 100) / 8))
        if health_signal >= 80:
            health_grade = "A"
        elif health_signal >= 68:
            health_grade = "B"
        elif health_signal >= 55:
            health_grade = "C"
        elif health_signal >= 40:
            health_grade = "D"
        else:
            health_grade = "E"
        return round(nps, 2), churn_risk_score, health_grade

    async def analyze_feedback(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        unit_label: str | None,
        category: str,
        feedback_text: str,
        satisfaction_rating: int,
    ) -> tuple[TenantTicket, TenantSentimentScore]:
        sentiment_score, sentiment_label, ai_reply = self._analyze_sentiment(
            feedback_text=feedback_text,
            satisfaction_rating=satisfaction_rating,
        )

        ticket = TenantTicket(
            tenant_id=tenant_id,
            project_id=project_id,
            unit_label=unit_label,
            category=category,
            status="open" if sentiment_label == "negative" else "triaged",
            feedback_text=feedback_text,
            requested_action="operator-review" if sentiment_label == "negative" else "monitor",
        )
        self.db.add(ticket)
        await self.db.flush()

        sentiment = TenantSentimentScore(
            tenant_id=tenant_id,
            project_id=project_id,
            tenant_ticket_id=ticket.id,
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            ai_reply=ai_reply,
            metrics_json={"satisfaction_rating": satisfaction_rating},
        )
        self.db.add(sentiment)

        await self.db.commit()
        await self.db.refresh(ticket)
        await self.db.refresh(sentiment)
        return ticket, sentiment

    async def calculate_satisfaction(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        promoter_count: int,
        passive_count: int,
        detractor_count: int,
        occupancy_rate: float,
        arrears_ratio: float,
    ) -> tuple[TenantFinancialHealth, float]:
        nps, churn_risk_score, health_grade = self._calculate_health(
            promoter_count=promoter_count,
            passive_count=passive_count,
            detractor_count=detractor_count,
            occupancy_rate=occupancy_rate,
            arrears_ratio=arrears_ratio,
        )

        health = TenantFinancialHealth(
            tenant_id=tenant_id,
            project_id=project_id,
            occupancy_rate=occupancy_rate,
            arrears_ratio=arrears_ratio,
            churn_risk_score=churn_risk_score,
            health_grade=health_grade,
            metrics_json={
                "nps": nps,
                "promoter_count": promoter_count,
                "passive_count": passive_count,
                "detractor_count": detractor_count,
            },
        )
        self.db.add(health)
        await self.db.commit()
        await self.db.refresh(health)
        return health, nps
