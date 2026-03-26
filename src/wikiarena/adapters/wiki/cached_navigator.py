from __future__ import annotations

import asyncio

from wikiarena.core import NavigationResolution
from wikiarena.core import PageSnapshot
from wikiarena.core import WikiNavigator
from wikiarena.protocol.enums import LinkPolicy


class CachedWikiNavigator:
    """Concurrency-safe caching wrapper for wiki navigators."""

    def __init__(
        self,
        inner_navigator: WikiNavigator,
    ):
        self.inner_navigator = inner_navigator

        self._page_cache: dict[tuple[str, str, str], PageSnapshot] = {}
        self._navigation_cache: dict[tuple[str, str, str], NavigationResolution] = {}

        self._page_inflight: dict[
            tuple[str, str, str], asyncio.Future[PageSnapshot]
        ] = {}
        self._navigation_inflight: dict[
            tuple[str, str, str],
            asyncio.Future[NavigationResolution],
        ] = {}

        self._lock = asyncio.Lock()

    async def get_page_snapshot(
        self,
        language: str,
        page_title: str,
        link_policy: LinkPolicy,
    ) -> PageSnapshot:
        cache_key = (
            language,
            page_title,
            link_policy.value,
        )

        leader = False
        async with self._lock:
            cached_page_snapshot = self._page_cache.get(
                cache_key,
            )
            if cached_page_snapshot is not None:
                return cached_page_snapshot.model_copy(
                    deep=True,
                )

            inflight_request = self._page_inflight.get(
                cache_key,
            )
            if inflight_request is None:
                loop = asyncio.get_running_loop()
                inflight_request = loop.create_future()
                self._page_inflight[cache_key] = inflight_request
                leader = True

        if not leader:
            shared_result = await inflight_request
            return shared_result.model_copy(
                deep=True,
            )

        try:
            fetched_page_snapshot = await self.inner_navigator.get_page_snapshot(
                language=language,
                page_title=page_title,
                link_policy=link_policy,
            )

            async with self._lock:
                self._page_cache[cache_key] = fetched_page_snapshot.model_copy(
                    deep=True,
                )
                self._page_inflight.pop(
                    cache_key,
                    None,
                )
                inflight_request.set_result(
                    fetched_page_snapshot,
                )

            return fetched_page_snapshot.model_copy(
                deep=True,
            )
        except Exception as fetch_error:
            async with self._lock:
                self._page_inflight.pop(
                    cache_key,
                    None,
                )
                inflight_request.set_exception(
                    fetch_error,
                )
            raise

    async def resolve_navigation(
        self,
        language: str,
        from_page_title: str,
        selected_link_text: str,
    ) -> NavigationResolution:
        cache_key = (
            language,
            from_page_title,
            selected_link_text,
        )

        leader = False
        async with self._lock:
            cached_navigation_resolution = self._navigation_cache.get(
                cache_key,
            )
            if cached_navigation_resolution is not None:
                return cached_navigation_resolution.model_copy(
                    deep=True,
                )

            inflight_request = self._navigation_inflight.get(
                cache_key,
            )
            if inflight_request is None:
                loop = asyncio.get_running_loop()
                inflight_request = loop.create_future()
                self._navigation_inflight[cache_key] = inflight_request
                leader = True

        if not leader:
            shared_result = await inflight_request
            return shared_result.model_copy(
                deep=True,
            )

        try:
            fetched_navigation_resolution = (
                await self.inner_navigator.resolve_navigation(
                    language=language,
                    from_page_title=from_page_title,
                    selected_link_text=selected_link_text,
                )
            )

            async with self._lock:
                self._navigation_cache[cache_key] = (
                    fetched_navigation_resolution.model_copy(
                        deep=True,
                    )
                )
                self._navigation_inflight.pop(
                    cache_key,
                    None,
                )
                inflight_request.set_result(
                    fetched_navigation_resolution,
                )

            return fetched_navigation_resolution.model_copy(
                deep=True,
            )
        except Exception as resolve_error:
            async with self._lock:
                self._navigation_inflight.pop(
                    cache_key,
                    None,
                )
                inflight_request.set_exception(
                    resolve_error,
                )
            raise

    async def cache_stats(
        self,
    ) -> dict[str, int]:
        async with self._lock:
            return {
                "page_cache_entries": len(self._page_cache),
                "navigation_cache_entries": len(self._navigation_cache),
                "page_inflight_requests": len(self._page_inflight),
                "navigation_inflight_requests": len(self._navigation_inflight),
            }

    async def clear_cache(
        self,
    ) -> None:
        async with self._lock:
            self._page_cache.clear()
            self._navigation_cache.clear()
