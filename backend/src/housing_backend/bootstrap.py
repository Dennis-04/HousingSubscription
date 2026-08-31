from __future__ import annotations

from housing_backend.application.collection import CollectNotices
from housing_backend.config import Settings, get_settings
from housing_backend.infrastructure.db.repositories import SqlAlchemyRepository
from housing_backend.infrastructure.db.session import Database
from housing_backend.infrastructure.documents.http_fetcher import HttpDocumentFetcher
from housing_backend.infrastructure.documents.local_storage import LocalObjectStorage
from housing_backend.infrastructure.http import ResilientHttpClient
from housing_backend.infrastructure.sources.applyhome import ApplyHomeSource
from housing_backend.infrastructure.sources.lh import LhSource


class Container:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.database = Database(self.settings)
        self.repository = SqlAlchemyRepository(self.database.sessions)
        self.http = ResilientHttpClient(
            timeout_seconds=self.settings.collection_http_timeout_seconds,
            max_retries=self.settings.collection_max_retries,
        )
        self.sources = {}
        if self.settings.has_service_key:
            self.sources = {
                "applyhome": ApplyHomeSource(
                    self.http,
                    api_base_url=self.settings.applyhome_api_base_url,
                    service_key=self.settings.data_go_kr_service_key,
                    page_size=self.settings.collection_page_size,
                ),
                "lh": LhSource(
                    self.http,
                    api_base_url=self.settings.lh_api_base_url,
                    service_key=self.settings.data_go_kr_service_key,
                    page_size=self.settings.collection_page_size,
                ),
            }
        self.storage = LocalObjectStorage(self.settings.document_storage_path)
        self.document_fetcher = HttpDocumentFetcher(self.http.client, self.settings.pdf_max_bytes)
        self.collect_notices = CollectNotices(
            repository=self.repository,
            document_repository=self.repository,
            sources=self.sources,
            document_fetcher=(
                self.document_fetcher if self.settings.pdf_download_enabled else None
            ),
            storage=self.storage if self.settings.pdf_download_enabled else None,
            lookback_days=self.settings.collection_lookback_days,
            future_days=self.settings.collection_future_days,
        )

    async def startup(self) -> None:
        if self.settings.db_auto_create:
            await self.database.create_all()

    async def shutdown(self) -> None:
        await self.http.close()
        await self.database.dispose()
