from __future__ import annotations
import base64, os
from pathlib import Path
from dataclasses import dataclass
import httpx
from .models import Action, Observation, Profile

@dataclass
class Decision:
    thought: str
    action: Action

class Planner:
    def decide(self, goal: str, profile: Profile, observation: Observation, history: list[dict]) -> Decision:
        raise NotImplementedError

class HeuristicPlanner(Planner):
    def decide(self, goal: str, profile: Profile, observation: Observation, history: list[dict]) -> Decision:
        low = goal.lower()
        visible = [f"{e.text} {e.content_desc} {e.resource_id}".lower() for e in observation.elements]
        if "battery" in low and any("%" in e.text for e in observation.elements):
            pct = next(e.text for e in observation.elements if "%" in e.text)
            return Decision(f"Battery percentage {pct} is visible; goal is verified.", Action(type="finish", success=True, message=f"Battery percentage visible: {pct}"))
        stop = {"open", "go", "to", "and", "the", "verify", "visible", "navigate", "find", "tell", "me", "current", "level", "percentage", "is", "in", "settings"}
        tokens = [t.strip(".,:;!?()[]").lower() for t in low.split() if len(t) > 2 and t not in stop]
        scored = []
        for e, txt in zip(observation.elements, visible):
            score = sum(1 for t in tokens if t in txt)
            if score:
                scored.append((score, e))
        if scored:
            scored.sort(key=lambda x: (-x[0], x[1].index))
            e = scored[0][1]
            return Decision(f"Visible element #{e.index} matches goal tokens: {e.text or e.content_desc or e.resource_id}", Action(type="click", target_index=e.index, target_description=e.text or e.content_desc or e.resource_id))
        if not history and "settings" in low:
            return Decision("Launch Android Settings as the task entry point.", Action(type="launch_app", package="com.android.settings"))
        if len(history) < 2:
            return Decision("No direct target is visible; scroll down once and re-observe.", Action(type="swipe", direction="up"))
        return Decision("No evidence-backed route remains in the deterministic planner.", Action(type="finish", success=False, message="No matching visible target; configure ARTEMIS_PLANNER_URL for model planning."))

class RemotePlanner(Planner):
    """Provider-neutral bridge. POSTs state to ARTEMIS_PLANNER_URL and expects {thought, action}."""
    def __init__(self, url: str, token: str | None = None, timeout: float = 45):
        self.url, self.token, self.timeout = url, token, timeout
    def decide(self, goal: str, profile: Profile, observation: Observation, history: list[dict]) -> Decision:
        payload = {
            "goal": goal,
            "profile": profile.value,
            "observation": {
                "activity": observation.activity,
                "width": observation.width,
                "height": observation.height,
                "elements": [e.model_dump() for e in observation.elements],
                "screenshot_path": observation.screenshot_path,
                "screenshot_base64": base64.b64encode(Path(observation.screenshot_path).read_bytes()).decode() if observation.screenshot_path and Path(observation.screenshot_path).exists() else None,
            },
            "history": history[-12:],
        }
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        r = httpx.post(self.url, json=payload, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        return Decision(str(data.get("thought", "remote planner")), Action.model_validate(data["action"]))

def make_planner() -> Planner:
    url = os.getenv("ARTEMIS_PLANNER_URL")
    return RemotePlanner(url, os.getenv("ARTEMIS_PLANNER_TOKEN")) if url else HeuristicPlanner()
