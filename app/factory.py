from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import text

from app.config import Settings, get_settings
from app.db import Base, make_engine, make_session_factory
from app.api.receipts import router as receipts_router
from app.services.document_intelligence import DocumentIntelligenceOcr
from app.services.receipt_extractor import ReceiptExtractor
from app.services.receipt_processor import ReceiptProcessor
from app.tracer import (
    get_logger,
    instrument_app,
    instrument_engine,
    log_extra,
    setup_logging,
    setup_tracing,
    shutdown_tracing,
)

import app.models  # noqa: F401  (register models on Base.metadata)

log = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings)
    setup_tracing(settings)
    engine = make_engine(settings.database_url)
    instrument_engine(engine)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(bind=engine)
        log.info(
            "[App] starting service=%s env=%s",
            settings.otel_service_name,
            settings.environment,
            extra=log_extra(execution_step="startup", status="started"),
        )
        try:
            yield
        finally:
            log.info("[App] shutting down", extra=log_extra(execution_step="shutdown", status="stopped"))
            shutdown_tracing()

    app = FastAPI(title="mimojo-receipt-intelligence-service", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.processor = ReceiptProcessor(
        ocr=DocumentIntelligenceOcr(settings),
        extractor=ReceiptExtractor(settings),
        session_factory=session_factory,
    )
    app.include_router(receipts_router, prefix="/api/v1")
    instrument_app(app)

    @app.get("/health")
    def health(request: Request):
        session = request.app.state.session_factory()
        try:
            session.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="database unavailable") from exc
        finally:
            session.close()
        return {"status": "ok"}

    return app
