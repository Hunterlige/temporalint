"""Activity calls need a start-to-close or schedule-to-close timeout."""

from tests.helpers import hits, lint


def test_missing_timeout_on_execute_and_start_variants() -> None:
    assert hits(
        """\
        from temporalio import workflow

        workflow.execute_activity(greet)
        workflow.start_activity_method(greet)
        workflow.execute_local_activity_class(greet)
        workflow.start_local_activity(greet)
        """
    ) == [
        (3, "TPL001"),
        (3, "TPL007"),
        (4, "TPL001"),
        (5, "TPL001"),
        (5, "TPL007"),
        (6, "TPL001"),
    ]


def test_either_timeout_satisfies_the_rule() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow

        await workflow.execute_activity(greet, start_to_close_timeout=timeout)
        await workflow.start_activity(greet, schedule_to_close_timeout=timeout)
        await workflow.execute_local_activity(
            greet,
            start_to_close_timeout=timeout,
            schedule_to_close_timeout=timeout,
        )
        """
        )
        == []
    )


def test_star_kwargs_are_not_flagged() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow

        await workflow.execute_activity(greet, **opts)
        """
        )
        == []
    )


def test_aliased_and_direct_imports() -> None:
    assert hits(
        """\
        import temporalio.workflow as wf
        from temporalio.workflow import execute_activity as run_activity

        await wf.start_activity_class(greet)
        await run_activity(greet)
        """
    ) == [
        (4, "TPL001"),
        (5, "TPL001"),
    ]


def test_unresolved_star_import_is_skipped() -> None:
    assert (
        hits(
            """\
        from temporalio.workflow import *

        execute_activity(greet)
        """
        )
        == []
    )


def test_noqa_suppresses_only_the_named_code() -> None:
    diagnostics = lint(
        """\
        from temporalio import workflow

        workflow.execute_activity(greet)  # noqa: TPL001
        workflow.start_activity(greet)  # noqa: TPL007
        workflow.execute_activity(greet)  # noqa
        """
    )
    assert [(item.line, item.code) for item in diagnostics] == [
        (3, "TPL007"),
        (4, "TPL001"),
    ]
    assert diagnostics[0].col == 1
