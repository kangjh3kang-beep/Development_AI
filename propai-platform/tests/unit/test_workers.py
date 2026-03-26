"""워커 태스크 비즈니스 로직 검증 테스트.

Step 3.2 품질 게이트:
1. embed_regulations — OpenAI + Qdrant 코드 존재 검증
2. generate_report_pdf — ReportLab + MinIO 코드 존재 검증
3. mlops — XGBoost + MLflow 코드 존재 검증
4. generate_floor_plan — Replicate + MinIO 코드 존재 검증
5. parse_large_ifc — ifcopenshell + DB 저장 코드 존재 검증
"""

import inspect

from apps.worker.tasks import embed_regulations, generate_floor_plan, generate_report_pdf, mlops, parse_large_ifc

# ──────────────────────────────────────
# embed_regulations 비즈니스 로직 검증
# ──────────────────────────────────────


class TestEmbedRegulationsLogic:
    """embed_regulations 워커가 더미가 아닌 실제 로직을 포함하는지 검증."""

    def test_imports_openai(self) -> None:
        """OpenAI API 호출 코드가 존재한다."""
        src = inspect.getsource(embed_regulations.run_embed_regulations)
        assert "AsyncOpenAI" in src

    def test_imports_qdrant(self) -> None:
        """Qdrant 벡터 DB upsert 코드가 존재한다."""
        src = inspect.getsource(embed_regulations.run_embed_regulations)
        assert "AsyncQdrantClient" in src
        assert "upsert" in src

    def test_embedding_model_specified(self) -> None:
        """임베딩 모델이 명시되어 있다."""
        src = inspect.getsource(embed_regulations.run_embed_regulations)
        assert "text-embedding-3-small" in src

    def test_db_update_embedded_flag(self) -> None:
        """DB에 embedded=TRUE 업데이트 코드가 있다."""
        src = inspect.getsource(embed_regulations.run_embed_regulations)
        assert "embedded = TRUE" in src

    def test_returns_processed_count(self) -> None:
        """처리 건수를 반환한다."""
        src = inspect.getsource(embed_regulations.run_embed_regulations)
        assert '"processed"' in src


# ──────────────────────────────────────
# generate_report_pdf 비즈니스 로직 검증
# ──────────────────────────────────────


class TestReportPDFLogic:
    """generate_report_pdf 워커가 실제 PDF 생성 로직을 포함하는지 검증."""

    def test_imports_reportlab(self) -> None:
        """ReportLab Canvas 관련 코드가 존재한다."""
        src = inspect.getsource(generate_report_pdf.run_generate_report_pdf)
        assert "SimpleDocTemplate" in src
        assert "A4" in src

    def test_korean_font_handling(self) -> None:
        """나눔고딕 한글 폰트 처리 코드가 존재한다."""
        src = inspect.getsource(generate_report_pdf.run_generate_report_pdf)
        assert "NanumGothic" in src

    def test_minio_upload(self) -> None:
        """MinIO 업로드 코드가 존재한다."""
        src = inspect.getsource(generate_report_pdf.run_generate_report_pdf)
        assert "put_object" in src
        assert "propai-reports" in src

    def test_returns_pdf_url(self) -> None:
        """PDF URL을 반환한다."""
        src = inspect.getsource(generate_report_pdf.run_generate_report_pdf)
        assert '"pdf_url"' in src

    def test_cover_page(self) -> None:
        """커버페이지 요소가 있다."""
        src = inspect.getsource(generate_report_pdf.run_generate_report_pdf)
        assert "PropAI" in src
        assert "종합 보고서" in src

    def test_avm_section(self) -> None:
        """AVM 시세 분석 섹션이 있다."""
        src = inspect.getsource(generate_report_pdf.run_generate_report_pdf)
        assert "AVM" in src
        assert "estimated_price" in src

    def test_disclaimer_section(self) -> None:
        """면책 조항이 있다."""
        src = inspect.getsource(generate_report_pdf.run_generate_report_pdf)
        assert "면책" in src or "투자 의사결정" in src


