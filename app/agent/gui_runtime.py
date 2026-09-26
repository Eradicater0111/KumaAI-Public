from app.agent.kuma_runtime import (
    _explicit_memory_operation_requested,
    create_kuma,
)
from app.memory.completed_turn_observation_owner import (
    KumaMemoryV2CompletedTurnOwner,
)

from app.agent.body_lifecycle import (
    release_owned_mouse_button_for_shutdown,
)

from app.integration_v2_live_turn_owner import (
    KumaIntegrationV2LiveTurnOwner,
)

from app.integration_v2_production_policy import (
    PRODUCTION_REALTIME_TRIGGER_POLICY,
)

from app.runtime_v2_live_owner import (
    KumaRuntimeV2LiveOwner,
)

from app.runtime_observability import (
    RuntimeObservationSnapshot,
    project_runtime_observation,
)


class KumaGUIRuntime:
    """
    GUI-facing runtime wrapper for the production KumaAgent.

    The GUI interacts with this class rather than constructing
    or configuring KumaAgent directly.
    """

    def __init__(
        self,
        confirmation_callback=None,
        status_callback=None,
    ):
        self.kuma = create_kuma()

        self._memory_v2_owner = (
            KumaMemoryV2CompletedTurnOwner()
        )

        self._runtime_v2_owner = (
            KumaRuntimeV2LiveOwner()
        )

        self._integration_v2_owner = (
            KumaIntegrationV2LiveTurnOwner(
                runtime_owner=self._runtime_v2_owner,
                realtime_runtime=self.kuma.realtime_runtime,
                trigger_policy=(
                    PRODUCTION_REALTIME_TRIGGER_POLICY
                ),
            )
        )

        self.kuma._runtime_observer = (
            self._runtime_v2_owner.observe_pipeline_event
        )

        if confirmation_callback is not None:
            self.kuma.confirmation_callback = (
                confirmation_callback
            )

        if status_callback is not None:
            self.kuma.status_callback = (
                status_callback
            )

    def runtime_trace_events(
        self,
    ):
        """
        Return bounded in-memory zero-authority runtime trace events.
        """

        return self._runtime_v2_owner.events()

    def runtime_observation_snapshot(
        self,
    ) -> RuntimeObservationSnapshot:
        """
        Return an immutable payload-free Runtime-2F diagnostic snapshot.

        Projection failure is fail-soft and has no effect on KUMA execution.
        """

        try:
            return project_runtime_observation(
                self._runtime_v2_owner.events()
            )
        except Exception:
            return RuntimeObservationSnapshot()

    def run(self, user_message):
        """
        Execute a user request through the production KUMA agent.

        This method is intentionally synchronous. The Qt worker/thread
        layer calls it outside the GUI thread.
        """
        explicit_memory_operation_requested = (
            _explicit_memory_operation_requested(
                self.kuma,
                user_message,
            )
        )

        return self._memory_v2_owner.run(
            lambda: self._integration_v2_owner.run(
                lambda prepared_realtime_turn: self.kuma.run(
                    user_message,
                    prepared_realtime_turn=prepared_realtime_turn,
                )
            ),
            user_message=user_message,
            explicit_memory_operation_requested=(
                explicit_memory_operation_requested
            ),
        )

    def shutdown(self):
        """
        Perform explicit normal-shutdown physical-body cleanup.

        The GUI calls this only after its worker has stopped,
        preventing a new KUMA body action from racing with release.
        """
        try:
            return (
                release_owned_mouse_button_for_shutdown()
            )
        finally:
            self._runtime_v2_owner.close()
