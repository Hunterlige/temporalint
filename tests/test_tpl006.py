"""A query method must return a value."""

from tests.helpers import hits, lint

TPL006 = {"TPL006"}


def test_query_without_return() -> None:
    diagnostics = lint(
        """\
        from temporalio import workflow

        @workflow.defn
        class Greeting:
            @workflow.query
            def status(self) -> None:
                self.calls += 1

            @workflow.query(name="progress")
            async def progress(self) -> int:
                if self.done:
                    return
                return None

            @workflow.query
            def nested(self) -> str:
                def helper() -> str:
                    return "ok"

                helper()
        """,
        TPL006,
    )
    assert [(item.line, item.code) for item in diagnostics] == [
        (6, "TPL006"),
        (10, "TPL006"),
        (16, "TPL006"),
    ]
    assert diagnostics[0].message == 'query "status" returns no value'
    assert diagnostics[0].col == 5


def test_returning_queries_and_stubs_are_valid() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow
        from temporalio.workflow import query

        @workflow.defn
        class Greeting:
            @workflow.query
            def status(self) -> str:
                if self.done:
                    return "done"
                raise_if_bad()

            @query
            def interface(self) -> str: ...

            @workflow.query
            def documented(self) -> str:
                \"\"\"Implemented elsewhere.\"\"\"

            @workflow.query
            def unsupported(self) -> str:
                raise NotImplementedError

            @workflow.query
            def stream(self):
                yield self.value

            @workflow.signal
            def ping(self) -> None:
                self.calls += 1
        """,
            TPL006,
        )
        == []
    )


def test_noqa() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow

        class Greeting:
            @workflow.query
            def status(self) -> None:  # noqa: TPL006
                self.calls += 1
        """,
            TPL006,
        )
        == []
    )
