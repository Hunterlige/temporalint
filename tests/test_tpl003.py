"""Activity calls should bound retries."""

from tests.helpers import hits, lint

TPL003 = {"TPL003"}


def test_off_by_default() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow

        await workflow.execute_activity(greet, start_to_close_timeout=timeout)
        """
        )
        == []
    )


def test_missing_retry_policy() -> None:
    diagnostics = lint(
        """\
        from temporalio import workflow

        await workflow.execute_activity(greet, start_to_close_timeout=timeout)
        await workflow.start_activity_method(Greeter.greet, start_to_close_timeout=timeout)
        await workflow.execute_local_activity(
            greet, start_to_close_timeout=timeout, schedule_to_close_timeout=None
        )
        """,
        TPL003,
    )
    assert [(item.line, item.code) for item in diagnostics] == [
        (3, "TPL003"),
        (4, "TPL003"),
        (5, "TPL003"),
    ]
    assert diagnostics[0].message == (
        "execute_activity sets no retry_policy; activities retry without limit by default"
    )
    assert diagnostics[0].col == 7


def test_retry_policy_without_maximum_attempts() -> None:
    diagnostics = lint(
        """\
        from datetime import timedelta
        from temporalio import workflow
        from temporalio.common import RetryPolicy

        await workflow.execute_activity(greet, retry_policy=RetryPolicy())
        await workflow.execute_activity(
            greet, retry_policy=RetryPolicy(initial_interval=timedelta(seconds=1))
        )
        await workflow.execute_activity(greet, retry_policy=RetryPolicy(maximum_attempts=0))
        await workflow.execute_activity(greet, retry_policy=RetryPolicy(a, b, c, 0))
        await workflow.execute_activity(greet, retry_policy=None)
        """,
        TPL003,
    )
    assert [(item.line, item.code) for item in diagnostics] == [
        (5, "TPL003"),
        (6, "TPL003"),
        (9, "TPL003"),
        (10, "TPL003"),
        (11, "TPL003"),
    ]
    assert diagnostics[0].message == (
        "execute_activity retry_policy sets no maximum_attempts; the activity retries without limit"
    )


def test_bounded_retries_are_valid() -> None:
    assert (
        hits(
            """\
        import temporalio.common
        from temporalio import workflow
        from temporalio.common import RetryPolicy

        await workflow.execute_activity(greet, retry_policy=RetryPolicy(maximum_attempts=3))
        await workflow.execute_activity(
            greet, retry_policy=temporalio.common.RetryPolicy(maximum_attempts=1)
        )
        await workflow.execute_activity(greet, retry_policy=RetryPolicy(a, b, c, 5))
        await workflow.execute_activity(greet, schedule_to_close_timeout=timeout)
        await workflow.execute_activity(
            greet, retry_policy=RetryPolicy(), schedule_to_close_timeout=timeout
        )
        """,
            TPL003,
        )
        == []
    )


def test_unknown_policies_are_skipped() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow
        from temporalio.common import RetryPolicy

        await workflow.execute_activity(greet, retry_policy=policy)
        await workflow.execute_activity(greet, retry_policy=RetryPolicy(maximum_attempts=n))
        await workflow.execute_activity(greet, retry_policy=RetryPolicy(**opts))
        await workflow.execute_activity(greet, retry_policy=RetryPolicy(*values))
        await workflow.execute_activity(greet, retry_policy=Other())
        await workflow.execute_activity(greet, **opts)
        await workflow.execute_child_workflow(Child.run)
        """,
            TPL003,
        )
        == []
    )


def test_noqa() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow

        await workflow.execute_activity(greet)  # noqa: TPL003
        """,
            TPL003,
        )
        == []
    )
