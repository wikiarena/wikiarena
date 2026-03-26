from enum import Enum


class ParticipantKind(str, Enum):
    LLM = "llm"
    HUMAN = "human"
    SCRIPTED = "scripted"


class ErrorScope(str, Enum):
    STEP = "step"
    RUN = "run"
    RACE = "race"
    BENCHMARK = "benchmark"
    SETUP = "setup"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"


class StepOutcome(str, Enum):
    MOVE_COMMITTED = "move_committed"
    INVALID_LINK = "invalid_link"
    MALFORMED_TOOL_CALL = "malformed_tool_call"
    EMPTY_RESPONSE = "empty_response"
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    VALIDATION_ERROR = "validation_error"
    API_ERROR = "api_error"


class TerminalOutcome(str, Enum):
    SUCCESS = "success"
    MODEL_FAILURE = "model_failure"
    SYSTEM_FAILURE = "system_failure"
    CANCELLED = "cancelled"


class TerminationReason(str, Enum):
    TASK_COMPLETED = "task_completed"
    MAX_MOVES_EXHAUSTED = "max_moves_exhausted"
    INVALID_BUDGET_EXHAUSTED = "invalid_budget_exhausted"
    DEAD_END = "dead_end"
    MODEL_BEHAVIOR_ERROR = "model_behavior_error"
    WIKI_ERROR = "wiki_error"
    HARNESS_ERROR = "harness_error"
    INFRASTRUCTURE_ERROR = "infrastructure_error"
    MODEL_TIMEOUT = "model_timeout"
    CANCELLED = "cancelled"


class SolverMode(str, Enum):
    NONE = "none"
    LOCAL_SQLITE = "local_sqlite"
    REMOTE = "remote"


class WikiBackend(str, Enum):
    LIVE = "live"
    GRAPH = "graph"


class LinkPolicy(str, Enum):
    RAW_ORDERED = "raw_ordered"
    DEDUPE_KEEP_FIRST = "dedupe_keep_first"


class RedirectPolicy(str, Enum):
    RESOLVE_AFTER_SELECTION = "resolve_after_selection"


class ResponseContract(str, Enum):
    TOOL_CALL_ONLY = "tool_call_only"
    STRUCTURED_OUTPUT_ONLY = "structured_output_only"


class PathKind(str, Enum):
    SHORTEST = "shortest"
    SAMPLED = "sampled"
    OBSERVED = "observed"


class PathSource(str, Enum):
    LOCAL_SQLITE = "local_sqlite"
    REMOTE_SOLVER = "remote_solver"
    LIVE_SOLVER = "live_solver"
    RUN_TRACE = "run_trace"


class RunEventType(str, Enum):
    RUN_STARTED = "run_started"
    STEP_ATTEMPT_RECORDED = "step_attempt_recorded"
    MOVE_COMMITTED = "move_committed"
    RUN_TERMINATED = "run_terminated"
