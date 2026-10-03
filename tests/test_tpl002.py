"""Async workflow APIs must be awaited."""

from tests.helpers import hits


def test_bare_async_workflow_calls_must_be_awaited() -> None:
    assert hits(
        """\
        from temporalio import workflow

        workflow.execute_activity_method(greet)
        workflow.execute_local_activity(greet, start_to_close_timeout=timeout)
        workflow.execute_child_workflow(Child.run)
        workflow.start_child_workflow(Child.run)
        workflow.sleep(1)
        workflow.wait_condition(lambda: ready)
        """
    ) == [
        (3, "TPL001"),
        (3, "TPL002"),
        (4, "TPL002"),
        (5, "TPL002"),
        (6, "TPL002"),
        (7, "TPL002"),
        (8, "TPL002"),
    ]


def test_awaited_calls_and_sync_start_activity_are_clean() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow

        await workflow.execute_activity(greet, start_to_close_timeout=timeout)
        await workflow.execute_child_workflow(Child.run)
        await workflow.sleep(1)
        workflow.start_activity(greet, start_to_close_timeout=timeout)
        handle = workflow.execute_activity(greet, start_to_close_timeout=timeout)
        """
        )
        == []
    )


def test_direct_import_alias() -> None:
    assert hits(
        """\
        from temporalio.workflow import sleep as pause

        pause(1)
        """
    ) == [(3, "TPL002")]


def test_noqa() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow

        workflow.sleep(1)  # noqa: TPL002
        """
        )
        == []
    )
