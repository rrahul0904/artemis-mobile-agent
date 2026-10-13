from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass

from .models import Action, Observation, RiskClass


_OUTWARD = re.compile(r"\b(send|reply|post|publish|share|submit|call|message|email|invite|follow|like)\b", re.I)
_FINANCIAL = re.compile(r"\b(pay|purchase|buy|order|checkout|place order|transfer|send money|subscribe|donate|tip)\b", re.I)
_DESTRUCTIVE = re.compile(r"\b(delete|remove|erase|uninstall|cancel account|close account|factory reset|wipe)\b", re.I)
_SECURITY = re.compile(r"\b(permission|security|password|passcode|pin|two.factor|2fa|accessibility|device admin|vpn|install unknown|allow restricted)\b", re.I)
_ELEVATION = re.compile(r"\b(shell|terminal|developer|root|shizuku|debug|adb|install apk|sideload)\b", re.I)


@dataclass(frozen=True)
class PolicyDecision:
    risk: RiskClass
    approval_required: bool
    reason: str
    target_fingerprint: str


class ActionPolicy:
    """Deterministic, fail-closed policy for device write actions.

    Screen text is treated only as untrusted evidence used to raise risk. It can
    never lower a risk classification or grant a capability.
    """

    def assess(self, action: Action, observation: Observation) -> PolicyDecision:
        target = self._target_text(action, observation)
        fingerprint = self.target_fingerprint(action, observation)

        if action.type == "install_apk":
            return PolicyDecision(RiskClass.CAPABILITY_ELEVATION, True, "installing software requires approval", fingerprint)

        if action.type in {"finish", "wait"}:
            return PolicyDecision(RiskClass.READ_ONLY, False, "no external side effect", fingerprint)

        if _FINANCIAL.search(target):
            return PolicyDecision(RiskClass.FINANCIAL_OR_PURCHASE, True, "financial or purchase commitment", fingerprint)
        if _DESTRUCTIVE.search(target):
            return PolicyDecision(RiskClass.DESTRUCTIVE, True, "destructive action", fingerprint)
        if _SECURITY.search(target):
            return PolicyDecision(RiskClass.SECURITY_OR_PERMISSION_CHANGE, True, "security or permission change", fingerprint)
        if _ELEVATION.search(target):
            return PolicyDecision(RiskClass.CAPABILITY_ELEVATION, True, "capability elevation", fingerprint)
        if _OUTWARD.search(target):
            return PolicyDecision(RiskClass.OUTWARD_FACING, True, "outward-facing action", fingerprint)

        # Typing is reversible until a submit/send action commits it. Launching,
        # navigation, scrolling and local key actions stay in the reversible class.
        return PolicyDecision(RiskClass.REVERSIBLE_LOCAL, False, "reversible local interaction", fingerprint)

    def approval_payload(
        self,
        *,
        run_id: str,
        session_id: str,
        step_id: int,
        action: Action,
        observation: Observation,
        decision: PolicyDecision,
        ttl_seconds: int = 120,
    ) -> dict:
        now = time.time()
        nonce = secrets.token_hex(16)
        envelope = {
            "run_id": run_id,
            "session_id": session_id,
            "step_id": step_id,
            "package_or_activity": observation.activity or "",
            "action": action.model_dump(exclude_none=True),
            "observation_digest": observation.digest or self.observation_digest(observation),
            "target_fingerprint": decision.target_fingerprint,
            "risk": decision.risk.value,
            "reason": decision.reason,
            "nonce": nonce,
            "issued_at": now,
            "expires_at": now + max(1, ttl_seconds),
        }
        envelope["intent_digest"] = self.digest(envelope)
        return envelope

    def validate_binding(self, approval: dict, *, run_id: str, action: Action, observation: Observation) -> tuple[bool, str]:
        if approval.get("run_id") != run_id:
            return False, "approval run mismatch"
        if float(approval.get("expires_at") or 0) < time.time():
            return False, "approval expired"
        if approval.get("status") != "approved":
            return False, "approval is not approved"
        if approval.get("consumed_at"):
            return False, "approval already consumed"

        expected_action = action.model_dump(exclude_none=True)
        if approval.get("action") != expected_action:
            return False, "approval action mismatch"

        current_observation = observation.digest or self.observation_digest(observation)
        if approval.get("observation_digest") != current_observation:
            return False, "approval observation mismatch"

        if approval.get("target_fingerprint") != self.target_fingerprint(action, observation):
            return False, "approval target mismatch"

        check = {k: v for k, v in approval.items() if k not in {"approval_id", "status", "decision_at", "decision_text", "consumed_at"}}
        supplied_digest = check.pop("intent_digest", None)
        if supplied_digest != self.digest(check):
            return False, "approval intent digest mismatch"
        return True, "approval binding valid"

    def _target_text(self, action: Action, observation: Observation) -> str:
        parts = [action.type, action.target_description or "", action.text or "", action.package or "", action.url or ""]
        if action.target_index is not None and 0 <= action.target_index < len(observation.elements):
            element = observation.elements[action.target_index]
            parts.extend([element.text, element.content_desc, element.resource_id, element.class_name])
        return " ".join(p for p in parts if p)

    def target_fingerprint(self, action: Action, observation: Observation) -> str:
        element = None
        if action.target_index is not None and 0 <= action.target_index < len(observation.elements):
            item = observation.elements[action.target_index]
            element = {
                "text": item.text,
                "content_desc": item.content_desc,
                "resource_id": item.resource_id,
                "class_name": item.class_name,
                "bounds": item.bounds,
            }
        return self.digest({
            "activity": observation.activity or "",
            "target_index": action.target_index,
            "target": action.target,
            "target_description": action.target_description,
            "element": element,
        })

    def observation_digest(self, observation: Observation) -> str:
        return self.digest({
            "activity": observation.activity,
            "width": observation.width,
            "height": observation.height,
            "hierarchy_xml": observation.hierarchy_xml,
        })

    @staticmethod
    def digest(value: object) -> str:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        return "sha256:" + hashlib.sha256(raw).hexdigest()
