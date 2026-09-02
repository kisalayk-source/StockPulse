from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from urllib.parse import urljoin

import httpx
from cachetools import TTLCache

from app.config import Settings
from app.services.providers import ProviderUnavailable

logger = logging.getLogger("app.sec.client")

SEC_DATA_BASE = "https://data.sec.gov"
SEC_WWW_BASE = "https://www.sec.gov"


def rank_filing_documents(names: list[str], form_type: str, form_family: str) -> list[str]:
    family = form_family.upper()
    form_token = form_type.replace("/", "").replace(" ", "").lower()

    def score(name: str) -> int:
        lower = name.lower()
        if not lower.endswith((".xml", ".htm", ".html")):
            return -1
        if lower.endswith((".htm", ".html")) and "index" in lower:
            return -1
        points = 0
        if lower.endswith(".xml"):
            points += 5
        if family == "4" and any(token in lower for token in ("form4", "form_4", "ownership", "wk-form4", "xslf345")):
            points += 20
        if family in {"13D", "13G"} and any(token in lower for token in ("sc13", "13d", "13g", "ownership")):
            points += 20
        if family == "13F":
            if "infotable" in lower or "informationtable" in lower:
                points += 25
            if "primary" in lower:
                points += 15
        if form_token and form_token in lower:
            points += 8
        if "primary" in lower:
            points += 3
        return points

    ranked = sorted({name for name in names if score(name) >= 0}, key=score, reverse=True)
    return ranked


class SecClient:
    """Async SEC EDGAR HTTP client with rate limiting and caching."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.enabled = settings.sec_enabled
        self.user_agent = settings.sec_user_agent
        self._min_interval = 1.0 / max(settings.sec_requests_per_second, 1.0)
        self._last_request = 0.0
        self._lock = asyncio.Lock()
        self._cache: TTLCache[str, Any] = TTLCache(
            maxsize=512,
            ttl=settings.sec_cache_ttl_seconds,
        )
        headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
        self.client = client or httpx.AsyncClient(
            timeout=30.0,
            headers=headers,
            follow_redirects=True,
        )

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise ProviderUnavailable("sec", "SEC integration is disabled (SEC_ENABLED=false)")

    async def _throttle(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()

    async def _get_text(self, url: str, cache_key: str | None = None) -> str:
        self._require_enabled()
        key = cache_key or url
        if key in self._cache:
            return self._cache[key]
        await self._throttle()
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self.client.get(url)
                if response.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                text = response.text
                self._cache[key] = text
                return text
            except httpx.HTTPError as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                logger.warning(
                    "sec_request_failed",
                    extra={
                        "attempt": attempt + 1,
                        "error_type": type(exc).__name__,
                        "status_code": status,
                        "url": url,
                    },
                )
                await asyncio.sleep(0.5 * (attempt + 1))
        raise ProviderUnavailable("sec", "SEC request failed") from last_error

    async def _get_json(self, url: str, cache_key: str | None = None) -> Any:
        self._require_enabled()
        key = cache_key or url
        if key in self._cache:
            return self._cache[key]
        await self._throttle()
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self.client.get(url)
                if response.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                payload = response.json()
                self._cache[key] = payload
                return payload
            except httpx.HTTPError as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                logger.warning(
                    "sec_request_failed",
                    extra={
                        "attempt": attempt + 1,
                        "error_type": type(exc).__name__,
                        "status_code": status,
                        "url": url,
                    },
                )
                await asyncio.sleep(0.5 * (attempt + 1))
        raise ProviderUnavailable("sec", "SEC request failed") from last_error

    async def company_tickers(self) -> dict[str, Any]:
        url = f"{SEC_WWW_BASE}/files/company_tickers.json"
        return await self._get_json(url, "company_tickers")

    async def submissions(self, cik: str) -> dict[str, Any]:
        cik10 = cik.zfill(10)
        url = f"{SEC_DATA_BASE}/submissions/CIK{cik10}.json"
        return await self._get_json(url, f"submissions:{cik10}")

    async def filing_index(self, cik: str, accession: str) -> str:
        accession_no_dash = accession.replace("-", "")
        cik_int = str(int(cik))
        # Archive documents live on www.sec.gov; data.sec.gov returns 404 for /Archives/edgar/.
        url = f"{SEC_WWW_BASE}/Archives/edgar/data/{cik_int}/{accession_no_dash}/index.json"
        payload = await self._get_json(url, f"index:{accession_no_dash}")
        return payload

    async def fetch_document(self, cik: str, accession: str, filename: str) -> str:
        accession_no_dash = accession.replace("-", "")
        cik_int = str(int(cik))
        url = f"{SEC_WWW_BASE}/Archives/edgar/data/{cik_int}/{accession_no_dash}/{filename}"
        return await self._get_text(url, f"doc:{accession_no_dash}:{filename}")

    async def fetch_filing_document(self, cik: str, accession: str, form_type: str) -> str:
        documents = await self.fetch_filing_documents(cik, accession, form_type)
        return documents.get("main") or documents.get("primary") or next(iter(documents.values()))

    async def fetch_filing_documents(self, cik: str, accession: str, form_type: str) -> dict[str, str]:
        from app.sec.edgar import form_family

        index = await self.filing_index(cik, accession)
        items = index.get("directory", {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        names = [str(item.get("name", "")) for item in items if item.get("name")]
        family = form_family(form_type)
        ranked = rank_filing_documents(names, form_type, family)
        documents: dict[str, str] = {}
        for name in ranked:
            lower = name.lower()
            text = await self.fetch_document(cik, accession, name)
            if "infotable" in lower or "informationtable" in lower:
                documents.setdefault("infotable", text)
            elif "primary" in lower:
                documents.setdefault("primary", text)
            else:
                documents.setdefault("main", text)
        if not documents:
            raise ProviderUnavailable("sec", f"No parseable document for accession {accession}")
        return documents

    async def fetch_ranked_filing_documents(self, cik: str, accession: str, form_type: str) -> list[tuple[str, str]]:
        from app.sec.edgar import form_family

        index = await self.filing_index(cik, accession)
        items = index.get("directory", {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        names = [str(item.get("name", "")) for item in items if item.get("name")]
        family = form_family(form_type)
        documents: list[tuple[str, str]] = []
        for name in rank_filing_documents(names, form_type, family):
            documents.append((name, await self.fetch_document(cik, accession, name)))
        if not documents:
            raise ProviderUnavailable("sec", f"No parseable document for accession {accession}")
        return documents

    async def aclose(self) -> None:
        await self.client.aclose()