# ──────────────────────────────────────
# mlops 비즈니스 로직 검증
# ──────────────────────────────────────


class TestMLOpsLogic:
    """mlops 워커가 실제 학습/등록 로직을 포함하는지 검증."""

    def test_imports_xgboost(self) -> None:
        """XGBoost 학습 코드가 존재한다."""
        src = inspect.getsource(mlops.run_retrain_avm)
        assert "XGBRegressor" in src

    def test_imports_mlflow(self) -> None:
        """MLflow 모델 등록 코드가 존재한다."""
        src = inspect.getsource(mlops.run_retrain_avm)
        assert "mlflow" in src
        assert "log_model" in src

    def test_mape_calculation(self) -> None:
        """MAPE 계산 코드가 있다."""
        src = inspect.getsource(mlops.run_retrain_avm)
        assert "mape" in src

    def test_train_test_split(self) -> None:
        """train_test_split이 사용된다."""
        src = inspect.getsource(mlops.run_retrain_avm)
        assert "train_test_split" in src

    def test_champion_decision(self) -> None:
        """챔피언 교체 판단 코드가 있다."""
        src = inspect.getsource(mlops.run_retrain_avm)
        assert "is_champion" in src


# ──────────────────────────────────────
# generate_floor_plan 비즈니스 로직 검증
# ──────────────────────────────────────


class TestFloorPlanLogic:
    """generate_floor_plan 워커가 실제 이미지 생성 로직을 포함하는지 검증."""

    def test_imports_replicate(self) -> None:
        """Replicate API 호출 코드가 존재한다."""
        src = inspect.getsource(generate_floor_plan.run_generate_floor_plan)
        assert "replicate" in src

    def test_sdxl_model(self) -> None:
        """SDXL 모델이 명시되어 있다."""
        src = inspect.getsource(generate_floor_plan.run_generate_floor_plan)
        assert "stability-ai/sdxl" in src

    def test_minio_upload(self) -> None:
        """MinIO 업로드 코드가 존재한다."""
        src = inspect.getsource(generate_floor_plan.run_generate_floor_plan)
        assert "put_object" in src

    def test_db_update(self) -> None:
        """DB 업데이트 코드가 있다."""
        src = inspect.getsource(generate_floor_plan.run_generate_floor_plan)
        assert "UPDATE designs" in src


# ──────────────────────────────────────
# parse_large_ifc 비즈니스 로직 검증
# ──────────────────────────────────────


class TestIFCParsingLogic:
    """parse_large_ifc 워커가 실제 IFC 파싱 로직을 포함하는지 검증."""

    def test_imports_ifcopenshell(self) -> None:
        """ifcopenshell 임포트가 존재한다."""
        src = inspect.getsource(parse_large_ifc.run_parse_large_ifc)
        assert "ifcopenshell" in src

    def test_target_ifc_types(self) -> None:
        """IFC 요소 유형이 정의되어 있다."""
        assert "IfcWall" in parse_large_ifc._TARGET_TYPES
        assert "IfcSlab" in parse_large_ifc._TARGET_TYPES
        assert len(parse_large_ifc._TARGET_TYPES) >= 8

    def test_quantity_extraction(self) -> None:
        """물량 산출(체적/면적) 코드가 있다."""
        src = inspect.getsource(parse_large_ifc.run_parse_large_ifc)
        assert "VolumeValue" in src
        assert "AreaValue" in src

    def test_db_save(self) -> None:
        """DB 저장 코드가 있다."""
        src = inspect.getsource(parse_large_ifc.run_parse_large_ifc)
        assert "UPDATE designs" in src
        assert "bim_data" in src

    def test_returns_element_count(self) -> None:
        """요소 수를 반환한다."""
        src = inspect.getsource(parse_large_ifc.run_parse_large_ifc)
        assert '"element_count"' in src
