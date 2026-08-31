from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from housing_backend.api.routes import router
from housing_backend.bootstrap import Container
from housing_backend.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = Container()
    logging.basicConfig(
        level=getattr(logging, container.settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    await container.startup()
    app.state.container = container
    try:
        yield
    finally:
        await container.shutdown()


app = FastAPI(
    title="주택청약지도 API",
    version="0.1.0",
    description=(
        "청약홈·LH 공식 데이터를 우선 수집하고 PDF 원문/정정 이력을 함께 보관하는 API. "
        "최종 청약 판단 전에는 반드시 원문 공고문을 확인해야 합니다."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)
app.include_router(router)
