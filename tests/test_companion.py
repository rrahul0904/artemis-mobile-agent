from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from artemis_mobile_agent.companion import CompanionBackend
from artemis_mobile_agent.devices import make_backend
from artemis_mobile_agent.models import Action


_XML = '<hierarchy><node text="Battery" resource-id="battery" class="android.widget.TextView" clickable="true" bounds="[40,480][900,610]"/></hierarchy>'


class _Handler(BaseHTTPRequestHandler):
    last_action = None

    def log_message(self, format, *args):  # pragma: no cover - keep test output clean
        return

    def _json(self, code: int, payload: dict):
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self) -> bool:
        if self.headers.get("Authorization") == "Bearer test-token":
            return True
        self._json(401, {"error": "unauthorized"})
        return False

    def do_GET(self):
        if not self._authorized():
            return
        if self.path == "/v1/device":
            self._json(200, {"device": {"serial": "companion-001", "state": "device", "model": "Pixel Companion"}})
            return
        if self.path.startswith("/v1/logcat"):
            self._json(200, {"text": "I/Companion: healthy"})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._authorized():
            return
        size = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(size) or b"{}")
        if self.path == "/v1/observe":
            self._json(
                200,
                {
                    "hierarchy_xml": _XML,
                    "screenshot_base64": base64.b64encode(b"fake-png").decode(),
                    "width": 1080,
                    "height": 2400,
                    "activity": "com.android.settings/.Settings",
                    "sequence": 7,
                    "digest": "sha256:observation-7",
                },
            )
            return
        if self.path == "/v1/action":
            type(self).last_action = body
            if body.get("observation", {}).get("digest") != "sha256:observation-7":
                self._json(409, {"ok": False, "message": "stale observation"})
                return
            self._json(200, {"ok": True, "message": "tap accepted"})
            return
        self._json(404, {"error": "not found"})


def _server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_companion_roundtrip(tmp_path):
    server = _server()
    try:
        backend = CompanionBackend(f"http://127.0.0.1:{server.server_port}", "test-token")
        devices = backend.list_devices()
        assert len(devices) == 1
        assert devices[0].serial == "companion-001"
        assert devices[0].transport == "companion"

        observation = backend.observe("companion-001", tmp_path, 1)
        assert observation.sequence == 7
        assert observation.digest == "sha256:observation-7"
        assert observation.activity == "com.android.settings/.Settings"
        assert observation.screenshot_path is not None
        assert len(observation.elements) == 1
        assert observation.elements[0].text == "Battery"

        result = backend.execute("companion-001", Action(type="click", target_index=0), observation)
        assert result.ok is True
        assert _Handler.last_action["action"]["type"] == "click"
        assert _Handler.last_action["observation"] == {"sequence": 7, "digest": "sha256:observation-7"}
        assert backend.logcat("companion-001") == "I/Companion: healthy"
    finally:
        server.shutdown()
        server.server_close()


def test_companion_requires_auth():
    server = _server()
    try:
        backend = CompanionBackend(f"http://127.0.0.1:{server.server_port}", "wrong-token")
        assert backend.list_devices() == []
    finally:
        server.shutdown()
        server.server_close()


def test_backend_factory_prefers_explicit_companion(monkeypatch):
    monkeypatch.delenv("ARTEMIS_FAKE_DEVICE", raising=False)
    monkeypatch.setenv("ARTEMIS_COMPANION_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("ARTEMIS_COMPANION_TOKEN", "abc")
    backend = make_backend()
    assert isinstance(backend, CompanionBackend)
    assert backend.base_url == "http://127.0.0.1:9999"
    assert backend.token == "abc"
