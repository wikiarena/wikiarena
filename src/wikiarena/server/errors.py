from __future__ import annotations


class GraphNotReadyError(RuntimeError):
    pass


class UnknownTitleError(LookupError):
    def __init__(
        self,
        *,
        title_role: str,
        title: str,
    ):
        self.title_role = title_role
        self.title = title
        super().__init__(
            f"unknown {title_role} title: {title}",
        )
