"""Deterministic contract generation service for v53 smart contracts."""

from datetime import UTC, datetime

UTC = UTC
import secrets
import uuid
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.esign_request import ESignRequest
from apps.api.database.models.phase_v53_contracts import GeneratedContractDraft
from apps.api.database.models.project import Project

_LANGUAGE_COPY: dict[str, dict[str, object]] = {
    "ko": {
        "contract_types": {
            "sale": "매매계약",
            "lease": "임대차계약",
            "construction": "공사도급계약",
            "consulting": "컨설팅계약",
        },
        "term_labels": {
            "contract_type": "계약 유형",
            "counterparty": "상대방",
            "effective_date": "효력발생일",
            "contract_amount": "계약 금액",
            "language": "문서 언어",
            "special_clauses": "특약",
        },
        "clause_titles": {
            "purpose": "계약 목적",
            "commercial": "금액 및 지급 조건",
            "responsibilities": "주요 의무 및 제출물",
            "risk": "리스크 및 변경관리",
            "signing": "전자서명 및 효력",
        },
        "summary": (
            "{project_name} 프로젝트를 대상으로 {counterparty_name}와 체결하는 "
            "{contract_type_label} 초안입니다. 프로젝트 실연동 메타데이터를 반영해 "
            "상업 조건, 수행 의무, 전자서명 흐름을 한 번에 검토하도록 구성했습니다."
        ),
        "clauses": {
            "purpose": (
                "{project_name} 프로젝트에 대해 당사자 간 역할, 적용 범위, 기본 목적을 "
                "{contract_type_label} 기준으로 정의합니다."
            ),
            "commercial": (
                "{amount_text} 기준의 상업 조건과 승인 절차를 명시하며, 프로젝트 상태에 "
                "따라 증빙과 지급 게이트를 함께 관리합니다."
            ),
            "responsibilities": (
                "{counterparty_name}는 프로젝트 deliverable과 보고 의무를 수행하고, "
                "발주 측은 검수 및 승인 일정을 제공해야 합니다."
            ),
            "risk": (
                "비용 변동, 일정 지연, 인허가 또는 운영 리스크가 발생하면 서면 합의와 "
                "변경관리 기록을 통해 수정합니다.{special_clause_suffix}"
            ),
            "signing": (
                "본 초안은 PropAI 계약 워크플로에서 전자서명 요청으로 연계될 수 있으며, "
                "{effective_date} 이후 효력이 발생하도록 설계합니다."
            ),
        },
        "unpriced_amount": "세부 금액은 별도 협의",
        "special_clause_prefix": " 추가 특약: ",
    },
    "en": {
        "contract_types": {
            "sale": "Sale agreement",
            "lease": "Lease agreement",
            "construction": "Construction agreement",
            "consulting": "Consulting agreement",
        },
        "term_labels": {
            "contract_type": "Contract type",
            "counterparty": "Counterparty",
            "effective_date": "Effective date",
            "contract_amount": "Contract amount",
            "language": "Document language",
            "special_clauses": "Special clauses",
        },
        "clause_titles": {
            "purpose": "Purpose",
            "commercial": "Commercial terms",
            "responsibilities": "Responsibilities and deliverables",
            "risk": "Risk and change control",
            "signing": "E-signature and effectiveness",
        },
        "summary": (
            "This {contract_type_label} draft covers the {project_name} project with "
            "{counterparty_name}. It packages live project context, commercial terms, "
            "delivery duties, and the e-sign handoff into one reviewable draft."
        ),
        "clauses": {
            "purpose": (
                "The parties define the scope, role split, and baseline objectives for "
                "the {project_name} project under this {contract_type_label}."
            ),
            "commercial": (
                "Commercial conditions are anchored to {amount_text}, with approval and "
                "evidence gates aligned to the current project workflow."
            ),
            "responsibilities": (
                "{counterparty_name} is responsible for the agreed deliverables and "
                "reporting cadence, while the owner must provide timely review and acceptance."
            ),
            "risk": (
                "Cost, schedule, permit, and operating-risk deviations must be logged "
                "through formal change control before the contract baseline is adjusted.{special_clause_suffix}"
            ),
            "signing": (
                "This draft can be handed off directly into the PropAI e-sign workflow, "
                "with legal effect starting on {effective_date}."
            ),
        },
        "unpriced_amount": "commercial amount to be finalized",
        "special_clause_prefix": " Additional clauses: ",
    },
    "zh-CN": {
        "contract_types": {
            "sale": "买卖合同",
            "lease": "租赁合同",
            "construction": "施工合同",
            "consulting": "咨询合同",
        },
        "term_labels": {
            "contract_type": "合同类型",
            "counterparty": "相对方",
            "effective_date": "生效日期",
            "contract_amount": "合同金额",
            "language": "文档语言",
            "special_clauses": "特别条款",
        },
        "clause_titles": {
            "purpose": "合同目的",
            "commercial": "商务条款",
            "responsibilities": "职责与交付物",
            "risk": "风险与变更控制",
            "signing": "电子签署与生效",
        },
        "summary": (
            "该{contract_type_label}草案面向 {project_name} 项目，由 {counterparty_name} "
            "参与。系统会把项目上下文、商务条件、履约责任与电子签署衔接整合到同一份草案中。"
        ),
        "clauses": {
            "purpose": (
                "双方依据 {contract_type_label} 约定 {project_name} 项目的范围、职责分工与基础目标。"
            ),
            "commercial": (
                "商务条件以 {amount_text} 为基础，并与当前项目审批和证明材料流程保持一致。"
            ),
            "responsibilities": (
                "{counterparty_name} 负责约定交付成果与汇报节奏，业主方负责按时审查与验收。"
            ),
            "risk": (
                "如发生成本、进度、许可或运营风险偏差，应先完成正式变更控制后再调整合同基线。"
                "{special_clause_suffix}"
            ),
            "signing": (
                "该草案可直接移交至 PropAI 电子签署流程，并自 {effective_date} 起生效。"
            ),
        },
        "unpriced_amount": "商务金额待最终确认",
        "special_clause_prefix": " 附加条款：",
    },
}


