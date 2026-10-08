"""An activity started with heartbeat_timeout must heartbeat."""

from tests.helpers import hits, lint

TPL004 = {"TPL004"}


def test_activity_that_never_heartbeats() -> None:
    diagnostics = lint(
        """\
        import asyncio
        from temporalio import activity, workflow

        @activity.defn
        async def compute(n: int) -> int:
            await asyncio.sleep(60)
            return len(str(n))

        class Activities:
            @activity.defn(name="process")
            async def process(self) -> None:
                self.prepare()

            def prepare(self) -> None:
                self.client.send()

        @workflow.defn
        class Flow:
            @workflow.run
            async def run(self) -> None:
                await workflow.execute_activity(
                    compute, 1, start_to_close_timeout=t, heartbeat_timeout=t
                )
                await workflow.start_activity_method(
                    Activities.process, start_to_close_timeout=t, heartbeat_timeout=t
                )
        """
    )
    assert [(item.line, item.code) for item in diagnostics] == [
        (21, "TPL004"),
        (24, "TPL004"),
    ]
    assert diagnostics[0].message == (
        'execute_activity sets heartbeat_timeout but activity "compute" never calls activity.heartbeat'
    )
    assert diagnostics[1].message == (
        "start_activity_method sets heartbeat_timeout but activity "
        + '"Activities.process" never calls activity.heartbeat'
    )


def test_heartbeating_activities_are_valid() -> None:
    assert (
        hits(
            """\
        from temporalio import activity, workflow
        from temporalio.activity import heartbeat as beat

        @activity.defn
        async def direct() -> None:
            activity.heartbeat()

        @activity.defn
        async def aliased() -> None:
            beat("progress")

        def report() -> None:
            activity.heartbeat()

        @activity.defn
        async def through_helper() -> None:
            report()

        @activity.defn
        async def nested() -> None:
            def tick() -> None:
                activity.heartbeat()

            tick()

        @activity.defn
        async def as_callback() -> None:
            run(callback=activity.heartbeat)

        class Activities:
            @activity.defn
            async def process(self) -> None:
                self.tick()

            def tick(self) -> None:
                activity.heartbeat()

        await workflow.execute_activity(direct, heartbeat_timeout=t)
        await workflow.execute_activity(aliased, heartbeat_timeout=t)
        await workflow.execute_activity(through_helper, heartbeat_timeout=t)
        await workflow.execute_activity(nested, heartbeat_timeout=t)
        await workflow.execute_activity(as_callback, heartbeat_timeout=t)
        await workflow.execute_activity_method(Activities.process, heartbeat_timeout=t)
        """,
            TPL004,
        )
        == []
    )


def test_calls_that_may_heartbeat_are_skipped() -> None:
    assert (
        hits(
            """\
        from temporalio import activity, workflow
        from myapp.work import do_work
        from myapp.wrappers import auto_heartbeater

        @activity.defn
        async def imported_helper() -> None:
            await do_work()

        @activity.defn
        async def unknown_name(callback) -> None:
            callback()

        @auto_heartbeater
        @activity.defn
        async def wrapped() -> None:
            return None

        class Base:
            @activity.defn
            async def process(self) -> None:
                self.inherited()

            @activity.defn
            async def parent(self) -> None:
                super().process()

        await workflow.execute_activity(imported_helper, heartbeat_timeout=t)
        await workflow.execute_activity(unknown_name, heartbeat_timeout=t)
        await workflow.execute_activity(wrapped, heartbeat_timeout=t)
        await workflow.execute_activity_method(Base.process, heartbeat_timeout=t)
        await workflow.execute_activity_method(Base.parent, heartbeat_timeout=t)
        """,
            TPL004,
        )
        == []
    )


def test_unresolved_targets_and_no_timeout_are_skipped() -> None:
    assert (
        hits(
            """\
        from temporalio import activity, workflow
        from myapp.activities import imported

        @activity.defn
        async def idle() -> None:
            return None

        def plain() -> None:
            return None

        await workflow.execute_activity(idle, start_to_close_timeout=t)
        await workflow.execute_activity(idle, start_to_close_timeout=t, heartbeat_timeout=None)
        await workflow.execute_activity(imported, heartbeat_timeout=t)
        await workflow.execute_activity("idle", heartbeat_timeout=t)
        await workflow.execute_activity(plain, heartbeat_timeout=t)
        await workflow.execute_local_activity(idle, start_to_close_timeout=t)
        """,
            TPL004,
        )
        == []
    )


def test_noqa() -> None:
    assert (
        hits(
            """\
        from temporalio import activity, workflow

        @activity.defn
        async def idle() -> None:
            return None

        await workflow.execute_activity(idle, heartbeat_timeout=t)  # noqa: TPL004
        """,
            TPL004,
        )
        == []
    )
