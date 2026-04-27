from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket

from wikiarena.server.race_models import StoredRaceEvent


class RaceStreamHub:
    def __init__(self) -> None:
        self._connections_by_race: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, race_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections_by_race.setdefault(race_id, set()).add(websocket)

    async def disconnect(self, race_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections_by_race.get(race_id)
            if connections is None:
                return
            connections.discard(websocket)
            if not connections:
                self._connections_by_race.pop(race_id, None)

    async def broadcast(self, race_id: str, stored_event: StoredRaceEvent) -> None:
        async with self._lock:
            connections = list(self._connections_by_race.get(race_id, set()))
        if not connections:
            return

        payload = json.dumps(stored_event.model_dump(mode="json"), ensure_ascii=False)
        failed_connections: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_text(payload)
            except Exception:
                failed_connections.append(websocket)

        if failed_connections:
            async with self._lock:
                current_connections = self._connections_by_race.get(race_id)
                if current_connections is None:
                    return
                for websocket in failed_connections:
                    current_connections.discard(websocket)
                if not current_connections:
                    self._connections_by_race.pop(race_id, None)


race_stream_hub = RaceStreamHub()