class ContractGeneratorService:
    """Project-scoped contract draft generator with e-sign handoff."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _normalize_language(target_language: str) -> str:
        return target_language if target_language in _LANGUAGE_COPY else "ko"

    @staticmethod
    def _normalize_contract_type(contract_type: str) -> str:
        contract_type = contract_type.strip().lower()
        return (
            contract_type
            if contract_type in {"sale", "lease", "construction", "consulting"}
            else "construction"
        )

    @staticmethod
    def _format_effective_date(value: datetime, language: str) -> str:
        value = value.astimezone(UTC)
        if language == "ko":
            return value.strftime("%Y-%m-%d")
        if language == "zh-CN":
            return value.strftime("%Y年%m月%d日")
        return value.strftime("%Y-%m-%d")

    @staticmethod
    def _format_amount(value: float | None, language: str) -> str:
        if value is None:
            return str(_LANGUAGE_COPY[language]["unpriced_amount"])
        if language == "ko":
            return f"KRW {value:,.0f}"
        return f"KRW {value:,.0f}"

    @classmethod
    def _contract_type_label(cls, contract_type: str, language: str) -> str:
        copy = _LANGUAGE_COPY[language]
        contract_types = copy["contract_types"]
        return str(contract_types[contract_type])

    @classmethod
    def _special_clause_suffix(
        cls,
        language: str,
        special_clauses: Iterable[str],
    ) -> str:
        items = [item.strip() for item in special_clauses if item.strip()]
        if not items:
            return ""
        prefix = str(_LANGUAGE_COPY[language]["special_clause_prefix"])
        return prefix + "; ".join(items)

    @classmethod
    def _build_key_terms(
        cls,
        *,
        contract_type: str,
        language: str,
        counterparty_name: str,
        effective_date: datetime,
        contract_amount_krw: float | None,
        special_clauses: list[str],
    ) -> list[dict[str, str]]:
        labels = _LANGUAGE_COPY[language]["term_labels"]
        return [
            {
                "label": str(labels["contract_type"]),
                "value": cls._contract_type_label(contract_type, language),
            },
            {
                "label": str(labels["counterparty"]),
                "value": counterparty_name,
            },
            {
                "label": str(labels["effective_date"]),
                "value": cls._format_effective_date(effective_date, language),
            },
            {
                "label": str(labels["contract_amount"]),
                "value": cls._format_amount(contract_amount_krw, language),
            },
            {
                "label": str(labels["language"]),
                "value": language,
            },
            {
                "label": str(labels["special_clauses"]),
                "value": ", ".join(item.strip() for item in special_clauses if item.strip())
                or "-",
            },
        ]

    @classmethod
    def _build_clauses(
        cls,
        *,
        project_name: str,
        contract_type: str,
        language: str,
        counterparty_name: str,
        effective_date: datetime,
        contract_amount_krw: float | None,
        special_clauses: list[str],
    ) -> list[dict[str, str]]:
        copy = _LANGUAGE_COPY[language]
        clause_titles = copy["clause_titles"]
        clause_templates = copy["clauses"]
        contract_type_label = cls._contract_type_label(contract_type, language)
        amount_text = cls._format_amount(contract_amount_krw, language)
        effective_date_text = cls._format_effective_date(effective_date, language)
        special_clause_suffix = cls._special_clause_suffix(language, special_clauses)
        clauses: list[dict[str, str]] = []

        for key in ("purpose", "commercial", "responsibilities", "risk", "signing"):
            clauses.append(
                {
                    "title": str(clause_titles[key]),
                    "body": str(clause_templates[key]).format(
                        project_name=project_name,
                        contract_type_label=contract_type_label,
                        counterparty_name=counterparty_name,
                        amount_text=amount_text,
                        effective_date=effective_date_text,
                        special_clause_suffix=special_clause_suffix,
                    ),
                }
            )

        return clauses

    @classmethod
    def _build_summary(
        cls,
        *,
        project_name: str,
        contract_type: str,
        language: str,
        counterparty_name: str,
    ) -> str:
        copy = _LANGUAGE_COPY[language]
        return str(copy["summary"]).format(
            project_name=project_name,
            counterparty_name=counterparty_name,
            contract_type_label=cls._contract_type_label(contract_type, language),
        )

    @staticmethod
    def _render_markdown(
        *,
        title: str,
        summary: str,
        key_terms: list[dict[str, str]],
        clauses: list[dict[str, str]],
    ) -> str:
        term_lines = "\n".join(
            f"- **{term['label']}**: {term['value']}" for term in key_terms
        )
        clause_lines = "\n\n".join(
            f"## {clause['title']}\n{clause['body']}" for clause in clauses
        )
        return f"# {title}\n\n{summary}\n\n## Key Terms\n{term_lines}\n\n{clause_lines}"

    async def _get_project(self, tenant_id: UUID, project_id: UUID) -> Project:
        result = await self.db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.tenant_id == tenant_id,
            )
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise ValueError("Project not found for contract workflow")
        return project

    async def generate_draft(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        contract_type: str,
        target_language: str,
        counterparty_name: str,
        effective_date: datetime,
        contract_amount_krw: float | None,
        special_clauses: list[str],
    ) -> dict[str, object]:
        project = await self._get_project(tenant_id, project_id)
        language = self._normalize_language(target_language)
        normalized_type = self._normalize_contract_type(contract_type)
        contract_type_label = self._contract_type_label(normalized_type, language)
        title = f"{project.name} {contract_type_label}"
        summary = self._build_summary(
            project_name=project.name,
            contract_type=normalized_type,
            language=language,
            counterparty_name=counterparty_name,
        )
        key_terms = self._build_key_terms(
            contract_type=normalized_type,
            language=language,
            counterparty_name=counterparty_name,
            effective_date=effective_date,
            contract_amount_krw=contract_amount_krw,
            special_clauses=special_clauses,
        )
        clauses = self._build_clauses(
            project_name=project.name,
            contract_type=normalized_type,
            language=language,
            counterparty_name=counterparty_name,
            effective_date=effective_date,
            contract_amount_krw=contract_amount_krw,
            special_clauses=special_clauses,
        )

        draft_id = uuid.uuid4()
        draft = GeneratedContractDraft(
            id=draft_id,
            tenant_id=tenant_id,
            project_id=project_id,
            contract_type=normalized_type,
            target_language=language,
            title=title,
            counterparty_name=counterparty_name,
            effective_date=effective_date.astimezone(UTC),
            contract_amount_krw=contract_amount_krw,
            summary=summary,
            key_terms_json=key_terms,
            clauses_json=clauses,
            rendered_markdown=self._render_markdown(
                title=title,
                summary=summary,
                key_terms=key_terms,
                clauses=clauses,
            ),
            document_url=f"https://propai.local/contracts/{draft_id}",
            status="draft",
            sign_status="not_requested",
        )
        self.db.add(draft)
        await self.db.commit()
        await self.db.refresh(draft)
        return self._to_response(draft, project.name)

    async def get_latest(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        contract_type: str | None = None,
    ) -> dict[str, object] | None:
        project = await self._get_project(tenant_id, project_id)
        stmt = select(GeneratedContractDraft).where(
            GeneratedContractDraft.tenant_id == tenant_id,
            GeneratedContractDraft.project_id == project_id,
        )
        if contract_type:
            stmt = stmt.where(
                GeneratedContractDraft.contract_type
                == self._normalize_contract_type(contract_type)
            )
        stmt = stmt.order_by(GeneratedContractDraft.created_at.desc())
        result = await self.db.execute(stmt)
        draft = result.scalars().first()
        if draft is None:
            return None
        return self._to_response(draft, project.name)

    async def request_esign(
        self,
        *,
        tenant_id: UUID,
        draft_id: UUID,
        signer_name: str,
        signer_email: str,
        signer_phone: str | None,
    ) -> dict[str, object]:
        result = await self.db.execute(
            select(GeneratedContractDraft).where(
                GeneratedContractDraft.id == draft_id,
                GeneratedContractDraft.tenant_id == tenant_id,
            )
        )
        draft = result.scalar_one_or_none()
        if draft is None:
            raise ValueError("Contract draft not found")

        project = await self._get_project(tenant_id, draft.project_id)
        if draft.esign_request_id is None:
            esign_request = ESignRequest(
                tenant_id=tenant_id,
                project_id=draft.project_id,
                document_name=draft.title,
                document_url=draft.document_url,
                signer_name=signer_name,
                signer_email=signer_email,
                signer_phone=signer_phone,
                provider="mock",
                status="requested",
                external_request_id=f"contract_esign_{secrets.token_hex(8)}",
                metadata_json={
                    "contract_draft_id": str(draft.id),
                    "contract_type": draft.contract_type,
                    "target_language": draft.target_language,
                },
            )
            self.db.add(esign_request)
            await self.db.flush()
            draft.esign_request_id = esign_request.id
            draft.status = "esign_requested"
            draft.sign_status = "requested"
            await self.db.commit()
            await self.db.refresh(draft)

        return self._to_response(draft, project.name)

    @staticmethod
    def _to_response(
        draft: GeneratedContractDraft,
        project_name: str,
    ) -> dict[str, object]:
        return {
            "draft_id": draft.id,
            "project_id": draft.project_id,
            "project_name": project_name,
            "contract_type": draft.contract_type,
            "target_language": draft.target_language,
            "title": draft.title,
            "counterparty_name": draft.counterparty_name,
            "effective_date": draft.effective_date,
            "contract_amount_krw": draft.contract_amount_krw,
            "document_url": draft.document_url,
            "status": draft.status,
            "sign_status": draft.sign_status,
            "key_terms": draft.key_terms_json or [],
            "clauses": draft.clauses_json or [],
            "summary": draft.summary,
            "rendered_markdown": draft.rendered_markdown,
            "esign_request_id": draft.esign_request_id,
            "created_at": draft.created_at,
        }
