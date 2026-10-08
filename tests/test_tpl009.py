"""Workflow code must log with workflow.logger."""

from tests.helpers import hits, lint


def test_print_and_logging_calls() -> None:
    diagnostics = lint(
        """\
        import logging
        from logging import error, getLogger
        from temporalio import workflow

        @workflow.defn
        class Greeting:
            @workflow.run
            async def run(self) -> None:
                print("hi")
                logging.warning("hi")
                error("hi")
                getLogger("workflow").info("hi")
                logging.getLogger("workflow").exception("hi")
        """
    )
    assert [(item.line, item.code) for item in diagnostics] == [
        (9, "TPL009"),
        (10, "TPL009"),
        (11, "TPL009"),
        (12, "TPL009"),
        (13, "TPL009"),
    ]
    assert diagnostics[0].message == "print in workflow code; use workflow.logger"
    assert diagnostics[1].message == "logging in workflow code; use workflow.logger"


def test_logger_variables_and_code_outside_the_workflow() -> None:
    assert (
        hits(
            """\
        import logging
        from temporalio import workflow

        log = logging.getLogger("app")

        def helper() -> None:
            print("outside")
            log.info("outside")

        @workflow.defn
        class Greeting:
            @workflow.run
            async def run(self) -> None:
                helper()
                log.info("replayed, but the logger is a variable")
                logging.getLogger("app")
                workflow.logger.info("ok")
        """
        )
        == []
    )


def test_noqa() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow

        @workflow.defn
        class Greeting:
            @workflow.run
            async def run(self) -> None:
                print("hi")  # noqa: TPL009
        """
        )
        == []
    )
