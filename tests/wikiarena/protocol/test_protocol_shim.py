from wiki_arena.protocol import TaskSpec


def test_legacy_protocol_shim_imports_vnext_task_spec() -> None:
    task_spec = TaskSpec(
        language="en",
        start_page_title="Apple",
        target_page_title="Banana",
    )
    assert task_spec.task_id == "en__apple__banana"
