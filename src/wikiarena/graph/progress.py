from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import Iterator, TextIO


@dataclass
class ProgressReporter:
    output_stream: TextIO = sys.stderr
    enabled: bool = True
    started_at: float = field(default_factory=perf_counter)

    def log(
        self,
        message: str,
    ) -> None:
        if not self.enabled:
            return
        elapsed_seconds = perf_counter() - self.started_at
        print(
            f"[{elapsed_seconds:8.1f}s] {message}",
            file=self.output_stream,
            flush=True,
        )

    @contextmanager
    def step(
        self,
        label: str,
    ) -> Iterator[None]:
        self.log(
            f"START {label}",
        )
        step_started_at = perf_counter()
        try:
            yield
        except Exception:
            self.log(
                f"FAILED {label} after {perf_counter() - step_started_at:.1f}s",
            )
            raise
        self.log(
            f"DONE {label} in {perf_counter() - step_started_at:.1f}s",
        )
