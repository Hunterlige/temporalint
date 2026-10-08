"""A workflow class needs exactly one async run method."""

from tests.helpers import hits, lint


def test_valid_workflow_class() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow

        @workflow.defn(name="greeting")
        class Greeting:
            @workflow.run
            async def run(self) -> None:
                return None
        """
        )
        == []
    )


def test_imported_decorator_names() -> None:
    assert (
        hits(
            """\
        from temporalio.workflow import defn, run

        @defn
        class Greeting:
            @run
            async def run(self) -> None:
                return None
        """
        )
        == []
    )


def test_missing_run_method() -> None:
    diagnostics = lint(
        """\
        from temporalio import workflow

        @workflow.defn
        class Greeting:
            pass
        """
    )
    assert [(item.line, item.code, item.message) for item in diagnostics] == [
        (4, "TPL005", 'workflow class "Greeting" has no @workflow.run method'),
    ]


def test_sync_run_method() -> None:
    assert hits(
        """\
        import temporalio.workflow as wf

        @wf.defn
        class Greeting:
            @wf.run
            def run(self) -> None:
                return None
        """
    ) == [(6, "TPL005")]


def test_two_run_methods() -> None:
    diagnostics = lint(
        """\
        from temporalio import workflow

        @workflow.defn
        class Greeting:
            @workflow.run
            def first(self) -> None:
                return None

            @workflow.run
            async def second(self) -> None:
                return None
        """
    )
    assert [(item.line, item.message) for item in diagnostics] == [
        (4, 'workflow class "Greeting" has 2 @workflow.run methods, want exactly one'),
        (
            6,
            '@workflow.run method "first" of workflow class "Greeting" must be async',
        ),
    ]


def test_plain_class_is_not_a_workflow() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow

        class Helper:
            @workflow.run
            def run(self) -> None:
                return None
        """
        )
        == []
    )


def test_nested_workflow_does_not_end_the_outer_scope() -> None:
    assert hits(
        """\
        from temporalio import workflow

        @workflow.defn
        class Outer:
            @workflow.run
            async def run(self) -> None:
                @workflow.defn
                class Inner:
                    pass

                print("still in the workflow")
        """
    ) == [
        (8, "TPL005"),
        (11, "TPL009"),
    ]


def test_noqa() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow

        @workflow.defn
        class Greeting:  # noqa: TPL005
            def run(self) -> None:
                return None
        """
        )
        == []
    )
