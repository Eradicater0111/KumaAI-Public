from __future__ import annotations

from app.agent.objective_verifier import safe_verify_objective

from app.agent.recovery_state_verifier import safe_verify_state

from ollama import chat

from app.agent.gui_argument_authority import (
    authorize_runtime_gui_arguments,
)

from app.vision.gui_target_verifier import (
    GUI_HOLD_TARGET_ATTESTATIONS,
    GUI_SEMANTIC_TARGET_ATTESTATIONS,
    GUI_TARGET_ATTESTATIONS,
    GuiTargetVerifier,
)
from app.agent.gui_step_authority_provenance import (
    RUNTIME_GUI_STEP_AUTHORITY,
    RUNTIME_GUI_STEP_AUTHORITY_PRODUCER,
)

from app.agent.gui_intent_authority import (
    validate_runtime_gui_authority,
)
from app.agent.gui_action_grounding import (
    MISSION_SEMANTIC_TARGET_TOOLS,
    gui_tool_names_for_capabilities,
    validate_planned_tool_binding,
    validate_runtime_gui_tool_binding,
)
from app.agent.permissions import (
    PermissionLevel,
    get_permission_level,
)
from app.agent.verifier import (
    verify_result,
    verification_report,
)
from app.agent.body_action_verifier import (
    FINGER_BODY_STATE_TOOLS,
    verify_body_action_postcondition,
)
from app.agent.mission_result import MissionExecutionResult
from app.agent.goal_decomposer import GoalDecomposer
from app.agent.planner_quality import PlannerQualityGate
from app.agent.mission_controller import MissionController
from app.agent.mission_runner import MissionRunner
from app.agent.kuma_mission_executor import KumaMissionExecutor
from app.agent.mission_state import MissionState, MissionStatus
from app.agent.mission_persistence import MissionPersistence
from app.agent.remaining_objective_resolver import (
    RemainingObjectiveResolver,
)
from app.agent.continuation_replay_guard import (
    ContinuationReplayGuard,
)
from app.agent.goal_plan import GoalStep
from app.agent.recovery_policy import RecoveryPolicy
from app.agent.recovery_state_verifier import (
    RecoveryStateVerifier,
)
from app.agent.objective_verifier import (
    ObjectiveVerifier,
)

from app.vision.gui_objective_verifier import (
    GUI_OUTCOME_TOOLS,
    GuiObjectiveVerifier,
)

from app.desktop.provenance import (
    SCREEN_DESKTOP_PROVENANCE,
)
from app.desktop.revalidation import (
    revalidate_desktop_context,
)
from app.desktop.runtime import (
    collect_desktop_context,
)


MAX_RECOVERY_CONTINUATION_CYCLES = 3
DESKTOP_ACTION_REVALIDATION_TIMEOUT_SECONDS = 2.0
DESKTOP_ACTION_REVALIDATION_MAX_WINDOWS = 32
DESKTOP_ACTION_REVALIDATION_MAX_AGE_SECONDS = 2.0


