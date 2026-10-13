from __future__ import annotations

import time

from artemis_mobile_agent.devices import FakeBackend
from artemis_mobile_agent.engine import Engine
from artemis_mobile_agent.models import Action, Observation, Profile, RunRequest, UIElement
from artemis_mobile_agent.planner import Decision, Planner
from artemis_mobile_agent.policy import ActionPolicy
from artemis_mobile_agent.store import TraceStore


def _observation(label: str = "Send") -> Observation:
    return Observation(
        hierarchy_xml=f'<hierarchy><node text="{label}" resource-id="action" class="android.widget.Button" clickable="true" bounds="[10,10][200,100]"/></hierarchy>',
        elements=[UIElement(index=0, text=label, resource_id="action", class_name="android.widget.Button", bounds=(10, 10, 200, 100))],
        activity="com.example/.MainActivity",
    )


def test_policy_requires_human_for_outward_financial_and_destructive_actions():
    policy = ActionPolicy()
    assert policy.assess(Action(type="click", target_index=0), _observation("Send")).risk.value == "outward_facing"
    assert policy.assess(Action(type="click", target_index=0), _observation("Place order")).risk.value == "financial_or_purchase"
    assert policy.assess(Action(type="click", target_index=0), _observation("Delete account")).risk.value == "destructive"
    assert policy.assess(Action(type="click", target_index=0), _observation("Battery")).approval_required is False


def test_approval_is_bound_to_exact_action_and_observation():
    policy = ActionPolicy()
    before = _observation("Send")
    action = Action(type="click", target_index=0)
    decision = policy.assess(action, before)
    receipt = policy.approval_payload(run_id="run-1", session_id="session-1", step_id=1, action=action, observation=before, decision=decision)
    receipt.update({"approval_id": "approval-1", "status": "approved"})

    ok, _ = policy.validate_binding(receipt, run_id="run-1", action=action, observation=before)
    assert ok is True

    changed_action = Action(type="click", target=(900, 900))
    ok, reason = policy.validate_binding(receipt, run_id="run-1", action=changed_action, observation=before)
    assert ok is False and "action mismatch" in reason

    changed_screen = _observation("Publish")
    ok, reason = policy.validate_binding(receipt, run_id="run-1", action=action, observation=changed_screen)
    assert ok is False and ("observation mismatch" in reason or "target mismatch" in reason)


class _RiskyPlanner(Planner):
    def decide(self, goal, profile, observation, history):
        if history:
            return Decision("done", Action(type="finish", success=True, message="done"))
        return Decision("send it", Action(type="click", target_index=2, target_description="Send"))


def _pending(engine: Engine, run_id: str, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        item = engine.store.pending_approval(run_id)
        if item:
            return item
        time.sleep(.01)
    raise AssertionError("approval was not requested")


def test_engine_denial_blocks_side_effect_and_records_receipt(tmp_path):
    backend = FakeBackend()
    store = TraceStore(tmp_path)
    engine = Engine(backend=backend, planner=_RiskyPlanner(), store=store)
    run = engine.submit(RunRequest(goal="send a message", profile=Profile.FLASH), background=True)
    approval = _pending(engine, run.id)
    assert approval["risk"] == "outward_facing"
    assert backend.screen[run.device_serial] == "settings"

    engine.resolve_approval(run.id, approval["approval_id"], "deny")
    finished = engine.wait(run.id, 3)
    assert finished.status.value == "succeeded"
    assert backend.screen[run.device_serial] == "settings"
    receipt = store.read_approval(run.id, approval["approval_id"])
    assert receipt["status"] == "denied"
    assert receipt.get("consumed_at") is None
    assert any(e["type"] == "step_blocked" for e in store.read_events(run.id))


def test_engine_approval_is_consumed_once_before_side_effect(tmp_path):
    backend = FakeBackend()
    store = TraceStore(tmp_path)
    engine = Engine(backend=backend, planner=_RiskyPlanner(), store=store)
    run = engine.submit(RunRequest(goal="send a message", profile=Profile.FLASH), background=True)
    approval = _pending(engine, run.id)

    engine.resolve_approval(run.id, approval["approval_id"], "approve")
    finished = engine.wait(run.id, 3)
    assert finished.status.value == "succeeded"
    assert backend.screen[run.device_serial] == "battery"
    receipt = store.read_approval(run.id, approval["approval_id"])
    assert receipt["status"] == "approved"
    assert receipt.get("consumed_at") is not None

    ok, reason = engine.policy.validate_binding(receipt, run_id=run.id, action=Action(type="click", target_index=2, target_description="Send"), observation=backend.observe(run.device_serial, tmp_path / "probe", 99))
    assert ok is False
    assert "consumed" in reason or "observation mismatch" in reason


def test_change_invalidates_old_action_and_informs_next_planner_step(tmp_path):
    backend = FakeBackend()
    store = TraceStore(tmp_path)
    engine = Engine(backend=backend, planner=_RiskyPlanner(), store=store)
    run = engine.submit(RunRequest(goal="send a message", profile=Profile.FLASH), background=True)
    approval = _pending(engine, run.id)

    engine.resolve_approval(run.id, approval["approval_id"], "change", "do not send; save as draft")
    finished = engine.wait(run.id, 3)
    assert finished.status.value == "succeeded"
    assert backend.screen[run.device_serial] == "settings"
    steps = store.read_steps(run.id)
    assert "CHANGES REQUESTED" in steps[0].result.message
    assert "save as draft" in steps[0].result.message
