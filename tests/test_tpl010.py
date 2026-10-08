"""Workflow code must fail with ApplicationError, not a non-Temporal exception."""

from tests.helpers import hits, lint


def test_raise_and_assert_inside_a_workflow() -> None:
    diagnostics = lint(
        """\
        from temporalio import workflow
        from temporalio.exceptions import ApplicationError, FailureError

        @workflow.defn
        class Greeting:
            @workflow.run
            async def run(self) -> None:
                raise ValueError("bad")
                raise TypeError
                assert self is not None
                raise ApplicationError("stop")
                raise FailureError("stop")
                raise ApplicationError
        """
    )
    assert [(item.line, item.code) for item in diagnostics] == [
        (8, "TPL010"),
        (9, "TPL010"),
        (10, "TPL010"),
    ]
    assert (
        diagnostics[0].message
        == "raise ValueError in workflow code; raise ApplicationError to fail the workflow"
    )
    assert (
        diagnostics[2].message
        == "assert in workflow code raises AssertionError; "
        + "raise ApplicationError to fail the workflow"
    )


def test_imported_custom_exception() -> None:
    assert hits(
        """\
        from temporalio import workflow
        from corvic import result

        @workflow.defn
        class Greeting:
            @workflow.run
            async def run(self) -> None:
                raise result.InternalError("test")
                raise ValueError("test")
        """
    ) == [
        (8, "TPL010"),
        (9, "TPL010"),
    ]


def test_local_exception_classes() -> None:
    assert hits(
        """\
        from temporalio import workflow
        from temporalio.exceptions import ApplicationError
        from elsewhere import ExternalError

        class BadInput(ValueError):
            pass

        class Worse(BadInput):
            pass

        class Stop(ApplicationError):
            pass

        class Unknown(ExternalError):
            pass

        @workflow.defn
        class Greeting:
            @workflow.run
            async def run(self) -> None:
                raise BadInput("no")
                raise Worse("no")
                raise Stop("done")
                raise Unknown("maybe")
        """
    ) == [
        (21, "TPL010"),
        (22, "TPL010"),
    ]


def test_exception_defined_on_the_workflow() -> None:
    assert hits(
        """\
        from temporalio import workflow
        from temporalio.exceptions import ApplicationError

        @workflow.defn
        class Greeting:
            class MyError(Exception):
                pass

            class Worse(MyError):
                pass

            class Stop(ApplicationError):
                pass

            @workflow.run
            async def run(self) -> None:
                raise self.MyError("no")
                raise Greeting.Worse("no")
                raise self.Stop("done")
                raise Exception("no")

        @workflow.defn(failure_exception_types=[Exception])
        class Allowed:
            class MyError(Exception):
                pass

            @workflow.run
            async def run(self) -> None:
                raise self.MyError("allowed")
                raise Exception("allowed")
        """
    ) == [
        (17, "TPL010"),
        (18, "TPL010"),
        (20, "TPL010"),
    ]


def test_queries_validators_and_unresolved_raises_are_quiet() -> None:
    assert hits(
        """\
            import asyncio
            from temporalio import workflow
            from temporalio.exceptions import ApplicationError
            from temporalio.workflow import ContinueAsNewError, query

            @workflow.defn
            class Greeting:
                @workflow.run
                async def run(self) -> None:
                    error = ValueError("later")
                    raise error
                    raise
                    raise ApplicationError("stop", type="Stop")
                    raise ContinueAsNewError
                    raise asyncio.CancelledError
                    def nested() -> None:
                        raise RuntimeError("still workflow code")

                @query
                def status(self) -> str:
                    raise ValueError("query")
                    assert False
                    return "ok"

                @workflow.update
                async def change(self, value: str) -> str:
                    raise KeyError(value)

                @change.validator
                def check(self, value: str) -> None:
                    raise ValueError(value)

            def helper() -> None:
                raise ValueError("outside")
            """
    ) == [(17, "TPL010"), (27, "TPL010")]


def test_failure_exception_types() -> None:
    assert hits(
        """\
        from temporalio import workflow

        @workflow.defn(failure_exception_types=[ValueError, OSError])
        class Greeting:
            @workflow.run
            async def run(self) -> None:
                raise ValueError("allowed")
                raise FileNotFoundError("allowed")
                raise KeyError("no")
                assert False

        @workflow.defn(failure_exception_types=[Exception])
        class AllFailures:
            @workflow.run
            async def run(self) -> None:
                raise RuntimeError("allowed")
                assert False

        @workflow.defn(failure_exception_types=TYPES)
        class Unknown:
            @workflow.run
            async def run(self) -> None:
                raise ValueError("cannot tell")
        """
    ) == [
        (9, "TPL010"),
        (10, "TPL010"),
    ]


def test_builtin_timeout_is_not_the_temporal_timeout() -> None:
    assert hits(
        """\
        from temporalio import workflow
        from temporalio.exceptions import TimeoutError as TemporalTimeout

        @workflow.defn
        class Greeting:
            @workflow.run
            async def run(self) -> None:
                raise TimeoutError("builtin")
                raise TemporalTimeout("temporal")
        """
    ) == [(8, "TPL010")]


def test_noqa() -> None:
    assert (
        hits(
            """\
            from temporalio import workflow

            @workflow.defn
            class Greeting:
                @workflow.run
                async def run(self) -> None:
                    raise ValueError("keep")  # noqa: TPL010
                    assert False  # noqa
            """
        )
        == []
    )
