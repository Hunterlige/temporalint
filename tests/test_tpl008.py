"""Workflow code must not call nondeterministic stdlib functions."""

from tests.helpers import hits, lint


def test_stdlib_calls_inside_a_workflow() -> None:
    diagnostics = lint(
        """\
        import datetime
        import os
        import random
        import secrets
        import time
        import uuid
        from temporalio import workflow

        @workflow.defn
        class Greeting:
            @workflow.run
            async def run(self) -> None:
                datetime.datetime.now()
                datetime.datetime.utcnow()
                datetime.datetime.today()
                datetime.date.today()
                time.time()
                time.time_ns()
                time.monotonic()
                time.perf_counter()
                random.randint(1, 2)
                secrets.token_hex()
                os.urandom(4)
                uuid.uuid4()
                uuid.uuid1()
        """
    )
    assert [item.line for item in diagnostics] == list(range(13, 26))
    assert {item.code for item in diagnostics} == {"TPL008"}
    suggestions = {item.line: item.message for item in diagnostics}
    assert "use workflow.now()" in suggestions[13]
    assert "use workflow.random()" in suggestions[22]
    assert "use workflow.uuid4()" in suggestions[25]
    assert "datetime.datetime.now" in suggestions[13]


def test_aliased_imports_and_nested_function() -> None:
    assert hits(
        """\
        from datetime import datetime as dt
        from datetime import date
        from random import choice
        from uuid import uuid4
        from temporalio import workflow

        @workflow.defn
        class Greeting:
            @workflow.run
            async def run(self) -> None:
                def nested() -> None:
                    dt.now()
                    date.today()
                    choice([1])
                    uuid4()

                nested()
        """
    ) == [
        (12, "TPL008"),
        (13, "TPL008"),
        (14, "TPL008"),
        (15, "TPL008"),
    ]


def test_calls_outside_the_workflow_are_ignored() -> None:
    assert (
        hits(
            """\
        import random
        from datetime import datetime
        from temporalio import workflow

        def helper() -> None:
            datetime.now()
            random.random()

        @workflow.defn
        class Greeting:
            @workflow.run
            async def run(self) -> None:
                helper()
                workflow.now()
                workflow.uuid4()
                workflow.random()
        """
        )
        == []
    )


def test_deterministic_stdlib_calls_are_ignored() -> None:
    assert (
        hits(
            """\
        import time
        import uuid
        from datetime import datetime
        from temporalio import workflow

        @workflow.defn
        class Greeting:
            @workflow.run
            async def run(self) -> None:
                datetime.fromisoformat("2020-01-01")
                time.sleep(1)
                uuid.uuid5(uuid.NAMESPACE_DNS, "example")
        """
        )
        == []
    )


def test_noqa() -> None:
    assert (
        hits(
            """\
        from datetime import datetime
        from temporalio import workflow

        @workflow.defn
        class Greeting:
            @workflow.run
            async def run(self) -> None:
                datetime.now()  # noqa: TPL008
        """
        )
        == []
    )
