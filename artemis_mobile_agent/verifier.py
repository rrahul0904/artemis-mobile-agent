from __future__ import annotations
import base64, os
from pathlib import Path
import httpx
from .models import Observation

class Verifier:
    def verify(self, goal: str, observation: Observation, expected_output: str | None = None) -> tuple[bool, str]:
        raise NotImplementedError

class HeuristicVerifier(Verifier):
    def verify(self, goal: str, observation: Observation, expected_output: str | None = None) -> tuple[bool, str]:
        visible = " ".join(filter(None, [e.text for e in observation.elements] + [e.content_desc for e in observation.elements])).lower()
        low = goal.lower()
        if expected_output:
            ok = expected_output.lower() in visible
            return ok, f"expected output {'visible' if ok else 'not visible'}: {expected_output}"
        if "battery" in low and ("percentage" in low or "level" in low):
            pct = next((e.text for e in observation.elements if "%" in e.text), None)
            return (pct is not None, f"battery evidence: {pct}" if pct else "battery percentage is not visible")
        if "verify" in low:
            tail = low.split("verify", 1)[1].strip(" :.-")
            meaningful = [t.strip(".,:;!?()[]") for t in tail.split() if len(t) > 2 and t not in {"the", "that", "and", "visible", "appears", "screen"}]
            hits = [t for t in meaningful if t in visible]
            return (bool(hits), f"visible verification tokens: {hits}" if hits else "no requested verification token is visible")
        return True, "no explicit terminal assertion; action result accepted"

class RemoteVerifier(Verifier):
    def __init__(self, url: str, token: str | None = None, timeout: float = 45):
        self.url, self.token, self.timeout = url, token, timeout
    def verify(self, goal: str, observation: Observation, expected_output: str | None = None) -> tuple[bool, str]:
        image = None
        if observation.screenshot_path and Path(observation.screenshot_path).exists():
            image = base64.b64encode(Path(observation.screenshot_path).read_bytes()).decode()
        payload = {"goal": goal, "expected_output": expected_output, "activity": observation.activity, "elements": [e.model_dump() for e in observation.elements], "screenshot_base64": image}
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        r = httpx.post(self.url, json=payload, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        return bool(data.get("success")), str(data.get("reason", "remote verifier"))

def make_verifier() -> Verifier:
    url = os.getenv("ARTEMIS_VERIFIER_URL")
    return RemoteVerifier(url, os.getenv("ARTEMIS_VERIFIER_TOKEN")) if url else HeuristicVerifier()
