from __future__ import annotations

import asyncio

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)

from wikiarena.server.race_hub import race_stream_hub
from wikiarena.server.race_manager import RaceManager
from wikiarena.server.race_models import (
    CreateRaceRequest,
    RaceCreatedResponse,
    RaceEventsResponse,
    RaceStateResponse,
)

router = APIRouter()


def get_race_manager() -> RaceManager:
    raise RuntimeError("Race manager dependency was not initialized")


@router.post("/v1/races", response_model=RaceCreatedResponse)
async def create_race(
    create_request: CreateRaceRequest,
    race_manager: RaceManager = Depends(get_race_manager),
) -> RaceCreatedResponse:
    metadata = await race_manager.create_race(create_request)
    return RaceCreatedResponse(
        race_id=metadata.race_id,
        status=metadata.status,
        stream_url=f"/v1/races/{metadata.race_id}/stream",
        events_url=f"/v1/races/{metadata.race_id}/events",
        race_url=f"/v1/races/{metadata.race_id}",
    )


@router.get("/v1/races/{race_id}", response_model=RaceStateResponse)
async def get_race(
    race_id: str,
    race_manager: RaceManager = Depends(get_race_manager),
) -> RaceStateResponse:
    state = race_manager.get_race_state(race_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Race not found")
    return state


@router.get("/v1/races/{race_id}/events", response_model=RaceEventsResponse)
async def get_race_events(
    race_id: str,
    after_sequence: int = Query(default=0, ge=0),
    race_manager: RaceManager = Depends(get_race_manager),
) -> RaceEventsResponse:
    state = race_manager.get_race_state(race_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Race not found")
    return RaceEventsResponse(
        race_id=race_id,
        latest_stream_sequence=state.latest_stream_sequence,
        events=[
            event
            for event in state.events
            if event.stream_sequence > after_sequence
        ],
    )


@router.websocket("/v1/races/{race_id}/stream")
async def stream_race(
    websocket: WebSocket,
    race_id: str,
    after_sequence: int = Query(default=0, ge=0),
    race_manager: RaceManager = Depends(get_race_manager),
) -> None:
    state = race_manager.get_race_state(race_id)
    if state is None:
        await websocket.close(code=1008, reason="Race not found")
        return

    await race_stream_hub.connect(race_id, websocket)
    try:
        for stored_event in state.events:
            if stored_event.stream_sequence > after_sequence:
                await websocket.send_json(stored_event.model_dump(mode="json"))

        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        await race_stream_hub.disconnect(race_id, websocket)
