from __future__ import annotations

from wikiarena.eval import build_participant_hash
from wikiarena.eval import build_race_id
from wikiarena.eval import build_ruleset_hash
from wikiarena.eval import build_run_id
from wikiarena.eval import build_taskset_hash
from wikiarena.eval import plan_benchmark_identity
from wikiarena.protocol import BenchmarkRules
from wikiarena.protocol import BenchmarkSpec
from wikiarena.protocol import DriverConfig
from wikiarena.protocol import HarnessConfig
from wikiarena.protocol import ParticipantSpec
from wikiarena.protocol import ScoringRules
from wikiarena.protocol import TaskSpec


def test_build_ruleset_hash_is_stable_for_same_inputs() -> None:
    first_hash = build_ruleset_hash(
        protocol_version="1.0.0",
        navigation_rules=BenchmarkRules(
            harness=HarnessConfig(
                harness_id="tool_v1",
            ),
        ).navigation,
        harness_config=HarnessConfig(
            harness_id="tool_v1",
        ),
        scoring_rules=ScoringRules(),
    )
    second_hash = build_ruleset_hash(
        protocol_version="1.0.0",
        navigation_rules=BenchmarkRules(
            harness=HarnessConfig(
                harness_id="tool_v1",
            ),
        ).navigation,
        harness_config=HarnessConfig(
            harness_id="tool_v1",
        ),
        scoring_rules=ScoringRules(),
    )

    assert first_hash == second_hash


def test_build_participant_hash_ignores_secret_settings_fields() -> None:
    participant_spec_a = ParticipantSpec(
        participant_id="p1",
        display_name="P1",
        driver_config=DriverConfig(
            provider="openai",
            model="gpt-x",
            settings={
                "temperature": 0,
                "api_key": "secret-a",
                "provider_settings": {
                    "auth_token": "secret-b",
                    "timeout_s": 20,
                },
            },
        ),
    )
    participant_spec_b = participant_spec_a.model_copy(
        update={
            "driver_config": participant_spec_a.driver_config.model_copy(
                update={
                    "settings": {
                        "temperature": 0,
                        "api_key": "different-secret",
                        "provider_settings": {
                            "auth_token": "different-secret",
                            "timeout_s": 20,
                        },
                    },
                },
            ),
        },
    )

    assert build_participant_hash(participant_spec_a) == build_participant_hash(
        participant_spec_b,
    )


def test_build_taskset_hash_changes_with_task_order() -> None:
    first_order_hash = build_taskset_hash(
        [
            TaskSpec(
                language="en",
                start_page_title="A",
                target_page_title="B",
            ),
            TaskSpec(
                language="en",
                start_page_title="C",
                target_page_title="D",
            ),
        ],
    )
    second_order_hash = build_taskset_hash(
        [
            TaskSpec(
                language="en",
                start_page_title="C",
                target_page_title="D",
            ),
            TaskSpec(
                language="en",
                start_page_title="A",
                target_page_title="B",
            ),
        ],
    )

    assert first_order_hash != second_order_hash


def test_plan_benchmark_identity_returns_consistent_hashes() -> None:
    benchmark_spec = BenchmarkSpec(
        benchmark_id="benchmark_v1",
        taskset_id="taskset_v1",
        rules=BenchmarkRules(
            harness=HarnessConfig(
                harness_id="tool_v1",
            ),
        ),
        participants=[
            ParticipantSpec(
                participant_id="p1",
                display_name="P1",
                driver_config=DriverConfig(
                    provider="openai",
                    model="gpt-x",
                    settings={"temperature": 0},
                ),
            ),
        ],
        tasks=[
            TaskSpec(
                language="en",
                start_page_title="Apple",
                target_page_title="Banana",
            ),
        ],
    )

    plan = plan_benchmark_identity(
        benchmark_spec,
        protocol_version="1.0.0",
    )

    assert plan.ruleset_hash
    assert plan.taskset_hash
    assert "p1" in plan.participant_hashes


def test_build_race_and_run_ids_are_deterministic() -> None:
    race_id = build_race_id(
        benchmark_id="My Benchmark",
        task_id="en__apple__banana",
        task_index=1,
        start_page_title="Apple",
        target_page_title="Banana",
    )
    run_id = build_run_id(
        race_id=race_id,
        participant_id="participant-1",
    )

    assert race_id == "race_my_benchmark_0001_en_apple__banana"
    assert run_id == "run_my_benchmark_0001_participant_1"
