from __future__ import annotations

import base64
import os
from pathlib import Path

import httpx

from .models import Action, ActionResult, DeviceInfo, Observation
from .ui import parse_elements


class CompanionBackend:
    """DeviceBackend implementation for an Artemis Android companion.

    The companion is intentionally treated as an executor/observation transport.
    Planning, verification, traces and policy remain in Artemis.
    """

    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 20.0):
        self.base_url = (base_url or os.getenv("ARTEMIS_COMPANION_URL", "http://127.0.0.1:8765")).rstrip("/")
        self.token = token if token is not None else os.getenv("ARTEMIS_COMPANION_TOKEN", "")
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, headers=self._headers(), timeout=self.timeout)

    def list_devices(self) -> list[DeviceInfo]:
        try:
            with self._client() as client:
                response = client.get("/v1/device")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []

        raw = payload.get("device", payload)
        return [
            DeviceInfo(
                serial=str(raw.get("serial") or "companion-local"),
                state=str(raw.get("state") or "device"),
                model=raw.get("model"),
                transport="companion",
            )
        ]

    def observe(self, serial: str, artifact_dir: Path, step: int) -> Observation:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        with self._client() as client:
            response = client.post("/v1/observe", json={"serial": serial, "step": step})
            response.raise_for_status()
            payload = response.json()

        xml = str(payload.get("hierarchy_xml") or "")
        xml_path = artifact_dir / f"step-{step:03d}.xml"
        xml_path.write_text(xml, encoding="utf-8")

        screenshot_path: str | None = None
        screenshot_b64 = payload.get("screenshot_base64")
        if screenshot_b64:
            shot = artifact_dir / f"step-{step:03d}.png"
            shot.write_bytes(base64.b64decode(screenshot_b64, validate=True))
            screenshot_path = str(shot)

        return Observation(
            screenshot_path=screenshot_path,
            hierarchy_path=str(xml_path),
            hierarchy_xml=xml,
            elements=parse_elements(xml),
            width=int(payload.get("width") or 1080),
            height=int(payload.get("height") or 2400),
            activity=payload.get("activity"),
            sequence=int(payload.get("sequence") or 0),
            digest=payload.get("digest"),
        )

    def execute(self, serial: str, action: Action, observation: Observation) -> ActionResult:
        envelope = {
            "serial": serial,
            "action": action.model_dump(exclude_none=True),
            "observation": {
                "sequence": observation.sequence,
                "digest": observation.digest,
            },
        }
        try:
            with self._client() as client:
                response = client.post("/v1/action", json=envelope)
                response.raise_for_status()
                payload = response.json()
            return ActionResult(
                ok=bool(payload.get("ok")),
                message=str(payload.get("message") or ""),
                stdout=str(payload.get("stdout") or ""),
                stderr=str(payload.get("stderr") or ""),
            )
        except (httpx.HTTPError, ValueError) as exc:
            return ActionResult(ok=False, message="companion action failed", stderr=repr(exc))

    def logcat(self, serial: str, lines: int = 200) -> str:
        try:
            with self._client() as client:
                response = client.get("/v1/logcat", params={"serial": serial, "lines": lines})
                response.raise_for_status()
                payload = response.json()
            return str(payload.get("text") or "")
        except (httpx.HTTPError, ValueError) as exc:
            return f"companion logcat unavailable: {exc!r}"
