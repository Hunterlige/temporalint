"""Activity and child-workflow calls cannot pass both arg and a non-empty args."""

from tests.helpers import hits, lint


def test_arg_and_nonempty_args() -> None:
    diagnostics = lint(
        """\
        from temporalio import workflow

        await workflow.execute_activity(
            greet, arg=name, args=[name], start_to_close_timeout=timeout
        )
        await workflow.execute_activity_method(
            greet, name, args=(name,), start_to_close_timeout=timeout
        )
        await workflow.execute_activity_class(
            greet, None, args=[name, other], start_to_close_timeout=timeout
        )
        await workflow.start_activity(
            greet, arg=name, args="ab", start_to_close_timeout=timeout
        )
        await workflow.start_activity_method(
            greet, arg=name, args=b"ab", start_to_close_timeout=timeout
        )
        await workflow.start_activity_class(
            greet, arg=name, args=[name], start_to_close_timeout=timeout
        )
        await workflow.execute_local_activity(
            greet, arg=name, args=[name], start_to_close_timeout=timeout
        )
        await workflow.execute_local_activity_method(
            greet, arg=name, args=[name], start_to_close_timeout=timeout
        )
        await workflow.execute_local_activity_class(
            greet, arg=name, args=[name], start_to_close_timeout=timeout
        )
        await workflow.start_local_activity(
            greet, arg=name, args=[name], start_to_close_timeout=timeout
        )
        await workflow.start_local_activity_method(
            greet, arg=name, args=[name], start_to_close_timeout=timeout
        )
        await workflow.start_local_activity_class(
            greet, arg=name, args=[name], start_to_close_timeout=timeout
        )
        await workflow.execute_child_workflow(Child.run, arg=name, args=[name])
        await workflow.start_child_workflow(Child.run, name, args=(name,))
        """
    )
    assert [(item.line, item.code) for item in diagnostics] == [
        (3, "TPL002"),
        (6, "TPL002"),
        (9, "TPL002"),
        (12, "TPL002"),
        (15, "TPL002"),
        (18, "TPL002"),
        (21, "TPL002"),
        (24, "TPL002"),
        (27, "TPL002"),
        (30, "TPL002"),
        (33, "TPL002"),
        (36, "TPL002"),
        (39, "TPL002"),
        (40, "TPL002"),
    ]
    assert diagnostics[0].message == "execute_activity passes both arg and a non-empty args"
    assert diagnostics[0].col == 7


def test_empty_literal_args_and_a_single_form_are_valid() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow

        await workflow.execute_activity(
            greet, arg=name, args=[], start_to_close_timeout=timeout
        )
        await workflow.execute_activity(
            greet, name, args=(), start_to_close_timeout=timeout
        )
        await workflow.execute_activity(
            greet, arg=name, args="", start_to_close_timeout=timeout
        )
        await workflow.execute_activity(
            greet, arg=name, args=b"", start_to_close_timeout=timeout
        )
        await workflow.execute_activity(greet, arg=name, start_to_close_timeout=timeout)
        await workflow.execute_activity(greet, args=[name], start_to_close_timeout=timeout)
        await workflow.start_child_workflow(Child.run, args=[name])
        await workflow.execute_activity(
            greet, name, [name], start_to_close_timeout=timeout
        )
        await workflow.sleep(arg=name, args=[name])
        """
        )
        == []
    )


def test_non_literal_args_and_star_kwargs_are_skipped() -> None:
    assert (
        hits(
            """\
        from temporalio import workflow

        await workflow.execute_activity(
            greet, arg=name, args=values, start_to_close_timeout=timeout
        )
        await workflow.execute_activity(
            greet, arg=name, args=list(values), start_to_close_timeout=timeout
        )
        await workflow.execute_activity(
            greet, arg=name, args=[*values], start_to_close_timeout=timeout
        )
        await workflow.execute_activity(
            greet, arg=name, args=[name], start_to_close_timeout=timeout, **opts
        )
        await workflow.execute_child_workflow(Child.run, name, args=values)
        await workflow.execute_activity(
            greet, arg=name, args=1, start_to_close_timeout=timeout
        )
        await workflow.execute_activity(
            greet, arg=name, args=None, start_to_close_timeout=timeout
        )
        """
        )
        == []
    )


def test_aliased_and_direct_imports() -> None:
    assert hits(
        """\
        import temporalio.workflow as wf
        from temporalio.workflow import execute_child_workflow as run_child

        await wf.start_activity(greet, arg=name, args=[name], start_to_close_timeout=timeout)
        await run_child(Child.run, arg=name, args=[name])
        """
    ) == [
        (4, "TPL002"),
        (5, "TPL002"),
    ]


def test_unresolved_star_import_is_skipped() -> None:
    assert (
        hits(
            """\
        from temporalio.workflow import *

        execute_activity(greet, arg=name, args=[name])
        """
        )
        == []
    )


def test_noqa_suppresses_only_the_named_code() -> None:
    assert hits(
        """\
        from temporalio import workflow

        await workflow.execute_activity(  # noqa: TPL002
            greet, arg=name, args=[name], start_to_close_timeout=timeout
        )
        await workflow.execute_child_workflow(  # noqa: TPL001
            Child.run, arg=name, args=[name]
        )
        """
    ) == [(6, "TPL002")]
