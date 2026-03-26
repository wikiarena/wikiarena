"""Archived WikiGameSolver backend retained for migration audits only."""

from __future__ import annotations

import asyncio
import socket
import time
from pathlib import Path

from wikiarena.solver.backend import SolverCapabilities, SolverTargetSession
from wikiarena.solver.models import SolverResponse

DEFAULT_REQUEST_KEY = bytes.fromhex(
    "be66cb30239f8b62e277407404ab98f2",
)


class WikiGameSolverTargetSession:
    def __init__(
        self,
        *,
        backend: "WikiGameSolverBackend",
        target_page: str,
    ):
        self.backend = backend
        self.target_page = target_page

    async def find_shortest_path(
        self,
        start_page: str,
    ) -> SolverResponse:
        return await self.backend.find_shortest_path(
            start_page,
            self.target_page,
        )

    async def get_shortest_path_length(
        self,
        start_page: str,
    ) -> int:
        response = await self.find_shortest_path(
            start_page,
        )
        return response.path_length


class WikiGameSolverBackend:
    def __init__(
        self,
        *,
        binary_path: str | Path,
        db_path: str | Path,
        snapshot_id: str | None = None,
        request_key: bytes = DEFAULT_REQUEST_KEY,
        max_depth: int = 200,
        k_paths: int = 1,
    ):
        self.binary_path = Path(
            binary_path,
        )
        self.db_path = Path(
            db_path,
        )
        self.request_key = request_key
        self.max_depth = max_depth
        self.k_paths = k_paths

        self.capabilities = SolverCapabilities(
            backend_id="wikigamesolver",
            snapshot_id=snapshot_id,
            supports_target_sessions=False,
        )

        self._server_process: asyncio.subprocess.Process | None = None
        self._port: int | None = None
        self._startup_lock = asyncio.Lock()

    async def find_shortest_path(
        self,
        start_page: str,
        target_page: str,
    ) -> SolverResponse:
        await self._ensure_server_started()
        assert self._port is not None

        started_at = time.perf_counter()
        reader, writer = await asyncio.open_connection(
            host="127.0.0.1",
            port=self._port,
        )
        try:
            request_payload = self._encode_request(
                start_page=start_page,
                target_page=target_page,
                k_paths=self.k_paths,
            )
            writer.write(
                request_payload,
            )
            await writer.drain()

            response_bytes = await reader.readuntil(
                separator=b"\x00",
            )
        finally:
            writer.close()
            await writer.wait_closed()

        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        return self._decode_response(
            response_bytes=response_bytes[:-1],
            elapsed_ms=elapsed_ms,
        )

    async def create_target_session(
        self,
        target_page: str,
    ) -> SolverTargetSession:
        return WikiGameSolverTargetSession(
            backend=self,
            target_page=target_page,
        )

    async def shutdown(
        self,
    ) -> None:
        if self._server_process is None:
            return

        self._server_process.terminate()
        try:
            await asyncio.wait_for(
                self._server_process.wait(),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            self._server_process.kill()
            await self._server_process.wait()
        finally:
            self._server_process = None
            self._port = None

    async def _ensure_server_started(
        self,
    ) -> None:
        if self._server_process is not None and self._server_process.returncode is None:
            return

        async with self._startup_lock:
            if (
                self._server_process is not None
                and self._server_process.returncode is None
            ):
                return

            port = _reserve_free_port()
            self._port = port
            self._server_process = await asyncio.create_subprocess_exec(
                str(self.binary_path),
                "--db",
                str(self.db_path),
                "--listen",
                str(port),
                "--max-depth",
                str(self.max_depth),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            for _ in range(1200):
                if self._server_process.returncode is not None:
                    stderr_data = b""
                    if self._server_process.stderr is not None:
                        stderr_data = await self._server_process.stderr.read()
                    raise RuntimeError(
                        f"WikiGameSolver server exited early: {stderr_data.decode('utf-8', errors='replace')}",
                    )
                try:
                    reader, writer = await asyncio.open_connection(
                        host="127.0.0.1",
                        port=port,
                    )
                except OSError:
                    await asyncio.sleep(0.1)
                    continue
                writer.close()
                await writer.wait_closed()
                return

            raise TimeoutError(
                "WikiGameSolver server did not become ready in time",
            )

    def _encode_request(
        self,
        *,
        start_page: str,
        target_page: str,
        k_paths: int,
    ) -> bytes:
        start_bytes = start_page.encode("utf-8")
        target_bytes = target_page.encode("utf-8")
        payload = bytearray(self.request_key)
        payload.extend(str(len(start_bytes)).encode("ascii"))
        payload.extend(b" ")
        payload.extend(start_bytes)
        payload.extend(str(len(target_bytes)).encode("ascii"))
        payload.extend(b" ")
        payload.extend(target_bytes)
        payload.extend(b" ")
        payload.extend(str(k_paths).encode("ascii"))
        return bytes(payload)

    def _decode_response(
        self,
        *,
        response_bytes: bytes,
        elapsed_ms: float,
    ) -> SolverResponse:
        response_text = response_bytes.decode(
            "utf-8",
            errors="replace",
        ).strip()
        if response_text == "No path found":
            return SolverResponse(
                paths=[],
                path_length=-1,
                computation_time_ms=elapsed_ms,
            )

        paths = _parse_wikigame_solver_paths(
            response_text,
        )
        if not paths:
            raise ValueError(
                f"unexpected WikiGameSolver response: {response_text!r}",
            )

        return SolverResponse(
            paths=paths,
            path_length=len(paths[0]) - 1,
            computation_time_ms=elapsed_ms,
        )


def _parse_wikigame_solver_paths(
    response_text: str,
) -> list[list[str]]:
    normalized_lines = [
        line.strip() for line in response_text.splitlines() if line.strip()
    ]
    if not normalized_lines:
        return []

    paths: list[list[str]] = []
    current_path: list[str] = []

    for line in normalized_lines:
        if line.startswith("Path #"):
            if current_path:
                paths.append(
                    current_path,
                )
                current_path = []
            continue

        if line.startswith("->"):
            title_text = line[2:].strip()
        else:
            title_text = line

        current_path.append(
            _canonical_title_from_output_line(
                title_text,
            ),
        )

    if current_path:
        paths.append(
            current_path,
        )
    return paths


def _canonical_title_from_output_line(
    title_text: str,
) -> str:
    marker = "(redirects to "
    if marker in title_text and title_text.endswith(")"):
        return title_text.split(marker, 1)[1][:-1]
    return title_text


def _reserve_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])
