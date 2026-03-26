from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from wikiarena.server.app import create_app
from wikiarena.server.errors import GraphNotReadyError, UnknownTitleError
from wikiarena.server.models import MetaResponse, SolveResponse


@dataclass
class StubRuntime:
    health_status: str = "ok"
    meta_response: MetaResponse | None = None
    solve_response: SolveResponse | None = None
    solve_exception: Exception | None = None
    started: bool = False
    stopped: bool = False

    async def startup(
        self,
    ) -> None:
        self.started = True

    async def shutdown(
        self,
    ) -> None:
        self.stopped = True

    def is_ready(
        self,
    ) -> bool:
        return self.health_status == "ok"

    def get_health_status(
        self,
    ) -> str:
        return self.health_status

    def get_meta(
        self,
    ) -> MetaResponse:
        if self.meta_response is None:
            raise GraphNotReadyError(
                "graph is not ready",
            )
        return self.meta_response

    async def solve(
        self,
        *,
        start_title: str,
        target_title: str,
    ) -> SolveResponse:
        del start_title
        del target_title
        if self.solve_exception is not None:
            raise self.solve_exception
        assert self.solve_response is not None
        return self.solve_response


def test_health_returns_ok_when_runtime_is_ready() -> None:
    runtime = StubRuntime(
        health_status="ok",
    )

    with TestClient(
        create_app(
            runtime=runtime,
        ),
    ) as client:
        response = client.get(
            "/health",
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }
    assert runtime.started is True
    assert runtime.stopped is True


def test_health_returns_503_when_runtime_is_not_ready() -> None:
    runtime = StubRuntime(
        health_status="starting",
    )

    with TestClient(
        create_app(
            runtime=runtime,
        ),
    ) as client:
        response = client.get(
            "/health",
        )

    assert response.status_code == 503
    assert response.json() == {
        "status": "starting",
    }


def test_meta_returns_loaded_graph_metadata() -> None:
    runtime = StubRuntime(
        meta_response=MetaResponse(
            service_version="0.1.0",
            snapshot_id="enwiki-20260301",
            dump_date="20260301",
            node_count=7_146_840,
            edge_count=695_099_364,
        ),
    )

    with TestClient(
        create_app(
            runtime=runtime,
        ),
    ) as client:
        response = client.get(
            "/v1/meta",
        )

    assert response.status_code == 200
    assert response.json() == {
        "service_version": "0.1.0",
        "snapshot_id": "enwiki-20260301",
        "dump_date": "20260301",
        "node_count": 7146840,
        "edge_count": 695099364,
    }


def test_solve_returns_paths_for_successful_query() -> None:
    runtime = StubRuntime(
        solve_response=SolveResponse(
            snapshot_id="enwiki-20260301",
            start_title="Apple",
            target_title="Banana",
            path_length=2,
            paths=[["Apple", "Fruit", "Banana"]],
            solve_ms=8.7,
        ),
    )

    with TestClient(
        create_app(
            runtime=runtime,
        ),
    ) as client:
        response = client.post(
            "/v1/solve",
            json={
                "start_title": "Apple",
                "target_title": "Banana",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "snapshot_id": "enwiki-20260301",
        "start_title": "Apple",
        "target_title": "Banana",
        "path_length": 2,
        "paths": [["Apple", "Fruit", "Banana"]],
        "solve_ms": 8.7,
    }


def test_solve_returns_empty_paths_when_no_path_exists() -> None:
    runtime = StubRuntime(
        solve_response=SolveResponse(
            snapshot_id="enwiki-20260301",
            start_title="Page A",
            target_title="Page B",
            path_length=None,
            paths=[],
            solve_ms=4.1,
        ),
    )

    with TestClient(
        create_app(
            runtime=runtime,
        ),
    ) as client:
        response = client.post(
            "/v1/solve",
            json={
                "start_title": "Page A",
                "target_title": "Page B",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "snapshot_id": "enwiki-20260301",
        "start_title": "Page A",
        "target_title": "Page B",
        "path_length": None,
        "paths": [],
        "solve_ms": 4.1,
    }


def test_solve_returns_404_for_unknown_start_title() -> None:
    runtime = StubRuntime(
        solve_exception=UnknownTitleError(
            title_role="start",
            title="Not A Page",
        ),
    )

    with TestClient(
        create_app(
            runtime=runtime,
        ),
    ) as client:
        response = client.post(
            "/v1/solve",
            json={
                "start_title": "Not A Page",
                "target_title": "Banana",
            },
        )

    assert response.status_code == 404
    assert response.json() == {
        "code": "start_title_not_found",
        "message": "Start title was not found in the loaded graph snapshot.",
    }


def test_meta_returns_503_when_graph_is_not_ready() -> None:
    runtime = StubRuntime(
        health_status="starting",
        meta_response=None,
    )

    with TestClient(
        create_app(
            runtime=runtime,
        ),
    ) as client:
        response = client.get(
            "/v1/meta",
        )

    assert response.status_code == 503
    assert response.json() == {
        "code": "graph_not_ready",
        "message": "Graph is not ready.",
    }
