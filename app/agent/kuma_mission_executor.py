from __future__ import annotations

from app.agent.permissions import get_recovery_permission_level

from app.agent.objective_verifier import safe_verify_objective

from app.agent.recovery_state_verifier import safe_verify_state

from typing import Any

from app.agent.mission_result import (
    MissionExecutionResult,
)

from app.agent.permissions import (
    PermissionLevel,
    get_permission_level,
)

from app.agent.recovery_manager import (
    RecoveryAction,
    RecoveryDecision,
    RecoveryManager,
)

from app.agent.recovery_policy import (
    RecoveryPolicy,
)

from app.agent.recovery_state_verifier import (
    RecoveryStateVerifier,
)

from app.agent.objective_verifier import (
    ObjectiveVerifier,
)

from app.agent.recovery_strategy import (
    RecoveryStrategyAdvisor,
)


class KumaMissionExecutor:
    """
    Adapter between the mission system and KumaAgent.

    The mission system decides WHAT objective is active.

    KumaAgent decides HOW to satisfy that objective.

    This adapter provides bounded operational recovery around
    individual mission-step attempts.

    Recovery is deliberately limited to:
        - safe bounded retries
        - existing argument normalization/validation
        - already registered/authorized alternatives
        - escalation

    It never modifies source code, changes KUMA's core logic,
    bypasses permissions, or creates a second planning loop.
    """

    def __init__(
        self,
        kuma,
        recovery_manager: RecoveryManager | None = None,
        recovery_policy: RecoveryPolicy | None = None,
        state_verifier: RecoveryStateVerifier | None = None,
        objective_verifier: ObjectiveVerifier | None = None,
        recovery_strategy_advisor: RecoveryStrategyAdvisor | None = None,
    ):
        self.kuma = kuma

        self.recovery_manager = (
            recovery_manager
            if recovery_manager is not None
            else RecoveryManager()
        )

        self.recovery_policy = (
            recovery_policy
            if recovery_policy is not None
            else RecoveryPolicy()
        )

        self.state_verifier = (
            state_verifier
            if state_verifier is not None
            else RecoveryStateVerifier()
        )

        self.objective_verifier = (
            objective_verifier
            if objective_verifier is not None
            else ObjectiveVerifier()
        )

        self.recovery_strategy_advisor = (
            recovery_strategy_advisor
            if recovery_strategy_advisor is not None
            else RecoveryStrategyAdvisor()
        )

    # =====================================================
    # EXACT RUNTIME PLAN BINDING
    # =====================================================

    def bind_runtime_plan(
        self,
        plan,
    ):
        """
        Preserve the exact active GoalPlan object for mission execution.

        This method grants no GUI authority.

        The runtime authority store remains responsible for verifying:
        - exact GoalPlan type,
        - exact plan object identity,
        - exact current GoalStep identity,
        - freshness,
        - current step binding.
        """

        self._runtime_plan = plan

    # =====================================================
    # EXECUTE
    # =====================================================

    def _observe_runtime_pipeline(
        self,
        *,
        event_kind,
        outcome,
    ):
        # Diagnostic forwarding only. Recovery behavior never depends on it.
        observer = getattr(
            self.kuma,
            "_observe_runtime_pipeline",
            None,
        )

        if not callable(
            observer
        ):
            return

        try:
            observer(
                event_kind=event_kind,
                outcome=outcome,
            )
        except Exception:
            return

    def execute(
        self,
        step,
    ) -> MissionExecutionResult:
        """
        Execute exactly one mission step with bounded recovery.

        A retry always re-executes the same mission step.

        Recovery never:
            - replans the mission
            - rewrites source code
            - bypasses permissions
            - invents new capabilities
            - recursively invokes run()
        """

        step_id = str(
            getattr(step, "id", "") or ""
        )

        executor = getattr(
            self.kuma,
            "execute_mission_step",
            None,
        )

        if executor is None:
            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                error=(
                    "KumaAgent does not expose "
                    "execute_mission_step()."
                ),
            )

        attempts = 0

        while True:

            # -------------------------------------------------
            # EXECUTE ONE ATTEMPT
            # -------------------------------------------------

            try:
                runtime_plan = getattr(
                    self,
                    "_runtime_plan",
                    None,
                )

                if runtime_plan is None:
                    result = executor(
                        step
                    )
                else:
                    result = executor(
                        step,
                        plan=runtime_plan,
                    )

            except Exception as error:
                result = MissionExecutionResult(
                    success=False,
                    step_id=step_id,
                    error=str(error),
                )

            # -------------------------------------------------
            # RESULT CONTRACT
            # -------------------------------------------------

            if not isinstance(
                result,
                MissionExecutionResult,
            ):
                result = MissionExecutionResult(
                    success=False,
                    step_id=step_id,
                    error=(
                        "KumaAgent returned an invalid "
                        "mission execution result."
                    ),
                )

            # -------------------------------------------------
            # SUCCESS
            # -------------------------------------------------

            if result.completed:
                return result

            # -------------------------------------------------
            # EXPLICIT LOWER-LAYER SAFETY ESCALATION
            # -------------------------------------------------
            #
            # A lower execution boundary may safely refuse an
            # action before execution.
            #
            # Recovery must never weaken that refusal by turning
            # it into RETRY or another action.
            # -------------------------------------------------

            explicit_recovery_action = str(
                result.recovery_action
                or ""
            ).strip().lower()

            if (
                explicit_recovery_action
                == RecoveryAction.ESCALATE.value
            ):
                self._observe_runtime_pipeline(
                    event_kind="recovery.decision",
                    outcome="escalate",
                )
                return result

            # -------------------------------------------------
            # IRREVERSIBLE EFFECT BARRIER
            # -------------------------------------------------
            #
            # A failed attempt that entered a physical effect
            # boundary may already have changed external state.
            #
            # This check occurs before diagnosis, verification,
            # policy, strategy, or retry selection. Those layers
            # may observe or escalate the result, but they may
            # never reopen this exact operation for automatic
            # execution.
            # -------------------------------------------------

            if (
                getattr(
                    result,
                    "effect_started",
                    False,
                )
                is True
            ):
                reason = (
                    "Execution entered an irreversible physical "
                    "effect boundary. Automatic retry is forbidden "
                    "because external state may already have changed."
                )

                result.recovery_action = (
                    RecoveryAction.ESCALATE.value
                )

                result.recovery_reason = (
                    reason
                )

                self._observe_runtime_pipeline(
                    event_kind="recovery.effect_barrier",
                    outcome="escalate",
                )
                self._observe_runtime_pipeline(
                    event_kind="recovery.decision",
                    outcome="escalate",
                )
                return result

            # -------------------------------------------------
            # DIAGNOSE FAILURE
            # -------------------------------------------------

            diagnosis = (
                self.recovery_manager.diagnose(
                    error=result.error,
                    verified=result.verified,
                    tool_name=result.tool_name,
                    result=result.result,
                )
            )

            # -------------------------------------------------
            # DANGEROUS ACTION CHECK
            # -------------------------------------------------

            dangerous = self._is_dangerous_tool(
                result.tool_name
            )

            # -------------------------------------------------
            # STATE + OBJECTIVE VERIFICATION
            # -------------------------------------------------
            #
            # A failed operation may still have achieved the
            # requested end-state.
            #
            # State and objective verification are READ-ONLY.
            # Even dangerous operations may be observed here,
            # but they may never be automatically retried.
            # -------------------------------------------------

            state_verification = None
            objective_verification = None

            if diagnosis.state_may_have_changed:

                state_verification = (
                    safe_verify_state(
                        self.state_verifier,
                        tool_name=result.tool_name,
                        arguments=result.arguments,
                        result=result.result,
                    )
                )
                self._observe_runtime_pipeline(
                    event_kind="state_verification.returned",
                    outcome=(
                        "contract_failure"
                        if getattr(
                            state_verification,
                            "contract_failure",
                            False,
                        ) is True
                        else "known_changed"
                        if (
                            getattr(
                                state_verification,
                                "known",
                                False,
                            ) is True
                            and getattr(
                                state_verification,
                                "state_changed",
                                None,
                            ) is True
                        )
                        else "known_unchanged"
                        if (
                            getattr(
                                state_verification,
                                "known",
                                False,
                            ) is True
                            and getattr(
                                state_verification,
                                "state_changed",
                                None,
                            ) is False
                        )
                        else "unknown"
                    ),
                )

                # ---------------------------------------------
                # UNKNOWN STATE
                # ---------------------------------------------

                if not state_verification.known:
                    decision = RecoveryDecision(
                        failure_type=diagnosis.failure_type,
                        action=RecoveryAction.ESCALATE,
                        reason=(
                            "Current state could not be verified "
                            "safely before recovery."
                        ),
                        retryable=False,
                    )

                else:

                    # -----------------------------------------
                    # OBJECTIVE VERIFICATION
                    # -----------------------------------------

                    objective_verification = (
                        safe_verify_objective(
                            self.objective_verifier,
                            objective=str(
                                getattr(
                                    step,
                                    "objective",
                                    "",
                                )
                                or ""
                            ),
                            success_criteria=list(
                                getattr(
                                    step,
                                    "success_criteria",
                                    [],
                                )
                                or []
                            ),
                            verification_requirements=list(
                                getattr(
                                    step,
                                    "verification_requirements",
                                    [],
                                )
                                or []
                            ),
                            tool_name=result.tool_name,
                            arguments=result.arguments,
                            state=state_verification,
                        )
                    )
                    self._observe_runtime_pipeline(
                        event_kind="objective_verification.returned",
                        outcome=(
                            "contract_failure"
                            if getattr(
                                objective_verification,
                                "contract_failure",
                                False,
                            ) is True
                            else "satisfied"
                            if (
                                getattr(
                                    objective_verification,
                                    "known",
                                    False,
                                ) is True
                                and getattr(
                                    objective_verification,
                                    "satisfied",
                                    None,
                                ) is True
                            )
                            else "unsatisfied"
                            if (
                                getattr(
                                    objective_verification,
                                    "known",
                                    False,
                                ) is True
                                and getattr(
                                    objective_verification,
                                    "satisfied",
                                    None,
                                ) is False
                            )
                            else "unknown"
                        ),
                    )

                    # -----------------------------------------
                    # TOOL FAILED, OBJECTIVE SUCCEEDED
                    # -----------------------------------------

                    if (
                        objective_verification.known
                        and objective_verification.satisfied
                    ):
                        return MissionExecutionResult(
                            success=True,
                            step_id=(
                                result.step_id
                                or step_id
                            ),
                            capability=result.capability,
                            tool_name=result.tool_name,
                            arguments=result.arguments,
                            result=result.result,
                            error="",
                            verified=True,
                            verification=(
                                "Recovered by objective verification. "
                                f"{objective_verification.summary} "
                                f"Evidence: "
                                f"{objective_verification.evidence}"
                            ),
                        )

                    # -----------------------------------------
                    # STATE CHANGED BUT OBJECTIVE NOT VERIFIED
                    # -----------------------------------------

                    if state_verification.state_changed:
                        decision = RecoveryDecision(
                            failure_type=diagnosis.failure_type,
                            action=RecoveryAction.ESCALATE,
                            reason=(
                                "The failed operation may already "
                                "have changed system state, but the "
                                "mission objective was not verified "
                                "as satisfied."
                            ),
                            retryable=False,
                        )

                    else:
                        decision = self.recovery_policy.decide(
                            diagnosis,
                            attempts=attempts,
                            dangerous=dangerous,
                        )

            else:
                decision = self.recovery_policy.decide(
                    diagnosis,
                    attempts=attempts,
                    dangerous=dangerous,
                )

            # -------------------------------------------------
            # EVIDENCE-AWARE RECOVERY STRATEGY
            # -------------------------------------------------
            #
            # Strategy combines diagnosis, policy, state, and
            # objective evidence.
            #
            # It may make recovery stricter, but it never grants
            # permission or executes another tool.
            # -------------------------------------------------

            strategy = (
                self.recovery_strategy_advisor.assess(
                    diagnosis=diagnosis,
                    policy_decision=decision,
                    state_verification=state_verification,
                    objective_verification=objective_verification,
                    dangerous=dangerous,
                )
            )
            self._observe_runtime_pipeline(
                event_kind="recovery.strategy_mode",
                outcome=("automatic" if getattr(strategy, "automatic", False) is True else "manual"),
            )

            decision = RecoveryDecision(
                failure_type=diagnosis.failure_type,
                action=strategy.action,
                reason=strategy.reason,
                retryable=(
                    strategy.action
                    == RecoveryAction.RETRY
                    and strategy.automatic
                ),
            )
            self._observe_runtime_pipeline(
                event_kind="recovery.decision",
                outcome=getattr(getattr(decision, "action", None), "value", ""),
            )

            # Advisory metadata for the mission layer.
            # This does not authorize another execution.
            result.recovery_action = (
                decision.action.value
            )

            result.recovery_reason = (
                decision.reason
            )

            recovery_evidence_parts = []

            if (
                state_verification is not None
                and state_verification.evidence
            ):
                recovery_evidence_parts.append(
                    "STATE: "
                    f"{state_verification.evidence}"
                )

            if (
                objective_verification is not None
                and objective_verification.evidence
            ):
                recovery_evidence_parts.append(
                    "OBJECTIVE: "
                    f"{objective_verification.evidence}"
                )

            result.recovery_evidence = (
                "\n".join(
                    recovery_evidence_parts
                )
            )

            print(
                "\nKUMA RECOVERY"
            )

            print(
                f"STEP → {result.step_id or step_id}"
            )

            print(
                f"FAILURE → {diagnosis.failure_type.value}"
            )

            print(
                f"ACTION → {decision.action.value}"
            )

            print(
                f"REASON → {decision.reason}"
            )

            # -------------------------------------------------
            # SAFE RETRY
            # -------------------------------------------------

            if decision.action == RecoveryAction.RETRY:

                attempts += 1

                print(
                    "KUMA RECOVERY → "
                    f"Retrying step "
                    f"{attempts}/"
                    f"{self.recovery_policy.max_retries}"
                )

                continue

            # -------------------------------------------------
            # ARGUMENT REPAIR
            # -------------------------------------------------

            if (
                decision.action
                == RecoveryAction.REPAIR_ARGUMENTS
            ):
                # Argument repair is already performed inside
                # KumaAgent.execute_mission_step() through its
                # existing normalization + validation pipeline.
                #
                # We deliberately do NOT invent a second repair
                # mechanism here.
                return result

            # -------------------------------------------------
            # ALTERNATIVE CAPABILITY
            # -------------------------------------------------

            if (
                decision.action
                == RecoveryAction.ALTERNATIVE_CAPABILITY
            ):
                # Alternative-capability selection requires
                # mission-aware replanning and is intentionally
                # not performed by this adapter yet.
                #
                # Returning the failure allows the mission
                # controller to stop/escalate safely.
                return result

            # -------------------------------------------------
            # RESUME FROM VERIFIED PARTIAL STATE
            # -------------------------------------------------
            #
            # RESUME never re-executes the failed tool here.
            #
            # KumaMissionExecutor is not a second planner.
            # Continuation belongs to the mission layer.
            # -------------------------------------------------

            if decision.action == RecoveryAction.RESUME:

                print(
                    "KUMA RECOVERY → "
                    "Verified partial state requires "
                    "mission-level continuation."
                )

                return result

            # -------------------------------------------------
            # ESCALATE / NONE
            # -------------------------------------------------

            return result

    # =====================================================
    # DANGEROUS ACTION DETECTION
    # =====================================================

    def _is_dangerous_tool(
        self,
        tool_name: str,
    ) -> bool:
        """
        Determine whether automatic recovery must be disabled
        for the tool involved in the failed attempt.

        Recovery fails closed for missing/malformed identity and
        for tools that the live KUMA runtime explicitly does not
        know. Isolated adapters without a tool registry preserve
        the historical permission classification used by tests.

        Recovery never changes permission levels.
        """

        try:

            tool_known = None

            registry = getattr(
                self.kuma,
                "tool_registry",
                None,
            )

            if isinstance(
                registry,
                dict,
            ):

                if type(tool_name) is str:
                    normalized_tool_name = (
                        tool_name.strip()
                    )
                else:
                    normalized_tool_name = ""

                tool_known = (
                    bool(normalized_tool_name)
                    and normalized_tool_name in registry
                )

            return (
                get_recovery_permission_level(
                    tool_name,
                    tool_known=tool_known,
                )
                == PermissionLevel.DANGEROUS
            )

        except Exception:
            # Permission-classification failure is itself
            # ambiguous. Recovery therefore fails closed.
            return True