class MissionService:
    """
    Mission orchestration and one-step mission execution extracted from KumaAgent.

    The service owns mission lifecycle mechanics. KumaAgent remains the public
    compatibility facade and supplies the brain/tool/safety dependencies.
    """

    def __init__(self, kuma):
        self.kuma = kuma

        self.gui_objective_verifier = (
            GuiObjectiveVerifier()
        )

        self.gui_target_verifier = (
            GuiTargetVerifier()
        )

    def _revalidate_vision_target_desktop_context(
        self,
        observation_id,
    ):
        """Fail closed unless the current frontmost app still matches.

        This is a read-only execution prerequisite for a trusted semantic vision action. A match
        proves application identity continuity only; it grants no permission,
        target authority, or physical-action authority.
        """

        if (
            type(observation_id) is not str
            or not observation_id.strip()
        ):
            return (
                False,
                "Vision target action desktop context provenance requires "
                "an exact screen observation ID.",
            )

        observation_id = observation_id.strip()

        try:
            provenance = (
                SCREEN_DESKTOP_PROVENANCE.get(
                    observation_id
                )
            )
        except Exception:
            return (
                False,
                "Vision target action desktop context provenance lookup failed.",
            )

        if provenance is None:
            return (
                False,
                "Vision target action desktop context provenance is unavailable "
                "for the exact screen observation.",
            )

        try:
            current = collect_desktop_context(
                timeout_seconds=(
                    DESKTOP_ACTION_REVALIDATION_TIMEOUT_SECONDS
                ),
                max_windows=(
                    DESKTOP_ACTION_REVALIDATION_MAX_WINDOWS
                ),
            )
        except Exception:
            return (
                False,
                "Vision target action current desktop context collection failed.",
            )

        try:
            revalidation = revalidate_desktop_context(
                provenance.binding,
                provenance.desktop_before,
                provenance.desktop_after,
                current,
                max_current_age_seconds=(
                    DESKTOP_ACTION_REVALIDATION_MAX_AGE_SECONDS
                ),
            )
        except Exception:
            return (
                False,
                "Vision target action desktop context revalidation failed closed.",
            )

        if not revalidation.matched:
            diagnostic = "unknown"
            if (
                type(revalidation.diagnostics) is tuple
                and revalidation.diagnostics
                and type(revalidation.diagnostics[0]) is str
            ):
                diagnostic = revalidation.diagnostics[0]

            status = (
                revalidation.status
                if type(revalidation.status) is str
                else "unknown"
            )

            return (
                False,
                "Vision target action desktop context revalidation failed: "
                f"{status} ({diagnostic}).",
            )

        return True, ""

    def _revalidate_vision_click_desktop_context(
        self,
        observation_id,
    ):
        allowed, reason = (
            self._revalidate_vision_target_desktop_context(
                observation_id
            )
        )

        return (
            allowed,
            reason.replace(
                "Vision target action",
                "Vision click",
            ),
        )

    def _revalidate_vision_move_desktop_context(
        self,
        observation_id,
    ):
        allowed, reason = (
            self._revalidate_vision_target_desktop_context(
                observation_id
            )
        )

        return (
            allowed,
            reason.replace(
                "Vision target action",
                "Vision move",
            ),
        )

    def _revalidate_vision_hold_desktop_context(
        self,
        observation_id,
    ):
        allowed, reason = (
            self._revalidate_vision_target_desktop_context(
                observation_id
            )
        )

        return (
            allowed,
            reason.replace(
                "Vision target action",
                "Vision hold",
            ),
        )

    # =====================================================
    # TRUSTED FOCUSED TEXT MISSION LANE
    # =====================================================

    def _execute_trusted_focused_text(
        self,
        *,
        runtime_plan,
        runtime_step,
        arguments,
        approved,
    ):
        """Compose the complete trusted mission typing boundary.

        Returns:
            (execution, error, visual_verification)

        On admission failure:
            execution is None
            error is a fail-closed reason
            visual_verification is None

        Raw planner text is read exactly once to derive
        ExactTextIntentEvidence. No raw text is ever supplied to the
        physical executor.
        """

        from app.agent.runtime_gui_step_authority import (
            RUNTIME_GUI_STEP_AUTHORITY,
        )

        from app.agent.text_intent_evidence import (
            ExactTextIntentEvidence,
            ExactTextIntentEvidenceResult,
            derive_exact_text_intent_evidence,
        )

        from app.agent.gui_perception_refresh import (
            bootstrap_structured_ui_screen_context,
        )

        from app.agent.gui_dual_sensor_verification import (
            RuntimeDualSensorVisionVerificationResult,
            verify_runtime_focused_text_target,
        )

        from app.ui_observation.focus_workflow import (
            collect_bound_focused_ui,
        )

        from app.ui_observation.focus_target_producer import (
            FOCUS_TARGET_PRODUCER,
            FocusTargetProvenance,
            FocusTargetProvenanceProduction,
        )

        from app.agent.focused_text_receipt import (
            FOCUSED_TEXT_RECEIPT_PRODUCER,
            FocusedTextReceipt,
            FocusedTextReceiptProduction,
        )

        # -------------------------------------------------
        # EXACT PLAN + EXACT STEP AUTHORITY
        # -------------------------------------------------

        try:
            authority = (
                RUNTIME_GUI_STEP_AUTHORITY
                .get_current(
                    runtime_plan,
                    runtime_step,
                )
            )
        except Exception:
            authority = None

        if authority is None:
            return (
                None,
                (
                    "Trusted typing requires exact current "
                    "runtime plan/step authority."
                ),
                None,
            )

        if (
            getattr(
                authority,
                "planned_tool",
                None,
            )
            != "type_text"
        ):
            return (
                None,
                (
                    "Trusted typing authority is not bound "
                    "to type_text."
                ),
                None,
            )

        # -------------------------------------------------
        # EXACT HUMAN TEXT EVIDENCE
        # -------------------------------------------------

        if type(arguments) is not dict:
            return (
                None,
                "Trusted typing requires normalized arguments.",
                None,
            )

        proposed_text = arguments.get(
            "text"
        )

        try:
            text_result = (
                derive_exact_text_intent_evidence(
                    authority,
                    proposed_text,
                )
            )
        except Exception:
            text_result = None

        if (
            type(text_result)
            is not ExactTextIntentEvidenceResult
        ):
            return (
                None,
                "Exact text intent evidence is unavailable.",
                None,
            )

        text_evidence = (
            text_result.evidence
        )

        if (
            type(text_evidence)
            is not ExactTextIntentEvidence
        ):
            return (
                None,
                "Exact text intent evidence is unavailable.",
                None,
            )

        # From this boundary downward, proposed_text is no longer
        # used. The receipt is the only permitted carrier of text.

        target_intent = getattr(
            authority,
            "semantic_target_intent_snapshot",
            None,
        )

        if target_intent is None:
            return (
                None,
                (
                    "Trusted typing requires exact semantic "
                    "target intent authority."
                ),
                None,
            )

        human_goal = getattr(
            authority,
            "human_goal",
            "",
        )

        if (
            type(human_goal) is not str
            or not human_goal.strip()
        ):
            return (
                None,
                "Trusted typing human-goal authority is unavailable.",
                None,
            )

        # -------------------------------------------------
        # O0 — NEW TRUSTED STRUCTURED SCREEN CONTEXT
        # -------------------------------------------------

        try:
            bootstrap = (
                bootstrap_structured_ui_screen_context()
            )
        except Exception:
            bootstrap = None

        if not bool(
            getattr(
                bootstrap,
                "available",
                False,
            )
        ):
            return (
                None,
                (
                    "Trusted typing could not establish an "
                    "initial structured-screen context."
                ),
                None,
            )

        context = getattr(
            bootstrap,
            "context",
            None,
        )

        screen_observation = getattr(
            context,
            "screen_observation",
            None,
        )

        original_observation_id = getattr(
            screen_observation,
            "observation_id",
            "",
        )

        if (
            type(original_observation_id) is not str
            or not original_observation_id.strip()
        ):
            return (
                None,
                (
                    "Trusted typing initial screen "
                    "observation is unavailable."
                ),
                None,
            )

        # -------------------------------------------------
        # O0 -> O1 -> SEMANTIC TARGET -> VISUAL -> B8J
        # -------------------------------------------------
        #
        # This lane accepts NO planner x/y.
        # B8G remains reserved for the receipt producer.
        # -------------------------------------------------

        try:
            dual = (
                verify_runtime_focused_text_target(
                    intent=target_intent,
                    original_observation_id=(
                        original_observation_id
                    ),
                    human_goal=human_goal,
                    gui_target_verifier=(
                        self.kuma.gui_target_verifier
                    ),
                )
            )
        except Exception:
            dual = None

        if (
            type(dual)
            is not RuntimeDualSensorVisionVerificationResult
            or not bool(
                getattr(
                    dual,
                    "matched",
                    False,
                )
            )
            or getattr(
                dual,
                "evidence_consumed",
                None,
            )
            is not False
            or getattr(
                dual,
                "semantic_result",
                None,
            )
            is None
            or getattr(
                dual,
                "visual_verification",
                None,
            )
            is None
        ):
            return (
                None,
                (
                    "Trusted typing semantic/visual target "
                    "verification failed."
                ),
                None,
            )

        # -------------------------------------------------
        # FRESH FOCUS OBSERVATION
        # -------------------------------------------------

        try:
            focus_workflow = (
                collect_bound_focused_ui()
            )
        except Exception:
            focus_workflow = None

        focus_observation_id = getattr(
            focus_workflow,
            "focus_observation_id",
            "",
        )

        if (
            type(focus_observation_id) is not str
            or not focus_observation_id.strip()
        ):
            return (
                None,
                (
                    "Trusted typing could not establish "
                    "fresh focused-UI evidence."
                ),
                None,
            )

        # -------------------------------------------------
        # EXACT B7 <-> FOCUSED ELEMENT CORRELATION
        # -------------------------------------------------

        try:
            focus_production = (
                FOCUS_TARGET_PRODUCER.produce(
                    dual.semantic_result,
                    focus_observation_id,
                )
            )
        except Exception:
            focus_production = None

        if (
            type(focus_production)
            is not FocusTargetProvenanceProduction
        ):
            return (
                None,
                (
                    "Trusted typing focus-target "
                    "provenance is unavailable."
                ),
                None,
            )

        focus_provenance = (
            focus_production.provenance
        )

        if (
            type(focus_provenance)
            is not FocusTargetProvenance
            or focus_provenance.semantic_result
            is not dual.semantic_result
        ):
            return (
                None,
                (
                    "Trusted typing focus target does not "
                    "match exact semantic target identity."
                ),
                None,
            )

        # -------------------------------------------------
        # RECEIPT — ONE-AND-ONLY B8G CONSUMPTION
        # -------------------------------------------------

        try:
            receipt_production = (
                FOCUSED_TEXT_RECEIPT_PRODUCER.produce(
                    text_evidence,
                    focus_provenance,
                    dual.visual_verification,
                )
            )
        except Exception:
            receipt_production = None

        if (
            type(receipt_production)
            is not FocusedTextReceiptProduction
        ):
            return (
                None,
                (
                    "Trusted focused-text receipt "
                    "production failed."
                ),
                None,
            )

        receipt = (
            receipt_production.receipt
        )

        if (
            type(receipt)
            is not FocusedTextReceipt
            or receipt.text_evidence
            is not text_evidence
            or receipt.focus_provenance
            is not focus_provenance
            or receipt.semantic_result
            is not dual.semantic_result
        ):
            return (
                None,
                (
                    "Trusted focused-text receipt identity "
                    "contract failed."
                ),
                None,
            )

        # -------------------------------------------------
        # PRIVATE PHYSICAL EXECUTOR LANE
        # -------------------------------------------------
        #
        # NO text argument.
        # NO generic executor.
        # NO registered raw type_text invocation.
        # -------------------------------------------------

        try:
            execution = (
                self.kuma.executor
                .execute_focused_text(
                    receipt,
                    approved=approved,
                )
            )
        except Exception as error:
            return (
                None,
                (
                    "Trusted focused-text execution failed "
                    f"before returning a result: {error}"
                ),
                None,
            )

        return (
            execution,
            None,
            dual.visual_verification,
        )


    # =====================================================
    # TRUSTED SINGLE-KEY MISSION LANE
    # =====================================================

    def _execute_trusted_key(
        self,
        *,
        runtime_plan,
        runtime_step,
        arguments,
        approved,
    ):
        """Compose exact human key intent + fresh focus + receipt."""

        from app.agent.gui_step_authority_provenance import (
            RUNTIME_GUI_STEP_AUTHORITY,
        )

        from app.agent.key_intent_evidence import (
            ExactKeyIntentEvidence,
            ExactKeyIntentEvidenceResult,
            derive_exact_key_intent_evidence,
        )

        from app.agent.trusted_key_receipt import (
            TRUSTED_KEY_RECEIPT_PRODUCER,
            TrustedKeyReceipt,
            TrustedKeyReceiptProduction,
        )

        from app.ui_observation.focus_workflow import (
            collect_bound_focused_ui,
        )

        from app.ui_observation.focus_provenance import (
            FOCUS_DESKTOP_PROVENANCE,
            FocusDesktopProvenance,
        )

        # -------------------------------------------------
        # EXACT PLAN + STEP AUTHORITY
        # -------------------------------------------------

        try:
            authority = (
                RUNTIME_GUI_STEP_AUTHORITY
                .get_current(
                    runtime_plan,
                    runtime_step,
                )
            )
        except Exception:
            authority = None

        if authority is None:
            return (
                None,
                (
                    "Trusted key execution requires exact "
                    "current runtime plan/step authority."
                ),
            )

        if (
            getattr(
                authority,
                "planned_tool",
                None,
            )
            != "press_key"
        ):
            return (
                None,
                (
                    "Trusted key authority is not bound "
                    "to press_key."
                ),
            )

        # -------------------------------------------------
        # EXACT HUMAN KEY INTENT
        # -------------------------------------------------

        if type(arguments) is not dict:
            return (
                None,
                "Trusted key execution requires normalized arguments.",
            )

        proposed_key = (
            arguments.get(
                "key"
            )
        )

        try:
            evidence_result = (
                derive_exact_key_intent_evidence(
                    authority,
                    proposed_key,
                )
            )
        except Exception:
            evidence_result = None

        if (
            type(evidence_result)
            is not ExactKeyIntentEvidenceResult
            or not evidence_result.issued
        ):
            return (
                None,
                "Exact human key intent evidence is unavailable.",
            )

        key_evidence = (
            evidence_result.evidence
        )

        if (
            type(key_evidence)
            is not ExactKeyIntentEvidence
        ):
            return (
                None,
                "Exact human key intent evidence is unavailable.",
            )

        # proposed_key ends here.
        # No raw key value is passed to the executor.

        # -------------------------------------------------
        # FRESH BOUND FOCUS
        # -------------------------------------------------

        try:
            focus_workflow = (
                collect_bound_focused_ui()
            )
        except Exception:
            focus_workflow = None

        binding = getattr(
            focus_workflow,
            "binding",
            None,
        )

        focus_observation_id = getattr(
            binding,
            "focus_observation_id",
            "",
        )

        if (
            type(focus_observation_id) is not str
            or not focus_observation_id.strip()
        ):
            return (
                None,
                (
                    "Trusted key execution could not establish "
                    "fresh focused-UI provenance."
                ),
            )

        try:
            focus_provenance = (
                FOCUS_DESKTOP_PROVENANCE.get(
                    focus_observation_id
                )
            )
        except Exception:
            focus_provenance = None

        if (
            type(focus_provenance)
            is not FocusDesktopProvenance
            or focus_provenance.binding
            is not binding
        ):
            return (
                None,
                (
                    "Trusted key execution requires the exact "
                    "fresh focus provenance object."
                ),
            )

        # -------------------------------------------------
        # ONE-USE KEY RECEIPT
        # -------------------------------------------------

        try:
            receipt_production = (
                TRUSTED_KEY_RECEIPT_PRODUCER.produce(
                    key_evidence,
                    focus_provenance,
                )
            )
        except Exception:
            receipt_production = None

        if (
            type(receipt_production)
            is not TrustedKeyReceiptProduction
            or not receipt_production.issued
        ):
            return (
                None,
                "Trusted key receipt production failed.",
            )

        receipt = (
            receipt_production.receipt
        )

        if (
            type(receipt)
            is not TrustedKeyReceipt
            or receipt.key_evidence
            is not key_evidence
            or receipt.focus_provenance
            is not focus_provenance
        ):
            return (
                None,
                (
                    "Trusted key receipt identity contract "
                    "failed."
                ),
            )

        # -------------------------------------------------
        # PRIVATE EXECUTOR LANE
        # -------------------------------------------------

        try:
            execution = (
                self.kuma.executor
                .execute_trusted_key(
                    receipt,
                    approved=approved,
                )
            )
        except Exception as error:
            return (
                None,
                (
                    "Trusted key execution failed before "
                    "returning a result: "
                    f"{error}"
                ),
            )

        return (
            execution,
            None,
        )


    def _execute_trusted_scroll(
        self,
        *,
        runtime_plan,
        runtime_step,
        arguments,
        approved,
    ):
        from app.agent.gui_step_authority_provenance import (
            RUNTIME_GUI_STEP_AUTHORITY,
        )
        from app.agent.scroll_intent_evidence import (
            ExactScrollIntentEvidence,
            ExactScrollIntentEvidenceResult,
            derive_exact_scroll_intent_evidence,
        )
        from app.agent.pointer_desktop_provenance import (
            PointerDesktopProvenance,
            collect_pointer_desktop_provenance,
        )
        from app.agent.trusted_scroll_receipt import (
            TRUSTED_SCROLL_RECEIPT_PRODUCER,
            TrustedScrollReceipt,
            TrustedScrollReceiptProduction,
        )

        try:
            authority = (
                RUNTIME_GUI_STEP_AUTHORITY.get_current(
                    runtime_plan,
                    runtime_step,
                )
            )
        except Exception:
            authority = None

        if authority is None:
            return (
                None,
                (
                    "Trusted scroll requires exact current "
                    "runtime plan/step authority."
                ),
            )

        if (
            getattr(
                authority,
                "planned_tool",
                None,
            )
            != "scroll"
        ):
            return (
                None,
                "Trusted scroll authority is not bound to scroll.",
            )

        if type(arguments) is not dict:
            return (
                None,
                "Trusted scroll requires normalized arguments.",
            )

        proposed_amount = arguments.get(
            "amount"
        )

        try:
            evidence_result = (
                derive_exact_scroll_intent_evidence(
                    authority,
                    proposed_amount,
                )
            )
        except Exception:
            evidence_result = None

        if (
            type(evidence_result)
            is not ExactScrollIntentEvidenceResult
            or not evidence_result.issued
        ):
            return (
                None,
                "Exact human scroll intent evidence is unavailable.",
            )

        scroll_evidence = (
            evidence_result.evidence
        )

        if (
            type(scroll_evidence)
            is not ExactScrollIntentEvidence
        ):
            return (
                None,
                "Exact human scroll intent evidence is unavailable.",
            )

        try:
            pointer_result = (
                collect_pointer_desktop_provenance()
            )
        except Exception:
            pointer_result = None

        if not bool(
            getattr(
                pointer_result,
                "available",
                False,
            )
        ):
            return (
                None,
                (
                    "Trusted scroll could not establish fresh "
                    "pointer/desktop provenance."
                ),
            )

        pointer_provenance = (
            pointer_result.provenance
        )

        if (
            type(pointer_provenance)
            is not PointerDesktopProvenance
        ):
            return (
                None,
                (
                    "Trusted scroll pointer provenance "
                    "is unavailable."
                ),
            )

        try:
            production = (
                TRUSTED_SCROLL_RECEIPT_PRODUCER.produce(
                    scroll_evidence,
                    pointer_provenance,
                )
            )
        except Exception:
            production = None

        if (
            type(production)
            is not TrustedScrollReceiptProduction
            or not production.issued
        ):
            return (
                None,
                "Trusted scroll receipt production failed.",
            )

        receipt = production.receipt

        if (
            type(receipt)
            is not TrustedScrollReceipt
            or receipt.scroll_evidence
            is not scroll_evidence
            or receipt.pointer_provenance
            is not pointer_provenance
        ):
            return (
                None,
                "Trusted scroll receipt identity contract failed.",
            )

        try:
            execution = (
                self.kuma.executor
                .execute_trusted_scroll(
                    receipt,
                    approved=approved,
                )
            )
        except Exception as error:
            return (
                None,
                (
                    "Trusted scroll execution failed before "
                    f"returning a result: {error}"
                ),
            )

        return (
            execution,
            None,
        )


    def _execute_trusted_hold_mouse(
        self,
        *,
        runtime_plan,
        runtime_step,
        arguments,
        approved,
    ):
        from app.agent.gui_step_authority_provenance import (
            RUNTIME_GUI_STEP_AUTHORITY,
        )
        from app.agent.mouse_button_intent_evidence import (
            ExactMouseHoldIntentEvidence,
            derive_exact_mouse_hold_intent_evidence,
        )
        from app.agent.pointer_desktop_provenance import (
            PointerDesktopProvenance,
            collect_pointer_desktop_provenance,
        )
        from app.agent.trusted_mouse_button_receipt import (
            TRUSTED_MOUSE_HOLD_RECEIPT_PRODUCER,
            TrustedMouseHoldReceipt,
        )

        try:
            authority = RUNTIME_GUI_STEP_AUTHORITY.get_current(
                runtime_plan,
                runtime_step,
            )
        except Exception:
            authority = None

        if authority is None:
            return (
                None,
                "Trusted mouse hold requires exact runtime authority.",
            )

        if type(arguments) is not dict:
            return (
                None,
                "Trusted mouse hold requires normalized arguments.",
            )

        button = arguments.get(
            "button",
            "left",
        )

        evidence_result = (
            derive_exact_mouse_hold_intent_evidence(
                authority,
                button,
            )
        )

        if not evidence_result.issued:
            return (
                None,
                "Exact mouse-hold intent evidence is unavailable.",
            )

        evidence = evidence_result.evidence

        if type(evidence) is not ExactMouseHoldIntentEvidence:
            return (
                None,
                "Exact mouse-hold intent evidence is unavailable.",
            )

        pointer_result = (
            collect_pointer_desktop_provenance()
        )

        if not pointer_result.available:
            return (
                None,
                "Trusted mouse hold requires fresh pointer provenance.",
            )

        pointer = pointer_result.provenance

        if type(pointer) is not PointerDesktopProvenance:
            return (
                None,
                "Trusted mouse hold pointer provenance is unavailable.",
            )

        production = (
            TRUSTED_MOUSE_HOLD_RECEIPT_PRODUCER.produce(
                evidence,
                pointer,
            )
        )

        if not production.issued:
            return (
                None,
                "Trusted mouse-hold receipt production failed.",
            )

        receipt = production.receipt

        if (
            type(receipt) is not TrustedMouseHoldReceipt
            or receipt.hold_evidence is not evidence
            or receipt.pointer_provenance is not pointer
        ):
            return (
                None,
                "Trusted mouse-hold receipt identity failed.",
            )

        return (
            self.kuma.executor.execute_trusted_hold_mouse(
                receipt,
                approved=approved,
            ),
            None,
        )


    def _execute_trusted_hold_mouse_vision(
        self,
        *,
        runtime_plan,
        runtime_step,
        arguments,
        target_verification,
        approved,
    ):
        from app.agent.gui_step_authority_provenance import (
            RUNTIME_GUI_STEP_AUTHORITY,
        )
        from app.agent.mouse_button_intent_evidence import (
            ExactMouseHoldVisionIntentEvidence,
            derive_exact_mouse_hold_vision_intent_evidence,
        )
        from app.agent.trusted_semantic_hold_receipt import (
            TRUSTED_SEMANTIC_HOLD_RECEIPT_PRODUCER,
            TrustedSemanticHoldReceipt,
        )

        if type(arguments) is not dict:
            return (
                None,
                "Trusted semantic hold requires normalized arguments.",
            )

        try:
            authority = (
                RUNTIME_GUI_STEP_AUTHORITY.get_current(
                    runtime_plan,
                    runtime_step,
                )
            )
        except Exception:
            authority = None

        if authority is None:
            return (
                None,
                "Trusted semantic hold requires exact runtime authority.",
            )

        if (
            getattr(
                authority,
                "planned_tool",
                None,
            )
            != "hold_mouse_vision"
        ):
            return (
                None,
                "Runtime authority is not bound to hold_mouse_vision.",
            )

        if (
            target_verification is None
            or getattr(
                target_verification,
                "satisfied",
                False,
            )
            is not True
        ):
            return (
                None,
                "Trusted semantic hold requires exact target verification.",
            )

        button = arguments.get(
            "button",
            "left",
        )

        evidence_result = (
            derive_exact_mouse_hold_vision_intent_evidence(
                authority,
                button,
            )
        )

        if not evidence_result.issued:
            return (
                None,
                "Exact semantic-hold button intent is unavailable.",
            )

        hold_evidence = (
            evidence_result.evidence
        )

        if (
            type(hold_evidence)
            is not ExactMouseHoldVisionIntentEvidence
        ):
            return (
                None,
                "Exact semantic-hold button intent is unavailable.",
            )

        production = (
            TRUSTED_SEMANTIC_HOLD_RECEIPT_PRODUCER.produce(
                hold_evidence,
                target_verification,
                observation_id=arguments.get(
                    "observation_id",
                    "",
                ),
                vision_x=arguments.get(
                    "x"
                ),
                vision_y=arguments.get(
                    "y"
                ),
                button=button,
            )
        )

        if not production.issued:
            return (
                None,
                "Trusted semantic-hold receipt production failed.",
            )

        receipt = production.receipt

        if (
            type(receipt)
            is not TrustedSemanticHoldReceipt
            or receipt.hold_evidence
            is not hold_evidence
            or receipt.target_verification
            is not target_verification
        ):
            return (
                None,
                "Trusted semantic-hold receipt identity failed.",
            )

        execution = (
            self.kuma.executor
            .execute_trusted_hold_mouse_vision(
                receipt,
                approved=approved,
            )
        )

        return (
            execution,
            None,
        )


    def _execute_trusted_release_mouse(
        self,
        *,
        runtime_plan,
        runtime_step,
        arguments,
        approved,
    ):
        from app.agent.gui_step_authority_provenance import (
            RUNTIME_GUI_STEP_AUTHORITY,
        )
        from app.agent.mouse_button_intent_evidence import (
            ExactMouseReleaseIntentEvidence,
            derive_exact_mouse_release_intent_evidence,
        )
        from app.agent.trusted_mouse_button_receipt import (
            TRUSTED_MOUSE_RELEASE_RECEIPT_PRODUCER,
            TrustedMouseReleaseReceipt,
        )

        if (
            type(arguments) is not dict
            or arguments
        ):
            return (
                None,
                "Trusted mouse release accepts no planner button identity.",
            )

        try:
            authority = RUNTIME_GUI_STEP_AUTHORITY.get_current(
                runtime_plan,
                runtime_step,
            )
        except Exception:
            authority = None

        if authority is None:
            return (
                None,
                "Trusted mouse release requires exact runtime authority.",
            )

        evidence_result = (
            derive_exact_mouse_release_intent_evidence(
                authority
            )
        )

        if not evidence_result.issued:
            return (
                None,
                "Exact mouse-release intent evidence is unavailable.",
            )

        evidence = evidence_result.evidence

        if (
            type(evidence)
            is not ExactMouseReleaseIntentEvidence
        ):
            return (
                None,
                "Exact mouse-release intent evidence is unavailable.",
            )

        production = (
            TRUSTED_MOUSE_RELEASE_RECEIPT_PRODUCER.produce(
                evidence
            )
        )

        if not production.issued:
            return (
                None,
                "Trusted mouse-release receipt production failed.",
            )

        receipt = production.receipt

        if (
            type(receipt)
            is not TrustedMouseReleaseReceipt
            or receipt.release_evidence
            is not evidence
        ):
            return (
                None,
                "Trusted mouse-release receipt identity failed.",
            )

        return (
            self.kuma.executor.execute_trusted_release_mouse(
                receipt,
                approved=approved,
            ),
            None,
        )

    def _observe_runtime_pipeline(
        self,
        *,
        event_kind,
        outcome,
    ):
        # Diagnostic forwarding only. Mission behavior never depends on it.
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

    def execute_mission_step(
        self,
        step,
        plan=None,
    ) -> MissionExecutionResult:
        """
        Execute exactly one planned mission step.

        MissionController owns the larger mission.
        KUMA owns local reasoning and capability selection.

        This method must never recursively invoke run().
        """

        if step is None:
            return MissionExecutionResult(
                success=False,
                step_id="",
                error="Mission step was empty.",
            )

        step_id = str(
            getattr(step, "id", "") or ""
        ).strip()

        objective = str(
            getattr(step, "objective", "") or ""
        ).strip()

        if not step_id:
            return MissionExecutionResult(
                success=False,
                step_id="",
                error="Mission step has no ID.",
            )

        if not objective:
            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                error="Mission step has no objective.",
            )

        self.kuma.emit_status(
            f"Executing mission step: {step_id}"
        )

        print(
            "\nKUMA MISSION STEP"
        )

        print(
            f"ID → {step_id}"
        )

        print(
            f"OBJECTIVE → {objective}"
        )

        required_capabilities = list(
            getattr(
                step,
                "required_capabilities",
                [],
            )
            or []
        )

        planned_tool = str(
            getattr(
                step,
                "planned_tool",
                "",
            )
            or ""
        ).strip()

        gui_target_intent = getattr(
            step,
            "gui_target_intent",
            None,
        )

        gui_authority = str(
            getattr(
                step,
                "gui_authority",
                "",
            )
            or ""
        ).strip()

        gui_authority_goal = str(
            getattr(
                step,
                "gui_authority_goal",
                "",
            )
            or ""
        ).strip()

        success_criteria = list(
            getattr(
                step,
                "success_criteria",
                [],
            )
            or []
        )

        verification_requirements = list(
            getattr(
                step,
                "verification_requirements",
                [],
            )
            or []
        )

        print(
            "REQUIRED CAPABILITIES → "
            f"{required_capabilities}"
        )

        print(
            "PLANNED TOOL → "
            f"{planned_tool or '<none>'}"
        )

        print(
            "GUI AUTHORITY → "
            f"{gui_authority or '<none>'}"
        )

        print(
            "SUCCESS CRITERIA → "
            f"{success_criteria}"
        )

        print(
            "VERIFICATION REQUIREMENTS → "
            f"{verification_requirements}"
        )

        continuation_replay_context = getattr(
            step,
            "_continuation_replay_context",
            None,
        )

        return self._execute_single_mission_step(
            step_id=step_id,
            objective=objective,
            success_criteria=(
                success_criteria
            ),
            verification_requirements=(
                verification_requirements
            ),
            required_capabilities=(
                required_capabilities
            ),
            planned_tool=planned_tool,
            gui_target_intent=gui_target_intent,
            gui_authority=gui_authority,
            gui_authority_goal=gui_authority_goal,
            continuation_replay_context=(
                continuation_replay_context
            ),
        runtime_plan=plan,
            runtime_step=step,
        )


    def get_tools_for_capabilities(
        self,
        capabilities,
    ):
        """
        Return only runtime tools exposed by the supplied
        semantic capabilities.
        """

        selected = []
        seen = set()

        for capability in capabilities or []:

            for tool_name in (
                self.kuma.capability_registry.tools_for(
                    capability
                )
            ):

                if tool_name in seen:
                    continue

                tool = self.kuma.tool_registry.get(
                    tool_name
                )

                if tool is None:
                    continue

                selected.append(tool)
                seen.add(tool_name)

        return selected


    def _execute_single_mission_step(
        self,
        step_id: str,
        objective: str,
        success_criteria: list[str],
        verification_requirements: list[str],
        required_capabilities: list[str],
        planned_tool: str = "",
        gui_target_intent=None,
        gui_authority: str = "",
        gui_authority_goal: str = "",
        continuation_replay_context: dict | None = None,
        runtime_plan=None,
        runtime_step=None,
    ) -> MissionExecutionResult:
        """
        Ask the KUMA brain to select one capability/tool for
        the active mission step and execute it through the
        existing safety pipeline.

        Exactly one tool call is permitted.
        """

        authority_valid, authority_error = (
            validate_runtime_gui_authority(
                planned_tool,
                gui_authority,
            )
        )

        if not authority_valid:
            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                error=authority_error,
                verified=False,
                recovery_action="escalate",
                recovery_reason=authority_error,
            )

        binding_valid, binding_error = (
            validate_planned_tool_binding(
                self.kuma.capability_registry,
                required_capabilities,
                planned_tool,
            )
        )

        if not binding_valid:
            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                error=binding_error,
                verified=False,
                recovery_action="escalate",
                recovery_reason=binding_error,
            )

        gui_bound_tools = (
            gui_tool_names_for_capabilities(
                self.kuma.capability_registry,
                required_capabilities,
            )
        )

        capability_text = (
            ", ".join(required_capabilities)
            if required_capabilities
            else "No explicit capability restriction."
        )

        success_criteria_text = (
            "\n".join(
                f"- {criterion}"
                for criterion in success_criteria
            )
            if success_criteria
            else "- none provided"
        )

        verification_requirements_text = (
            "\n".join(
                f"- {requirement}"
                for requirement
                in verification_requirements
            )
            if verification_requirements
            else "- none provided"
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are executing ONE step of a larger "
                    "KUMA mission.\n\n"
                    "Mission step:\n"
                    f"{objective}\n\n"
                    "Allowed semantic capabilities:\n"
                    f"{capability_text}\n\n"
                    "Planner-bound tool:\n"
                    f"{planned_tool or '<none>'}\n\n"
                    "Success criteria:\n"
                    f"{success_criteria_text}\n\n"
                    "Verification requirements:\n"
                    f"{verification_requirements_text}\n\n"
                    "Any physical GUI action must directly "
                    "support this mission objective and its "
                    "success criteria.\n"
                    "Choose exactly one capability/tool needed "
                    "to advance this step.\n"
                    "Do not attempt the entire mission.\n"
                    "Do not claim completion without execution "
                    "and verification.\n"
                    "Use a tool only when necessary."
                ),
            },
            {
                "role": "user",
                "content": objective,
            },
        ]

        try:
            selected_tools = self.get_tools_for_capabilities(
                required_capabilities
            )

            if gui_bound_tools:
                bound_tool = (
                    self.kuma.tool_registry.get(
                        planned_tool
                    )
                )

                if bound_tool is None:
                    return MissionExecutionResult(
                        success=False,
                        step_id=step_id,
                        error=(
                            f"Planner-bound GUI tool "
                            f"'{planned_tool}' is not registered."
                        ),
                        verified=False,
                        recovery_action="escalate",
                        recovery_reason=(
                            "Planner-bound GUI tool is not "
                            "registered."
                        ),
                    )

                selected_tools = [
                    bound_tool
                ]

            if not selected_tools:
                return MissionExecutionResult(
                    success=False,
                    step_id=step_id,
                    error=(
                        "Mission step has no registered tools "
                        "for its required capabilities."
                    ),
                )

            response = chat(
                model=self.kuma.model,
                messages=messages,
                tools=selected_tools,
                think=False,
                options={
                    "num_ctx": 4096,
                    "temperature": 0.0,
                },
            )

        except Exception as error:
            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                error=(
                    f"KUMA mission brain failed: {error}"
                ),
            )

        model_message = (
            response.message
        )

        tool_calls = list(
            getattr(
                model_message,
                "tool_calls",
                [],
            )
            or []
        )

        if not tool_calls:

            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                error=(
                    "KUMA did not select a tool for "
                    "the mission step."
                ),
            )

        if len(tool_calls) > 1:

            print(
                "KUMA MISSION SAFETY → "
                f"Model proposed {len(tool_calls)} tools."
            )

            print(
                "KUMA MISSION SAFETY → "
                "Only the first tool is permitted."
            )

        tool_call = tool_calls[0]

        try:

            tool_name = (
                tool_call.function.name
            )

            raw_arguments = (
                tool_call.function.arguments
            )

            if raw_arguments is None:
                arguments = {}

            elif isinstance(
                raw_arguments,
                dict,
            ):
                arguments = dict(
                    raw_arguments
                )

            else:
                arguments = dict(
                    raw_arguments
                )

        except Exception as error:

            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                error=(
                    f"Invalid mission tool call: {error}"
                ),
            )

        # -------------------------------------------------
        # PLANNER → RUNTIME GUI TOOL BINDING
        # -------------------------------------------------

        runtime_binding_valid, runtime_binding_error = (
            validate_runtime_gui_tool_binding(
                self.kuma.capability_registry,
                required_capabilities,
                planned_tool,
                tool_name,
            )
        )

        if not runtime_binding_valid:
            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                tool_name=tool_name,
                arguments=arguments,
                error=runtime_binding_error,
                verified=False,
                recovery_action="escalate",
                recovery_reason=runtime_binding_error,
            )

        # -------------------------------------------------
        # CAPABILITY CONSTRAINT
        # -------------------------------------------------

        capability = self._mission_capability_for_tool(
            tool_name,
            required_capabilities,
        )

        if capability is None:

            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                tool_name=tool_name,
                arguments=arguments,
                error=(
                    f"Tool '{tool_name}' is not permitted "
                    "for the mission step's capabilities."
                ),
            )

        # -------------------------------------------------
        # EXISTING ARGUMENT NORMALIZATION
        # -------------------------------------------------

        try:

            arguments = self.kuma.normalize_tool_arguments(
                objective,
                tool_name,
                arguments,
            )

        except Exception as error:

            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                capability=capability,
                tool_name=tool_name,
                arguments=arguments,
                error=(
                    f"Mission arguments could not be "
                    f"normalized: {error}"
                ),
            )

        # -------------------------------------------------
        # EXISTING ARGUMENT VALIDATION
        # -------------------------------------------------

        arguments_valid, argument_error = (
            self.kuma.validate_tool_arguments(
                tool_name,
                arguments,
            )
        )

        if not arguments_valid:

            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                capability=capability,
                tool_name=tool_name,
                arguments=arguments,
                error=argument_error,
            )

        # -------------------------------------------------
        # RECOVERY CONTINUATION REPLAY GUARD
        # -------------------------------------------------
        #
        # Arguments are already normalized and validated here.
        #
        # This prevents superficially different model arguments
        # from bypassing exact replay detection.
        #
        # ReplayGuard itself grants no permission.
        # -------------------------------------------------

        if continuation_replay_context is not None:

            replay_guard = (
                ContinuationReplayGuard()
            )

            replay_decision = replay_guard.assess_context(
                proposed_tool=tool_name,
                proposed_arguments=arguments,
                context=continuation_replay_context,
            )

            if not replay_decision.allowed:

                print(
                    "KUMA CONTINUATION SAFETY → "
                    f"{replay_decision.reason}"
                )

                return MissionExecutionResult(
                    success=False,
                    step_id=step_id,
                    capability=capability,
                    tool_name=tool_name,
                    arguments=arguments,
                    error=replay_decision.reason,
                    verified=False,
                    recovery_action="escalate",
                    recovery_reason=(
                        replay_decision.reason
                    ),
                )

        # -------------------------------------------------
        # HUMAN GOAL → NORMALIZED GUI ARGUMENT AUTHORITY
        # -------------------------------------------------
        #
        # The planner/runtime model may choose arguments only
        # after the action class is authorized by 7.3C1.
        #
        # C2 independently checks the final normalized argument
        # set against the ORIGINAL human mission goal.
        #
        # Ungrounded arguments require exact, fail-closed human
        # confirmation before permissions or execution.
        #
        # This gate does not execute tools and does not bypass
        # the existing permission system.
        # -------------------------------------------------

        # -------------------------------------------------
        # SEMANTIC VISION-TARGET ATTESTATION
        # -------------------------------------------------
        #
        # click_vision is special:
        #
        # 7.1 proves observation provenance and geometry.
        # 7.3D proves that the exact proposed point currently
        # corresponds to the human-authorized visible target.
        #
        # The verifier is read-only. UNKNOWN, mismatch, or
        # verifier failure always stops execution.
        # -------------------------------------------------

        target_verification = None
        semantic_target_verified = False

        if tool_name in MISSION_SEMANTIC_TARGET_TOOLS:

            target_action_label = {
                "click_vision": "Vision click",
                "move_mouse_vision": "Vision move",
                "hold_mouse_vision": "Vision hold",
            }.get(
                tool_name,
                "Vision target action",
            )

            # -------------------------------------------------
            # B8K3 / PHASE 8B — DUAL-SENSOR TARGET VERIFICATION
            # -------------------------------------------------
            #
            # The model-selected observation belongs to the
            # screen it inspected (O0).
            #
            # B8K2 consumes O0 and independently captures a
            # fresh screen + AX context (O1).
            #
            # The visual verifier runs ONCE on O1. The exact
            # returned object must then survive B8J -> B8F ->
            # B8G identity checks.
            #
            # Only after that complete chain succeeds may
            # MissionService promote semantic_target_verified.
            #
            # Model x/y are proposals only. Trusted runtime
            # replaces observation_id and x/y with the fresh
            # O1 + K4 derived target point. button/clicks remain
            # unchanged.
            # -------------------------------------------------

            from app.agent.gui_dual_sensor_verification import (
                verify_runtime_dual_sensor_vision_target,
            )

            original_observation_id = (
                arguments.get(
                    "observation_id",
                    "",
                )
            )

            dual_verification = (
                verify_runtime_dual_sensor_vision_target(
                    raw_target_intent=gui_target_intent,
                    original_observation_id=(
                        original_observation_id
                    ),
                    x=arguments.get("x"),
                    y=arguments.get("y"),
                    human_goal=gui_authority_goal,
                    gui_target_verifier=(
                        self.gui_target_verifier
                    ),
                )
            )

            if not dual_verification.matched:

                diagnostic = (
                    dual_verification.diagnostics[0]
                    if dual_verification.diagnostics
                    else "unknown"
                )

                target_error = (
                    f"{target_action_label} semantic target "
                    "verification failed: dual-sensor "
                    f"corroboration {diagnostic}."
                )

                print(
                    "KUMA MISSION SAFETY → "
                    f"{target_error}"
                )

                return MissionExecutionResult(
                    success=False,
                    step_id=step_id,
                    capability=capability,
                    tool_name=tool_name,
                    arguments=arguments,
                    error=target_error,
                    verified=False,
                    recovery_action="escalate",
                    recovery_reason=target_error,
                )

            # Trusted runtime rebind.
            #
            # The physical action now targets the fresh screen
            # observation and exact K4 point used by BOTH AX and
            # visual evidence. button/clicks remain unchanged.
            arguments = dict(arguments)

            arguments["observation_id"] = (
                dual_verification.fresh_observation_id
            )

            arguments["x"] = (
                dual_verification.vision_x
            )

            arguments["y"] = (
                dual_verification.vision_y
            )

            # Re-validate the exact executable tool contract after
            # trusted target rebinding.
            (
                rebound_arguments_valid,
                rebound_argument_error,
            ) = self.kuma.validate_tool_arguments(
                tool_name,
                arguments,
            )

            if not rebound_arguments_valid:

                return MissionExecutionResult(
                    success=False,
                    step_id=step_id,
                    capability=capability,
                    tool_name=tool_name,
                    arguments=arguments,
                    error=(
                        "Trusted fresh target rebinding "
                        "produced invalid runtime arguments: "
                        f"{rebound_argument_error}"
                    ),
                    verified=False,
                    recovery_action="escalate",
                    recovery_reason=(
                        "Fresh target argument "
                        "revalidation failed."
                    ),
                )

            # -------------------------------------------------
            # EXECUTABLE-ARGUMENT RECOVERY REPLAY GUARD
            # -------------------------------------------------
            #
            # The earlier continuation guard checks the exact
            # normalized model proposal (O0).
            #
            # B8K4 then replaces observation_id and x/y with
            # independently refreshed O1 + trusted derived point.
            #
            # The arguments that can actually reach permission,
            # attestation, and execution must therefore be replay
            # checked again after trusted rebinding.
            #
            # This second check grants no permission or authority.
            # -------------------------------------------------

            if continuation_replay_context is not None:

                executable_replay_guard = (
                    ContinuationReplayGuard()
                )

                executable_replay_decision = (
                    executable_replay_guard.assess_context(
                        proposed_tool=tool_name,
                        proposed_arguments=arguments,
                        context=continuation_replay_context,
                    )
                )

                if not executable_replay_decision.allowed:

                    print(
                        "KUMA CONTINUATION SAFETY → "
                        f"{executable_replay_decision.reason}"
                    )

                    return MissionExecutionResult(
                        success=False,
                        step_id=step_id,
                        capability=capability,
                        tool_name=tool_name,
                        arguments=arguments,
                        error=(
                            executable_replay_decision.reason
                        ),
                        verified=False,
                        recovery_action="escalate",
                        recovery_reason=(
                            executable_replay_decision.reason
                        ),
                    )

            target_verification = (
                dual_verification.visual_verification
            )

            # Only this fresh dual-sensor target-proof path
            # may promote the semantic flag for a trusted
            # semantic target action.
            semantic_target_verified = True

        argument_authority = (
            authorize_runtime_gui_arguments(
                goal=gui_authority_goal,
                tool_name=tool_name,
                arguments=arguments,
                confirmation_fn=(
                    self.kuma.request_confirmation
                ),
                semantic_target_verified=(
                    semantic_target_verified
                ),
            )
        )

        if not argument_authority.allowed:

            print(
                "KUMA MISSION SAFETY → "
                f"{argument_authority.reason}"
            )

            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                capability=capability,
                tool_name=tool_name,
                arguments=arguments,
                error=argument_authority.reason,
                verified=False,
                recovery_action="escalate",
                recovery_reason=(
                    argument_authority.reason
                ),
            )

        # -------------------------------------------------
        # CURRENT DESKTOP CONTEXT REVALIDATION
        # -------------------------------------------------
        #
        # A5 provenance belongs to the exact ScreenObservation
        # used by click_vision. Immediately before permission /
        # attestation / execution, collect a fresh native desktop
        # sample and require A5-1 to match the original frontmost
        # application identity.
        #
        # MATCHED is evidence only. It does not grant permission
        # or target authority. MISMATCH / UNKNOWN fail closed.
        # -------------------------------------------------

        if tool_name in MISSION_SEMANTIC_TARGET_TOOLS:

            if tool_name == "click_vision":

                desktop_revalidator = (
                    self._revalidate_vision_click_desktop_context
                )

            elif tool_name == "hold_mouse_vision":

                desktop_revalidator = (
                    self._revalidate_vision_hold_desktop_context
                )

            else:

                desktop_revalidator = (
                    self._revalidate_vision_move_desktop_context
                )

            (
                desktop_context_matched,
                desktop_context_error,
            ) = desktop_revalidator(
                arguments.get(
                    "observation_id",
                    "",
                )
            )

            if not desktop_context_matched:

                print(
                    "KUMA MISSION SAFETY → "
                    f"{desktop_context_error}"
                )

                return MissionExecutionResult(
                    success=False,
                    step_id=step_id,
                    capability=capability,
                    tool_name=tool_name,
                    arguments=arguments,
                    error=desktop_context_error,
                    verified=False,
                    recovery_action="escalate",
                    recovery_reason=(
                        desktop_context_error
                    ),
                )

        # -------------------------------------------------
        # EXISTING PERMISSION SYSTEM
        # -------------------------------------------------

        permission = get_permission_level(
            tool_name
        )
        self._observe_runtime_pipeline(
            event_kind="permission.classified",
            outcome=getattr(permission, "value", ""),
        )

        approved = False

        if (
            permission
            == PermissionLevel.DANGEROUS
        ):

            approved = self.kuma.request_confirmation(
                tool_name,
                arguments,
            )

            if not approved:

                return MissionExecutionResult(
                    success=False,
                    step_id=step_id,
                    capability=capability,
                    tool_name=tool_name,
                    arguments=arguments,
                    error=(
                        f"Mission action '{tool_name}' "
                        "was denied."
                    ),
                )

        # -------------------------------------------------
        # ISSUE EXACT SEMANTIC CLICK ATTESTATION
        # -------------------------------------------------
        #
        # This happens only after:
        # - C1 action-class authority
        # - 7.3B exact tool binding
        # - normalization / validation
        # - replay guard
        # - 7.3D semantic target verification
        # - C2 argument authority
        # - A6 current desktop-context revalidation
        # - permission processing
        #
        # click_vision must consume this exact attestation.
        # -------------------------------------------------

        semantic_attestation_store = None

        if (
            tool_name in MISSION_SEMANTIC_TARGET_TOOLS
            and target_verification is not None
            and target_verification.satisfied
        ):

            try:

                if tool_name == "click_vision":

                    GUI_TARGET_ATTESTATIONS.issue(
                        result=target_verification,
                        button=arguments.get(
                            "button",
                            "left",
                        ),
                        clicks=arguments.get(
                            "clicks",
                            1,
                        ),
                    )

                    semantic_attestation_store = (
                        GUI_TARGET_ATTESTATIONS
                    )

                elif tool_name == "move_mouse_vision":

                    GUI_SEMANTIC_TARGET_ATTESTATIONS.issue(
                        result=target_verification,
                    )

                    semantic_attestation_store = (
                        GUI_SEMANTIC_TARGET_ATTESTATIONS
                    )

                elif tool_name == "hold_mouse_vision":

                    GUI_HOLD_TARGET_ATTESTATIONS.issue(
                        result=target_verification,
                        button=arguments.get(
                            "button",
                            "left",
                        ),
                    )

                    semantic_attestation_store = (
                        GUI_HOLD_TARGET_ATTESTATIONS
                    )

                else:
                    raise RuntimeError(
                        "Unsupported trusted semantic "
                        "target action."
                    )

            except Exception as error:

                attestation_error = (
                    "Could not issue semantic target "
                    f"attestation: {error}"
                )

                return MissionExecutionResult(
                    success=False,
                    step_id=step_id,
                    capability=capability,
                    tool_name=tool_name,
                    arguments=arguments,
                    error=attestation_error,
                    verified=False,
                    recovery_action="escalate",
                    recovery_reason=(
                        attestation_error
                    ),
                )

        # -------------------------------------------------
        # EXECUTE
        # -------------------------------------------------

        print(
            "KUMA MISSION TOOL → "
            f"{tool_name}({arguments})"
        )

        try:

            if tool_name == "type_text":
                execution, trusted_text_error, trusted_text_visual = (
                    self._execute_trusted_focused_text(
                        runtime_plan=runtime_plan,
                        runtime_step=runtime_step,
                        arguments=arguments,
                        approved=approved,
                    )
                )

                if trusted_text_error is not None:
                    return MissionExecutionResult(
                        success=False,
                        step_id=step_id,
                        error=trusted_text_error,
                        verified=False,
                    )

                action_result = execution
                target_verification = trusted_text_visual
                semantic_target_verified = True

            elif tool_name == "press_key":
                action_result, trusted_key_error = (
                    self._execute_trusted_key(
                        runtime_plan=runtime_plan,
                        runtime_step=runtime_step,
                        arguments=arguments,
                        approved=approved,
                    )
                )

                if trusted_key_error is not None:
                    return MissionExecutionResult(
                        success=False,
                        step_id=step_id,
                        error=trusted_key_error,
                        verified=False,
                    )

            elif tool_name == "scroll":
                action_result, trusted_scroll_error = (
                    self._execute_trusted_scroll(
                        runtime_plan=runtime_plan,
                        runtime_step=runtime_step,
                        arguments=arguments,
                        approved=approved,
                    )
                )

                if trusted_scroll_error is not None:
                    return MissionExecutionResult(
                        success=False,
                        step_id=step_id,
                        error=trusted_scroll_error,
                        verified=False,
                    )

            elif tool_name == "hold_mouse_vision":
                action_result, trusted_vision_hold_error = (
                    self._execute_trusted_hold_mouse_vision(
                        runtime_plan=runtime_plan,
                        runtime_step=runtime_step,
                        arguments=arguments,
                        target_verification=target_verification,
                        approved=approved,
                    )
                )

                if trusted_vision_hold_error is not None:
                    return MissionExecutionResult(
                        success=False,
                        step_id=step_id,
                        error=trusted_vision_hold_error,
                        verified=False,
                    )

            elif tool_name == "hold_mouse":
                action_result, trusted_hold_error = (
                    self._execute_trusted_hold_mouse(
                        runtime_plan=runtime_plan,
                        runtime_step=runtime_step,
                        arguments=arguments,
                        approved=approved,
                    )
                )

                if trusted_hold_error is not None:
                    return MissionExecutionResult(
                        success=False,
                        step_id=step_id,
                        error=trusted_hold_error,
                        verified=False,
                    )

            elif tool_name == "release_mouse":
                action_result, trusted_release_error = (
                    self._execute_trusted_release_mouse(
                        runtime_plan=runtime_plan,
                        runtime_step=runtime_step,
                        arguments=arguments,
                        approved=approved,
                    )
                )

                if trusted_release_error is not None:
                    return MissionExecutionResult(
                        success=False,
                        step_id=step_id,
                        error=trusted_release_error,
                        verified=False,
                    )

            else:
                action_result = (
                    self.kuma.executor.execute(
                        tool_name=tool_name,
                        arguments=arguments,
                        approved=approved,
                    )
                )
                self._observe_runtime_pipeline(
                    event_kind="executor.returned",
                    outcome=("success" if getattr(action_result, "success", False) is True else "failure"),
                )

        except Exception as error:

            if tool_name in FINGER_BODY_STATE_TOOLS:

                reason = (
                    "Finger action raised after entering the "
                    "physical execution boundary; automatic "
                    "replay is forbidden. "
                    f"{error}"
                )

                return MissionExecutionResult(
                    success=False,
                    step_id=step_id,
                    capability=capability,
                    tool_name=tool_name,
                    arguments=arguments,
                    error=str(error),
                    verified=False,
                    recovery_action="escalate",
                    recovery_reason=reason,
                )

            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                capability=capability,
                tool_name=tool_name,
                arguments=arguments,
                error=str(error),
            )

        finally:

            if semantic_attestation_store is not None:
                semantic_attestation_store.clear()

        if not action_result.success:

            if tool_name in FINGER_BODY_STATE_TOOLS:

                reason = (
                    action_result.error
                    or "Finger action execution failed."
                )

                return MissionExecutionResult(
                    success=False,
                    step_id=step_id,
                    capability=capability,
                    tool_name=tool_name,
                    arguments=arguments,
                    result=action_result.result,
                    error=reason,
                    verified=False,
                    recovery_action="escalate",
                    recovery_reason=(
                        "Finger-state action failed after "
                        "entering the physical execution "
                        "boundary; automatic retry is forbidden."
                    ),
                    effect_started=(
                        getattr(
                            action_result,
                            "effect_started",
                            False,
                        )
                        is True
                    ),
                )

            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                capability=capability,
                tool_name=tool_name,
                arguments=arguments,
                result=action_result.result,
                error=(
                    action_result.error
                    or "Mission tool execution failed."
                ),
                effect_started=(
                    getattr(
                        action_result,
                        "effect_started",
                        False,
                    )
                    is True
                ),
            )

        result = (
            action_result.result
        )

        # -------------------------------------------------
        # VERIFY
        # -------------------------------------------------

        action_verified = verify_result(
            tool_name,
            result,
            action_result.success,
        )
        self._observe_runtime_pipeline(
            event_kind="verifier.returned",
            outcome=("true" if action_verified is True else "false"),
        )

        action_verification = (
            verification_report(
                tool_name,
                result,
                action_result.success,
            )
        )

        if tool_name in FINGER_BODY_STATE_TOOLS:

            (
                body_verified,
                body_verification,
            ) = verify_body_action_postcondition(
                tool_name=tool_name,
                arguments=arguments,
            )
            self._observe_runtime_pipeline(
                event_kind="body_verifier.returned",
                outcome=("true" if body_verified is True else "false"),
            )

            if not body_verified:

                return MissionExecutionResult(
                    success=False,
                    step_id=step_id,
                    capability=capability,
                    tool_name=tool_name,
                    arguments=arguments,
                    result=result,
                    error=(
                        "Finger action returned success, but "
                        "the live KUMA body state did not "
                        "satisfy its exact postcondition."
                    ),
                    verified=False,
                    verification=(
                        f"{action_verification} "
                        f"{body_verification}"
                    ),
                    recovery_action="escalate",
                    recovery_reason=(
                        "Finger-state postcondition could not "
                        "be verified; automatic replay is "
                        "forbidden."
                    ),
                    effect_started=(
                        getattr(
                            action_result,
                            "effect_started",
                            False,
                        )
                        is True
                    ),
                )

            action_verification = (
                f"{action_verification} "
                f"{body_verification}"
            )

        if not action_verified:

            return MissionExecutionResult(
                success=False,
                step_id=step_id,
                capability=capability,
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                error=(
                    f"Mission step '{step_id}' "
                    "action could not be verified."
                ),
                verified=False,
                verification=(
                    action_verification
                ),
                effect_started=(
                    getattr(
                        action_result,
                        "effect_started",
                        False,
                    )
                    is True
                ),
            )

        # -------------------------------------------------
        # POST-ACTION GUI OBJECTIVE VERIFICATION
        # -------------------------------------------------
        #
        # Executor success proves only that the GUI action was
        # issued. It does NOT prove that the planned UI end-state
        # was achieved.
        #
        # State-changing GUI actions therefore require a fresh,
        # read-only post-action screen verification before the
        # mission step may complete.
        # -------------------------------------------------

        if tool_name in GUI_OUTCOME_TOOLS:

            gui_verification = (
                self.gui_objective_verifier
                .verify_current_screen(
                    objective=objective,
                    success_criteria=(
                        success_criteria
                    ),
                    verification_requirements=(
                        verification_requirements
                    ),
                    tool_name=tool_name,
                )
            )

            gui_evidence = str(
                gui_verification.evidence
                or ""
            ).strip()

            verification = (
                f"{action_verification} "
                "Post-action GUI verification: "
                f"{gui_verification.summary}"
            )

            if gui_evidence:
                verification += (
                    f" Evidence: {gui_evidence}"
                )

            if (
                not gui_verification.known
                or not gui_verification.satisfied
            ):

                reason = (
                    "The GUI action executed, but the "
                    "mission objective was not independently "
                    "verified as satisfied. "
                    f"{gui_verification.summary}"
                )

                return MissionExecutionResult(
                    success=False,
                    step_id=step_id,
                    capability=capability,
                    tool_name=tool_name,
                    arguments=arguments,
                    result=result,
                    error=reason,
                    verified=False,
                    verification=verification,
                    recovery_action="escalate",
                    recovery_reason=reason,
                    recovery_evidence=(
                        gui_evidence
                    ),
                    effect_started=(
                        getattr(
                            action_result,
                            "effect_started",
                            False,
                        )
                        is True
                    ),
                )

            return MissionExecutionResult(
                success=True,
                step_id=step_id,
                capability=capability,
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                verified=True,
                verification=verification,
                recovery_evidence=(
                    gui_evidence
                ),
                effect_started=(
                    getattr(
                        action_result,
                        "effect_started",
                        False,
                    )
                    is True
                ),
            )

        # -------------------------------------------------
        # NON-GUI ACTION VERIFICATION
        # -------------------------------------------------

        return MissionExecutionResult(
            success=True,
            step_id=step_id,
            capability=capability,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            verified=True,
            verification=(
                action_verification
            ),
            effect_started=(
                getattr(
                    action_result,
                    "effect_started",
                    False,
                )
                is True
            ),
        )


    def _mission_capability_for_tool(
        self,
        tool_name: str,
        required_capabilities: list[str],
    ) -> str | None:
        """
        Return the capability that authorizes a tool for the
        current mission step.
        """
        for capability in (
            required_capabilities or []
        ):

            if tool_name in (
                self.kuma.capability_registry.tools_for(
                    capability
                )
            ):
                return capability

        return None


    def execute_mission(
        self,
        goal: str,
    ):
        """
        Execute a complete KUMA mission from a natural-language goal.

        Pipeline:

            goal
              ↓
            decomposition
              ↓
            quality gate
              ↓
            mission controller
              ↓
            mission runner
              ↓
            KUMA mission executor
              ↓
            verified step execution
        """

        goal = str(
            goal or ""
        ).strip()

        if not goal:
            return MissionExecutionResult(
                success=False,
                step_id="",
                error="Mission goal cannot be empty.",
            )

        print(
            "\nKUMA MISSION → Starting mission"
        )

        mission_state = MissionState.create(
            goal
        )

        mission_persistence = MissionPersistence()

        mission_persistence.create(
            mission_state
        )

        mission_state.start()

        mission_persistence.save(
            mission_state
        )

        print(
            f"KUMA MISSION GOAL → {goal}"
        )

        # -------------------------------------------------
        # DECOMPOSE
        # -------------------------------------------------

        decomposer = GoalDecomposer(
            model=self.kuma.model,
            capability_registry=self.kuma.capability_registry,
        )

        plan, decomposition_error = (
            decomposer.decompose(
                goal
            )
        )

        if decomposition_error:

            print(
                "KUMA MISSION → Decomposition failed."
            )

            return MissionExecutionResult(
                success=False,
                step_id="",
                error=(
                    "Mission decomposition failed: "
                    f"{decomposition_error}"
                ),
            )

        if plan is None:

            return MissionExecutionResult(
                success=False,
                step_id="",
                error=(
                    "Mission decomposition returned "
                    "no plan."
                ),
            )

        # -------------------------------------------------
        # QUALITY GATE
        # -------------------------------------------------

        quality_gate = PlannerQualityGate(
            available_capabilities=(
                self.kuma.capability_registry.names()
            ),
        )

        accepted, reasons = (
            quality_gate.validate(
                plan
            )
        )

        if not accepted:

            print(
                "KUMA MISSION → Plan rejected."
            )

            for reason in reasons:
                print(
                    f"KUMA PLANNER REJECTION → {reason}"
                )

            return MissionExecutionResult(
                success=False,
                step_id="",
                error=(
                    "Mission plan rejected: "
                    + "; ".join(reasons)
                ),
            )

        # -------------------------------------------------
        # HUMAN INTENT → GUI ACTION-CLASS AUTHORITY
        # -------------------------------------------------
        #
        # Planner output is not authority.
        #
        # Explicit action classes derive authority from the
        # original user goal. Planner-introduced GUI action
        # classes require one fail-closed confirmation.
        #
        # This confirmation does NOT approve eventual tool
        # execution and does not bypass runtime permissions.
        # -------------------------------------------------

        authority_production = (
            RUNTIME_GUI_STEP_AUTHORITY_PRODUCER.authorize_plan(
                goal=goal,
                plan=plan,
                confirmation_fn=(
                    self.kuma.request_confirmation
                ),
            )
        )

        authority_decision = (
            authority_production.decision
        )

        if not authority_decision.allowed:

            print(
                "KUMA MISSION → GUI authority rejected."
            )

            return MissionExecutionResult(
                success=False,
                step_id="",
                error=(
                    "Mission plan GUI authority rejected: "
                    f"{authority_decision.reason}"
                ),
                verified=False,
            )

        print(
            "\nKUMA MISSION PLAN"
        )

        print(
            plan.summary()
        )

        # -------------------------------------------------
        # CONTROLLER
        # -------------------------------------------------

        controller = MissionController(
            goal=goal,
        )

        valid, controller_error = (
            controller.set_plan(
                plan
            )
        )

        if not valid:
            RUNTIME_GUI_STEP_AUTHORITY.clear()

            return MissionExecutionResult(
                success=False,
                step_id="",
                error=(
                    "Mission controller rejected plan: "
                    f"{controller_error}"
                ),
            )

        mission_state = MissionState.from_controller(
            controller,
            mission_state,
        )

        mission_persistence.save(
            mission_state
        )

        # -------------------------------------------------
        # EXECUTOR ADAPTER
        # -------------------------------------------------

        mission_executor = (
            KumaMissionExecutor(
                self.kuma
            )
        )

        mission_executor.bind_runtime_plan(
            plan
        )

        # -------------------------------------------------
        # RUNNER
        # -------------------------------------------------

        def persist_state(
            controller,
        ):
            nonlocal mission_state

            mission_state = (
                MissionState.from_controller(
                    controller,
                    mission_state,
                )
            )

            mission_persistence.save(
                mission_state
            )

        runner = MissionRunner(
            controller=controller,
            execute_step=(
                mission_executor.execute
            ),
            on_state_change=persist_state,
        )

        result = runner.run_mission()

        mission_state = MissionState.from_controller(
            controller,
            mission_state,
        )

        if controller.is_complete():
            mission_state.mark_completed(
                result=result.result
            )
        elif (
            str(
                result.recovery_action
                or ""
            ).strip().lower()
            == "resume"
        ):

            mission_state.status = (
                MissionStatus.PAUSED
            )

            mission_state.touch()

        elif not result.success:
            mission_state.status = MissionStatus.FAILED
            mission_state.touch()

        mission_persistence.save(
            mission_state
        )

        # -------------------------------------------------
        # FINAL STATUS
        # -------------------------------------------------

        if controller.is_complete():

            print(
                "\nKUMA MISSION → COMPLETE"
            )

        else:

            print(
                "\nKUMA MISSION → STOPPED"
            )

        print(
            controller.summary()
        )

        return result


    def _verify_post_continuation_objective(
        self,
        *,
        controller,
        mission_state,
        persistence,
        current_step,
    ) -> MissionExecutionResult:
        """
        Independently verify the ORIGINAL GoalStep after one
        verified recovery-continuation action.

        This boundary is read-only until the verification result
        is known.

        It does not:
        - execute tools
        - grant permissions
        - repeat continuation
        - infer completion from tool success
        - allow a model to declare completion
        """

        protected_known = bool(
            getattr(
                mission_state,
                "continuation_guard_known",
                False,
            )
        )

        protected_tool = str(
            getattr(
                mission_state,
                "continuation_guard_tool",
                "",
            )
            or ""
        ).strip()

        protected_arguments = dict(
            getattr(
                mission_state,
                "continuation_guard_arguments",
                {},
            )
            or {}
        )

        if (
            not protected_known
            or not protected_tool
        ):

            reason = (
                "Post-continuation objective verification "
                "cannot establish which executed operation "
                "produced the current state."
            )

            print(
                "KUMA OBJECTIVE VERIFICATION → UNKNOWN"
            )

            print(
                f"REASON → {reason}"
            )

            mission_state.status = (
                MissionStatus.PAUSED
            )

            mission_state.touch()

            persistence.save(
                mission_state
            )

            return MissionExecutionResult(
                success=False,
                step_id=current_step.id,
                error=reason,
                verified=False,
                recovery_action="escalate",
                recovery_reason=reason,
                recovery_evidence=(
                    mission_state.last_evidence
                ),
            )

        state_verification = (
            safe_verify_state(
                RecoveryStateVerifier(),
                tool_name=protected_tool,
                arguments=protected_arguments,
                result=mission_state.last_evidence,
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

        if not state_verification.known:

            reason = (
                "Current state could not be independently "
                "verified after the continuation action. "
                f"{state_verification.summary}"
            )

            print(
                "KUMA OBJECTIVE VERIFICATION → UNKNOWN STATE"
            )

            print(
                f"REASON → {reason}"
            )

            mission_state.status = (
                MissionStatus.PAUSED
            )

            mission_state.touch()

            persistence.save(
                mission_state
            )

            return MissionExecutionResult(
                success=False,
                step_id=current_step.id,
                result=(
                    mission_state.last_evidence
                ),
                error=reason,
                verified=False,
                verification=(
                    state_verification.summary
                ),
                recovery_action="escalate",
                recovery_reason=reason,
                recovery_evidence=(
                    state_verification.evidence
                    or mission_state.last_evidence
                ),
            )

        objective_verification = (
            safe_verify_objective(
                ObjectiveVerifier(),
                objective=str(
                    current_step.objective
                    or ""
                ),
                success_criteria=list(
                    current_step.success_criteria
                    or []
                ),
                verification_requirements=list(
                    current_step.verification_requirements
                    or []
                ),
                tool_name=protected_tool,
                arguments=protected_arguments,
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

        verification_evidence = str(
            objective_verification.evidence
            or state_verification.evidence
            or mission_state.last_evidence
            or ""
        ).strip()

        if not objective_verification.known:

            reason = (
                "The original mission-step objective could "
                "not be independently verified. "
                f"{objective_verification.summary}"
            )

            print(
                "KUMA OBJECTIVE VERIFICATION → UNKNOWN"
            )

            print(
                f"REASON → {reason}"
            )

            if state_verification.evidence:

                controller.task_state.set_evidence(
                    state_verification.evidence
                )

                mission_state = (
                    MissionState.from_controller(
                        controller,
                        mission_state,
                    )
                )

            mission_state.status = (
                MissionStatus.PAUSED
            )

            mission_state.touch()

            persistence.save(
                mission_state
            )

            return MissionExecutionResult(
                success=False,
                step_id=current_step.id,
                result=verification_evidence,
                error=reason,
                verified=False,
                verification=(
                    objective_verification.summary
                ),
                recovery_action="escalate",
                recovery_reason=reason,
                recovery_evidence=(
                    verification_evidence
                ),
            )

        if objective_verification.satisfied is True:

            completed = (
                controller
                .complete_current_step_from_verification(
                    result=(
                        verification_evidence
                        or objective_verification.summary
                    ),
                    evidence=verification_evidence,
                    reason=(
                        objective_verification.summary
                    ),
                )
            )

            if not completed:

                reason = (
                    "Objective verification succeeded, but "
                    "the active GoalStep could not be marked "
                    "complete safely."
                )

                mission_state.status = (
                    MissionStatus.PAUSED
                )

                mission_state.touch()

                persistence.save(
                    mission_state
                )

                return MissionExecutionResult(
                    success=False,
                    step_id=current_step.id,
                    error=reason,
                    verified=False,
                    recovery_action="escalate",
                    recovery_reason=reason,
                    recovery_evidence=(
                        verification_evidence
                    ),
                )

            mission_state = (
                MissionState.from_controller(
                    controller,
                    mission_state,
                )
            )

            if controller.is_complete():

                mission_state.mark_completed(
                    result=(
                        verification_evidence
                        or objective_verification.summary
                    )
                )

            else:

                mission_state.status = (
                    MissionStatus.PAUSED
                )

                mission_state.touch()

            persistence.save(
                mission_state
            )

            print(
                "KUMA OBJECTIVE VERIFICATION → SATISFIED"
            )

            print(
                "KUMA MISSION → "
                f"Step '{current_step.id}' independently "
                "verified complete."
            )

            return MissionExecutionResult(
                success=True,
                step_id=current_step.id,
                tool_name=protected_tool,
                arguments=protected_arguments,
                result=(
                    verification_evidence
                    or objective_verification.summary
                ),
                error="",
                verified=True,
                verification=(
                    "Original GoalStep independently "
                    "verified as satisfied. "
                    f"{objective_verification.summary}"
                ),
                recovery_action="",
                recovery_reason="",
                recovery_evidence=(
                    verification_evidence
                ),
            )

        if objective_verification.satisfied is False:

            resolution = (
                RemainingObjectiveResolver(
                    model_call=(
                        self.kuma.call_goal_decision_model
                    )
                )
                .resolve(
                    step=current_step,
                    evidence=(
                        verification_evidence
                    ),
                    recovery_reason=(
                        objective_verification.summary
                    ),
                )
            )

            if not resolution.known:

                reason = (
                    "The original objective is known to remain "
                    "unfinished, but KUMA could not safely "
                    "determine the next remaining objective. "
                    f"{resolution.reason}"
                )

                print(
                    "KUMA OBJECTIVE VERIFICATION → "
                    "UNSATISFIED / REMAINDER UNKNOWN"
                )

                mission_state.status = (
                    MissionStatus.PAUSED
                )

                mission_state.touch()

                persistence.save(
                    mission_state
                )

                return MissionExecutionResult(
                    success=False,
                    step_id=current_step.id,
                    result=verification_evidence,
                    error=reason,
                    verified=False,
                    verification=(
                        objective_verification.summary
                    ),
                    recovery_action="escalate",
                    recovery_reason=reason,
                    recovery_evidence=(
                        verification_evidence
                    ),
                )

            controller.task_state.set_evidence(
                verification_evidence
            )

            controller.task_state.set_remaining_objective(
                resolution.remaining_objective
            )

            controller.task_state.clear_continuation_verification_pending()

            recovery_cycles = (
                controller.task_state
                .increment_recovery_continuation_cycles()
            )

            controller.task_state.add_observation(
                "Original mission-step objective independently "
                "verified as unfinished; a new remaining "
                "objective was resolved. Recovery continuation "
                f"cycle {recovery_cycles}/"
                f"{MAX_RECOVERY_CONTINUATION_CYCLES}."
            )

            mission_state = (
                MissionState.from_controller(
                    controller,
                    mission_state,
                )
            )

            mission_state.status = (
                MissionStatus.PAUSED
            )

            mission_state.touch()

            persistence.save(
                mission_state
            )

            print(
                "KUMA OBJECTIVE VERIFICATION → UNSATISFIED"
            )

            print(
                "KUMA NEW REMAINING OBJECTIVE → "
                f"{resolution.remaining_objective}"
            )

            print(
                "KUMA RECOVERY CYCLES → "
                f"{recovery_cycles}/"
                f"{MAX_RECOVERY_CONTINUATION_CYCLES}"
            )

            print(
                "KUMA MISSION → "
                "No continuation action executed during "
                "objective verification."
            )

            if (
                recovery_cycles
                >= MAX_RECOVERY_CONTINUATION_CYCLES
            ):

                reason = (
                    "Automatic recovery continuation budget "
                    "exhausted for the current GoalStep. "
                    "Further continuation requires external "
                    "review rather than another autonomous "
                    "recovery cycle."
                )

                return MissionExecutionResult(
                    success=False,
                    step_id=current_step.id,
                    result=(
                        resolution.remaining_objective
                    ),
                    error=reason,
                    verified=False,
                    verification=(
                        "Original GoalStep remains unfinished "
                        "after the maximum bounded number of "
                        "verified continuation cycles."
                    ),
                    recovery_action="escalate",
                    recovery_reason=reason,
                    recovery_evidence=(
                        verification_evidence
                    ),
                )

            return MissionExecutionResult(
                success=True,
                step_id=current_step.id,
                result=(
                    resolution.remaining_objective
                ),
                error="",
                verified=False,
                verification=(
                    "Original GoalStep was independently "
                    "verified as unfinished."
                ),
                recovery_action="resume",
                recovery_reason=(
                    resolution.reason
                ),
                recovery_evidence=(
                    verification_evidence
                ),
            )

        reason = (
            "Objective verifier returned a known result "
            "without a valid satisfied state."
        )

        mission_state.status = (
            MissionStatus.PAUSED
        )

        mission_state.touch()

        persistence.save(
            mission_state
        )

        return MissionExecutionResult(
            success=False,
            step_id=current_step.id,
            error=reason,
            verified=False,
            recovery_action="escalate",
            recovery_reason=reason,
            recovery_evidence=(
                verification_evidence
            ),
        )


    def _execute_resumed_continuation(
        self,
        *,
        controller,
        mission_state,
        persistence,
        current_step,
        remaining_objective: str,
    ) -> MissionExecutionResult:
        """
        Execute at most ONE recovery-continuation action.

        This never completes the original GoalStep.

        The continuation still passes through:
        - capability constraints
        - argument normalization
        - argument validation
        - replay protection
        - permission / confirmation
        - normal executor
        - tool verification
        - bounded recovery

        Automatic retries are disabled at this boundary.
        """

        remaining_objective = str(
            remaining_objective
            or ""
        ).strip()

        if not remaining_objective:

            return MissionExecutionResult(
                success=False,
                step_id=current_step.id,
                error=(
                    "Recovery continuation has no "
                    "remaining objective."
                ),
                verified=False,
                recovery_action="escalate",
                recovery_reason=(
                    "Continuation requires a previously "
                    "resolved remaining objective."
                ),
            )

        continuation_step = GoalStep(
            id=current_step.id,
            objective=remaining_objective,
            dependencies=[],
            success_criteria=[],
            required_capabilities=list(
                current_step.required_capabilities
                or []
            ),
            planned_tool=str(
                getattr(
                    current_step,
                    "planned_tool",
                    "",
                )
                or ""
            ).strip(),
            # B8K5 — semantic target intent is step-local.
            #
            # This GoalStep is a synthetic recovery continuation
            # whose objective is the independently resolved
            # remaining_objective, not the original planner
            # objective. It must therefore never inherit the
            # original step's concrete semantic UI target.
            #
            # Trusted GUI authority remains separate below.
            # If this continuation attempts click_vision without
            # receiving a newly planned step-local target intent,
            # the B8 target-verification chain fails closed.
            gui_target_intent=None,
            gui_authority=str(
                getattr(
                    current_step,
                    "gui_authority",
                    "",
                )
                or ""
            ).strip(),
            gui_authority_goal=str(
                getattr(
                    current_step,
                    "gui_authority_goal",
                    "",
                )
                or ""
            ).strip(),
            risk_level=current_step.risk_level,
            artifacts=list(
                current_step.artifacts
                or []
            ),
            verification_requirements=[],
        )

        # Execution-only replay context.
        #
        # Durable authority remains in MissionState.
        continuation_step._continuation_replay_context = {
            "known": bool(
                mission_state.continuation_guard_known
            ),
            "tool": str(
                mission_state.continuation_guard_tool
                or ""
            ),
            "arguments": dict(
                mission_state.continuation_guard_arguments
                or {}
            ),
        }

        # -------------------------------------------------
        # BOUNDED RECOVERY
        # -------------------------------------------------
        #
        # We still use KumaMissionExecutor so ambiguous failures
        # receive recovery diagnosis/state verification.
        #
        # But continuation itself may not automatically RETRY.
        # -------------------------------------------------

        mission_executor = KumaMissionExecutor(
            self.kuma,
            recovery_policy=RecoveryPolicy(
                max_retries=0
            ),
        )

        # -------------------------------------------------
        # DURABLE EXECUTION INTENT
        # -------------------------------------------------
        #
        # Persist BEFORE crossing into tool execution. A restart
        # that sees this barrier must never automatically execute
        # another continuation because the previous process may
        # have died after the real action occurred.
        # -------------------------------------------------

        controller.task_state.mark_continuation_execution_inflight()

        mission_state = (
            MissionState.from_controller(
                controller,
                mission_state,
            )
        )

        mission_state.status = (
            MissionStatus.PAUSED
        )

        mission_state.touch()

        persistence.save(
            mission_state
        )

        execution = mission_executor.execute(
            continuation_step
        )

        # The current process received an outcome. Clear the
        # in-memory barrier and persist the classified state in
        # the outcome branches below.
        controller.task_state.clear_continuation_execution_inflight()

        mission_state = (
            MissionState.from_controller(
                controller,
                mission_state,
            )
        )

        # -------------------------------------------------
        # CONTINUATION CREATED ANOTHER VERIFIED PARTIAL STATE
        # -------------------------------------------------

        if (
            str(
                execution.recovery_action
                or ""
            ).strip().lower()
            == "resume"
            and not execution.completed
        ):

            continuation_evidence = str(
                execution.recovery_evidence
                or ""
            ).strip()

            if not continuation_evidence:

                mission_state.status = (
                    MissionStatus.PAUSED
                )

                mission_state.touch()

                persistence.save(
                    mission_state
                )

                return MissionExecutionResult(
                    success=False,
                    step_id=current_step.id,
                    error=(
                        "Continuation recovery returned "
                        "RESUME without verified evidence."
                    ),
                    verified=False,
                    recovery_action="escalate",
                    recovery_reason=(
                        "Continuation partial state could "
                        "not be safely preserved."
                    ),
                )

            preserved = (
                controller
                .preserve_current_step_for_resume(
                    reason=execution.recovery_reason,
                    evidence=continuation_evidence,
                    tool_name=execution.tool_name,
                    arguments=execution.arguments,
                    capability=execution.capability,
                )
            )

            if not preserved:

                mission_state.status = (
                    MissionStatus.PAUSED
                )

                mission_state.touch()

                persistence.save(
                    mission_state
                )

                return MissionExecutionResult(
                    success=False,
                    step_id=current_step.id,
                    error=(
                        "Continuation partial state "
                        "could not be preserved."
                    ),
                    verified=False,
                    recovery_action="escalate",
                    recovery_reason=(
                        "Mission-state preservation failed."
                    ),
                )

            mission_state = (
                MissionState.from_controller(
                    controller,
                    mission_state,
                )
            )

            mission_state.status = (
                MissionStatus.PAUSED
            )

            mission_state.touch()

            persistence.save(
                mission_state
            )

            return execution

        # -------------------------------------------------
        # CONTINUATION FAILED / WAS BLOCKED
        # -------------------------------------------------
        #
        # Do NOT fail the original GoalStep here.
        # Keep the mission paused.
        # -------------------------------------------------

        if not execution.completed:

            if not str(
                execution.recovery_action
                or ""
            ).strip():

                execution.recovery_action = (
                    "escalate"
                )

                execution.recovery_reason = (
                    execution.error
                    or (
                        "Continuation could not "
                        "advance safely."
                    )
                )

            mission_state = (
                MissionState.from_controller(
                    controller,
                    mission_state,
                )
            )

            mission_state.status = (
                MissionStatus.PAUSED
            )

            mission_state.touch()

            persistence.save(
                mission_state
            )

            return execution

        # -------------------------------------------------
        # VERIFIED CONTINUATION ACTION
        # -------------------------------------------------
        #
        # IMPORTANT:
        #
        # Tool-level success proves only that this continuation
        # action occurred successfully.
        #
        # It does NOT prove the ORIGINAL GoalStep is complete.
        #
        # 6B.6D owns original-objective verification.
        # -------------------------------------------------

        controller.task_state.record_action(
            tool_name=execution.tool_name,
            arguments=(
                execution.arguments
                or {}
            ),
            result=execution.result,
            verified=True,
        )

        controller.task_state.set_continuation_guard_action(
            tool_name=execution.tool_name,
            arguments=(
                execution.arguments
                or {}
            ),
            capability=execution.capability,
        )

        controller.task_state.clear_remaining_objective()

        controller.task_state.mark_continuation_verification_pending()

        controller.task_state.add_observation(
            "Recovery continuation action verified; "
            "original mission-step objective now requires "
            "independent verification."
        )

        mission_state = (
            MissionState.from_controller(
                controller,
                mission_state,
            )
        )

        mission_state.status = (
            MissionStatus.PAUSED
        )

        mission_state.touch()

        persistence.save(
            mission_state
        )

        continuation_evidence = str(
            execution.result
            if execution.result is not None
            else execution.verification
        ).strip()

        return MissionExecutionResult(
            success=True,
            step_id=current_step.id,
            capability=execution.capability,
            tool_name=execution.tool_name,
            arguments=execution.arguments,
            result=execution.result,
            error="",
            verified=False,
            verification=(
                "Continuation action passed tool-level "
                "verification. The original GoalStep remains "
                "IN_PROGRESS pending independent verification."
            ),
            recovery_action="resume",
            recovery_reason=(
                "Verified continuation is awaiting "
                "post-continuation objective verification."
            ),
            recovery_evidence=(
                continuation_evidence
            ),
        )


    def resume_mission(
        self,
        mission_id: str,
    ) -> MissionExecutionResult:
        """
        Resume a persisted KUMA mission.

        Resume uses the exact persisted GoalPlan. It never
        re-decomposes the original goal.

        Automatic resume is allowed only for missions that are
        currently RUNNING or PAUSED.

        Completed, failed, and blocked missions are not silently
        retried.
        """

        mission_id = str(
            mission_id or ""
        ).strip()

        if not mission_id:
            return MissionExecutionResult(
                success=False,
                step_id="",
                error="Mission ID cannot be empty.",
            )

        persistence = MissionPersistence()

        mission_state = persistence.load(
            mission_id
        )

        if mission_state is None:
            return MissionExecutionResult(
                success=False,
                step_id="",
                error=(
                    f"Mission not found: {mission_id}"
                ),
            )

        print(
            "\nKUMA MISSION → Resuming mission"
        )

        print(
            f"KUMA MISSION ID → {mission_state.mission_id}"
        )

        print(
            f"KUMA MISSION GOAL → {mission_state.goal}"
        )

        print(
            f"KUMA MISSION STATUS → "
            f"{mission_state.status.value}"
        )

        # -------------------------------------------------
        # TERMINAL STATES
        # -------------------------------------------------

        if mission_state.status == MissionStatus.COMPLETED:

            return MissionExecutionResult(
                success=True,
                step_id="",
                result=(
                    mission_state.final_result
                    or {
                        "mission_id": mission_state.mission_id,
                        "status": "completed",
                    }
                ),
                verified=True,
                verification=(
                    "Persisted mission is already complete."
                ),
            )

        if mission_state.status == MissionStatus.FAILED:

            return MissionExecutionResult(
                success=False,
                step_id=(
                    mission_state.current_step_id
                    or ""
                ),
                error=(
                    "Mission previously failed and requires "
                    "explicit retry handling."
                ),
            )

        if mission_state.status == MissionStatus.BLOCKED:

            return MissionExecutionResult(
                success=False,
                step_id=(
                    mission_state.current_step_id
                    or ""
                ),
                error=(
                    "Mission is blocked and cannot be "
                    "automatically resumed."
                ),
            )

        if mission_state.plan is None:

            return MissionExecutionResult(
                success=False,
                step_id="",
                error=(
                    "Persisted mission has no GoalPlan."
                ),
            )

        # -------------------------------------------------
        # RESTORE CONTROLLER
        # -------------------------------------------------

        try:

            controller = (
                MissionController
                .from_mission_state(
                    mission_state
                )
            )

        except Exception as error:

            return MissionExecutionResult(
                success=False,
                step_id="",
                error=(
                    "Could not restore mission controller: "
                    f"{error}"
                ),
            )

        # -------------------------------------------------
        # RE-DERIVE GUI ACTION-CLASS AUTHORITY
        # -------------------------------------------------
        #
        # Persisted GoalPlan structure may be resumed, but GUI
        # authority is trusted runtime metadata and is never
        # trusted from persistence. GoalStep deserialization drops
        # legacy/tampered authority fields. Re-bind every GUI
        # action class from the original mission goal before any
        # resumed execution or continuation may occur.
        #
        # Explicit action classes are re-derived automatically.
        # Planner-expanded GUI action classes require fresh,
        # fail-closed confirmation after restart. This confirmation
        # still does not approve eventual tool execution.
        # -------------------------------------------------

        resume_authority_production = (
            RUNTIME_GUI_STEP_AUTHORITY_PRODUCER.authorize_plan(
                goal=mission_state.goal,
                plan=controller.plan,
                confirmation_fn=(
                    self.kuma.request_confirmation
                ),
            )
        )

        resume_authority_decision = (
            resume_authority_production.decision
        )

        if not resume_authority_decision.allowed:

            authority_error = (
                "Persisted mission GUI authority could not be "
                "re-established: "
                f"{resume_authority_decision.reason}"
            )

            print(
                "KUMA MISSION → Resume GUI authority rejected."
            )

            return MissionExecutionResult(
                success=False,
                step_id=(
                    controller.plan.current_step_id
                    if controller.plan is not None
                    else ""
                ),
                error=authority_error,
                verified=False,
                recovery_action="escalate",
                recovery_reason=authority_error,
            )

        # -------------------------------------------------
        # PERSISTED RESUMABLE PARTIAL STATE
        # -------------------------------------------------
        #
        # A PAUSED mission with an IN_PROGRESS step represents
        # verified partial reality.
        #
        # The old operation is never automatically replayed.
        # Instead, derive only the unfinished remainder.
        # -------------------------------------------------

        current_step = (
            controller.current_step()
        )

        if (
            mission_state.status
            == MissionStatus.PAUSED
            and current_step is not None
            and getattr(
                current_step.status,
                "value",
                "",
            )
            == "in_progress"
        ):

            evidence = str(
                mission_state.last_evidence
                or ""
            ).strip()

            if not evidence:

                return MissionExecutionResult(
                    success=False,
                    step_id=current_step.id,
                    error=(
                        "Persisted in-progress step lacks "
                        "verified resume evidence."
                    ),
                    verified=False,
                    recovery_action="escalate",
                    recovery_reason=(
                        "Automatic replay was prevented because "
                        "the partial state could not be verified."
                    ),
                )

            # -------------------------------------------------
            # IN-FLIGHT CONTINUATION CRASH BARRIER
            # -------------------------------------------------
            #
            # A previous process persisted execution intent but
            # did not durably classify the outcome. The real tool
            # action may or may not already have happened.
            # -------------------------------------------------

            if bool(
                getattr(
                    mission_state,
                    "continuation_execution_inflight",
                    False,
                )
            ):

                reason = (
                    "A previous continuation execution was "
                    "interrupted before its outcome was durably "
                    "classified. Automatic continuation replay "
                    "is disabled because external state may "
                    "already have changed."
                )

                print(
                    "KUMA MISSION → "
                    "Unresolved in-flight continuation detected."
                )

                print(
                    "KUMA MISSION → "
                    "No continuation action executed."
                )

                return MissionExecutionResult(
                    success=False,
                    step_id=current_step.id,
                    result=evidence,
                    error=reason,
                    verified=False,
                    recovery_action="escalate",
                    recovery_reason=reason,
                    recovery_evidence=evidence,
                )

            # -------------------------------------------------
            # POST-CONTINUATION VERIFICATION BARRIER
            # -------------------------------------------------
            #
            # One verified continuation already happened.
            #
            # Never execute another continuation until 6B.6D
            # evaluates the original GoalStep.
            # -------------------------------------------------

            if bool(
                getattr(
                    mission_state,
                    "continuation_verification_pending",
                    False,
                )
            ):

                print(
                    "KUMA MISSION → "
                    "Running read-only post-continuation "
                    "objective verification."
                )

                return self._verify_post_continuation_objective(
                    controller=controller,
                    mission_state=mission_state,
                    persistence=persistence,
                    current_step=current_step,
                )

            persisted_remaining_objective = str(
                getattr(
                    mission_state,
                    "remaining_objective",
                    "",
                )
                or ""
            ).strip()

            if persisted_remaining_objective:

                recovery_cycles = int(
                    getattr(
                        mission_state,
                        "recovery_continuation_cycles",
                        0,
                    )
                )

                if (
                    recovery_cycles
                    >= MAX_RECOVERY_CONTINUATION_CYCLES
                ):

                    reason = (
                        "Automatic recovery continuation budget "
                        "is exhausted for the current GoalStep."
                    )

                    print(
                        "KUMA MISSION → "
                        "Recovery livelock guard blocked another "
                        "continuation action."
                    )

                    return MissionExecutionResult(
                        success=False,
                        step_id=current_step.id,
                        result=evidence,
                        error=reason,
                        verified=False,
                        recovery_action="escalate",
                        recovery_reason=reason,
                        recovery_evidence=evidence,
                    )

                print(
                    "KUMA MISSION → "
                    "Executing one replay-safe "
                    "continuation action."
                )

                return self._execute_resumed_continuation(
                    controller=controller,
                    mission_state=mission_state,
                    persistence=persistence,
                    current_step=current_step,
                    remaining_objective=(
                        persisted_remaining_objective
                    ),
                )

            else:

                resolver = RemainingObjectiveResolver(
                    model_call=(
                        self.kuma.call_goal_decision_model
                    )
                )

                resolution = resolver.resolve(
                    step=current_step,
                    evidence=evidence,
                    recovery_reason=(
                        current_step.reason
                    ),
                )

                if not resolution.known:

                    mission_state.status = (
                        MissionStatus.PAUSED
                    )

                    mission_state.remaining_objective = ""

                    mission_state.touch()

                    persistence.save(
                        mission_state
                    )

                    print(
                        "KUMA MISSION → "
                        "Remaining objective is uncertain; "
                        "mission remains paused."
                    )

                    return MissionExecutionResult(
                        success=False,
                        step_id=current_step.id,
                        result=evidence,
                        error=(
                            "KUMA could not safely determine "
                            "the unfinished remainder of the "
                            "partial mission step."
                        ),
                        verified=False,
                        verification=(
                            "Verified partial state was preserved, "
                            "but the continuation objective remains "
                            "unknown."
                        ),
                        recovery_action="escalate",
                        recovery_reason=(
                            resolution.reason
                        ),
                        recovery_evidence=evidence,
                    )

                remaining_objective = (
                    resolution.remaining_objective
                )

                resolution_reason = (
                    resolution.reason
                )

                controller.task_state.set_remaining_objective(
                    remaining_objective
                )

                # Persist the refined continuation state without
                # changing the mission into RUNNING execution.
                mission_state = (
                    MissionState.from_controller(
                        controller,
                        mission_state,
                    )
                )

                mission_state.status = (
                    MissionStatus.PAUSED
                )

                mission_state.touch()

                persistence.save(
                    mission_state
                )

            print(
                "KUMA MISSION → "
                "Verified partial state preserved."
            )

            print(
                "KUMA MISSION REMAINING OBJECTIVE → "
                f"{remaining_objective}"
            )

            print(
                "KUMA MISSION → "
                "No continuation action executed."
            )

            return MissionExecutionResult(
                success=True,
                step_id=current_step.id,
                result=remaining_objective,
                verified=False,
                verification=(
                    "Remaining objective was derived from "
                    "verified partial state. No continuation "
                    "action was executed."
                ),
                recovery_action="resume",
                recovery_reason=(
                    resolution_reason
                ),
                recovery_evidence=evidence,
            )

        # A resumed mission is active again.
        mission_state.status = (
            MissionStatus.RUNNING
        )

        mission_state.current_step_id = (
            controller.plan.current_step_id
            if controller.plan is not None
            else ""
        )

        mission_state.touch()

        persistence.save(
            mission_state
        )

        # -------------------------------------------------
        # EXECUTOR
        # -------------------------------------------------

        mission_executor = (
            KumaMissionExecutor(
                self.kuma
            )
        )

        # -------------------------------------------------
        # PERSISTENCE CALLBACK
        # -------------------------------------------------

        def persist_state(
            controller,
        ):
            nonlocal mission_state

            mission_state = (
                MissionState.from_controller(
                    controller,
                    mission_state,
                )
            )

            persistence.save(
                mission_state
            )

        # -------------------------------------------------
        # RUNNER
        # -------------------------------------------------

        runner = MissionRunner(
            controller=controller,
            execute_step=(
                mission_executor.execute
            ),
            on_state_change=persist_state,
        )

        result = runner.run_mission()

        # -------------------------------------------------
        # FINAL SNAPSHOT
        # -------------------------------------------------

        mission_state = (
            MissionState.from_controller(
                controller,
                mission_state,
            )
        )

        if controller.is_complete():

            mission_state.mark_completed(
                result=result.result
            )

        elif (
            str(
                result.recovery_action
                or ""
            ).strip().lower()
            == "resume"
        ):

            mission_state.status = (
                MissionStatus.PAUSED
            )

            mission_state.touch()

        elif not result.success:

            mission_state.status = (
                MissionStatus.FAILED
            )

            mission_state.touch()

        else:

            mission_state.status = (
                MissionStatus.PAUSED
            )

            mission_state.touch()

        persistence.save(
            mission_state
        )

        # -------------------------------------------------
        # FINAL STATUS
        # -------------------------------------------------

        if controller.is_complete():

            print(
                "\nKUMA MISSION → RESUME COMPLETE"
            )

        else:

            print(
                "\nKUMA MISSION → RESUME STOPPED"
            )

        print(
            controller.summary()
        )

        return result
