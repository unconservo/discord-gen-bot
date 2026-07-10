"""Async HTTP client for the OAO PHP backend.

Wraps aiohttp with:
    * Automatic API-key injection
    * Timeout handling
    * Exponential-backoff retries (bug fix #8)
    * JSON decoding that gracefully handles empty / malformed responses

All cogs should use `api_client` (the module-level singleton) and never
create ad-hoc aiohttp sessions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Union

import aiohttp

from config import (
    API_KEY,
    API_RETRY_ATTEMPTS,
    API_RETRY_BASE_DELAY,
    API_TIMEOUT_SECONDS,
)

log = logging.getLogger(__name__)

JSONType = Union[Dict[str, Any], List[Any]]


class ApiClient:
    """Reusable aiohttp-based client for the PHP backend."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = API_KEY,
        timeout_seconds: int = API_TIMEOUT_SECONDS,
        retry_attempts: int = API_RETRY_ATTEMPTS,
        retry_base_delay: float = API_RETRY_BASE_DELAY,
    ) -> None:
        self._api_key = api_key
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._retry_attempts = max(1, retry_attempts)
        self._retry_base_delay = retry_base_delay
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> JSONType:
        """Perform a single HTTP call with retries + exponential backoff.

        Returns [] on total failure so downstream views can still render
        without crashing, but each failure is logged loudly.
        """
        merged_params: Dict[str, Any] = dict(params or {})
        if self._api_key:
            merged_params["key"] = self._api_key

        last_exc: Optional[BaseException] = None

        for attempt in range(1, self._retry_attempts + 1):
            try:
                session = await self._get_session()
                async with session.request(
                    method,
                    url,
                    params=merged_params,
                    data=data,
                ) as resp:
                    text = await resp.text()

                    if not text.strip():
                        return []

                    try:
                        return json.loads(text)
                    except json.JSONDecodeError as e:
                        log.error(
                            "Invalid JSON from %s (attempt %d/%d): %s | body=%s",
                            url,
                            attempt,
                            self._retry_attempts,
                            e,
                            text[:200],
                        )
                        last_exc = e

            except asyncio.TimeoutError as e:
                log.warning(
                    "API TIMEOUT %s %s (attempt %d/%d)",
                    method,
                    url,
                    attempt,
                    self._retry_attempts,
                )
                last_exc = e
            except aiohttp.ClientError as e:
                log.warning(
                    "API ERROR %s %s (attempt %d/%d): %s",
                    method,
                    url,
                    attempt,
                    self._retry_attempts,
                    e,
                )
                last_exc = e

            # Exponential backoff before the next attempt.
            if attempt < self._retry_attempts:
                delay = self._retry_base_delay * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

        log.error(
            "API call to %s failed after %d attempts: %s",
            url,
            self._retry_attempts,
            last_exc,
        )
        return []

    # -----------------------------------------------------------------
    # Public verbs
    # -----------------------------------------------------------------
    async def get(
        self, url: str, params: Optional[Dict[str, Any]] = None
    ) -> JSONType:
        return await self._request("GET", url, params=params)

    async def post(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> JSONType:
        return await self._request("POST", url, params=params, data=data)

    async def put(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> JSONType:
        return await self._request("PUT", url, params=params, data=data)

    async def delete(
        self, url: str, params: Optional[Dict[str, Any]] = None
    ) -> JSONType:
        return await self._request("DELETE", url, params=params)


# Module-level singleton — import this everywhere.
api_client = ApiClient()
