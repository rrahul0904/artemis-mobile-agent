from __future__ import annotations
import base64, os, re, subprocess, time
from pathlib import Path
from typing import Protocol
from .models import Action, ActionResult, DeviceInfo, Observation
from .ui import denormalized, parse_elements

class DeviceBackend(Protocol):
    def list_devices(self) -> list[DeviceInfo]: ...
    def observe(self, serial: str, artifact_dir: Path, step: int) -> Observation: ...
    def execute(self, serial: str, action: Action, observation: Observation) -> ActionResult: ...
    def logcat(self, serial: str, lines: int = 200) -> str: ...

class AdbBackend:
    def __init__(self, adb_bin: str | None = None):
        self.adb = adb_bin or os.getenv("ADB_BIN", "adb")
    def _run(self, *args: str, timeout: float = 20, binary: bool = False):
        p = subprocess.run([self.adb, *args], capture_output=True, timeout=timeout, check=False)
        if binary:
            return p
        return p.returncode, p.stdout.decode(errors="replace"), p.stderr.decode(errors="replace")
    def _serial(self, serial: str, *args: str):
        return self._run("-s", serial, *args)
    def list_devices(self) -> list[DeviceInfo]:
        try:
            rc, out, _ = self._run("devices", "-l")
        except (FileNotFoundError, subprocess.SubprocessError):
            return []
        if rc:
            return []
        result = []
        for line in out.splitlines()[1:]:
            if not line.strip():
                continue
            parts = line.split()
            serial = parts[0]
            state = parts[1] if len(parts) > 1 else "unknown"
            model = next((p.split(":", 1)[1] for p in parts if p.startswith("model:")), None)
            result.append(DeviceInfo(serial=serial, state=state, model=model))
        return result
    def observe(self, serial: str, artifact_dir: Path, step: int) -> Observation:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        shot = artifact_dir / f"step-{step:03d}.png"
        xmlp = artifact_dir / f"step-{step:03d}.xml"
        p = self._run("-s", serial, "exec-out", "screencap", "-p", binary=True)
        if p.returncode == 0:
            shot.write_bytes(p.stdout)
        self._serial(serial, "shell", "uiautomator", "dump", "/sdcard/window.xml")
        rc, out, _ = self._serial(serial, "exec-out", "cat", "/sdcard/window.xml")
        xml = out if rc == 0 else ""
        xmlp.write_text(xml, encoding="utf-8")
        _, size, _ = self._serial(serial, "shell", "wm", "size")
        m = re.search(r"(\d+)x(\d+)", size)
        width, height = (int(m.group(1)), int(m.group(2))) if m else (1080, 2400)
        _, activity, _ = self._serial(serial, "shell", "dumpsys", "window", "windows")
        current = next((ln.strip() for ln in activity.splitlines() if "mCurrentFocus" in ln or "mFocusedApp" in ln), None)
        return Observation(screenshot_path=str(shot) if shot.exists() else None, hierarchy_path=str(xmlp), hierarchy_xml=xml, elements=parse_elements(xml), width=width, height=height, activity=current)
    def execute(self, serial: str, action: Action, observation: Observation) -> ActionResult:
        try:
            if action.type == "click":
                if action.target_index is not None:
                    try:
                        px = observation.elements[action.target_index].center
                    except IndexError:
                        return ActionResult(ok=False, message="target index is no longer visible")
                elif action.target:
                    px = denormalized(action.target, observation.width, observation.height)
                else:
                    return ActionResult(ok=False, message="click requires a target")
                rc, out, err = self._serial(serial, "shell", "input", "tap", str(px[0]), str(px[1]))
                return ActionResult(ok=rc == 0, message=f"tap {px}", stdout=out, stderr=err)
            if action.type == "long_press":
                px = observation.elements[action.target_index].center if action.target_index is not None else denormalized(action.target or (500, 500), observation.width, observation.height)
                rc, out, err = self._serial(serial, "shell", "input", "swipe", str(px[0]), str(px[1]), str(px[0]), str(px[1]), str(action.duration_ms))
                return ActionResult(ok=rc == 0, message="long press", stdout=out, stderr=err)
            if action.type == "input_text":
                text = (action.text or "").replace(" ", "%s")
                rc, out, err = self._serial(serial, "shell", "input", "text", text)
                return ActionResult(ok=rc == 0, message="text input", stdout=out, stderr=err)
            if action.type == "swipe":
                w, h = observation.width, observation.height
                d = (action.direction or "up").lower()
                coords = {
                    "up": (w // 2, int(h * .75), w // 2, int(h * .25)),
                    "down": (w // 2, int(h * .25), w // 2, int(h * .75)),
                    "left": (int(w * .8), h // 2, int(w * .2), h // 2),
                    "right": (int(w * .2), h // 2, int(w * .8), h // 2),
                }.get(d)
                if not coords:
                    return ActionResult(ok=False, message=f"unsupported swipe direction {d}")
                rc, out, err = self._serial(serial, "shell", "input", "swipe", *map(str, coords), str(action.duration_ms))
                return ActionResult(ok=rc == 0, message=f"swipe {d}", stdout=out, stderr=err)
            if action.type == "press_key":
                rc, out, err = self._serial(serial, "shell", "input", "keyevent", action.key or "KEYCODE_BACK")
                return ActionResult(ok=rc == 0, message="key event", stdout=out, stderr=err)
            if action.type == "launch_app":
                rc, out, err = self._serial(serial, "shell", "monkey", "-p", action.package or "com.android.settings", "-c", "android.intent.category.LAUNCHER", "1")
                return ActionResult(ok=rc == 0, message="app launch", stdout=out, stderr=err)
            if action.type == "install_apk":
                rc, out, err = self._run("-s", serial, "install", "-r", action.apk_path or "")
                return ActionResult(ok=rc == 0, message="apk install", stdout=out, stderr=err)
            if action.type == "open_link":
                rc, out, err = self._serial(serial, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", action.url or "")
                return ActionResult(ok=rc == 0, message="open link", stdout=out, stderr=err)
            if action.type == "wait":
                time.sleep(action.delay_ms / 1000)
                return ActionResult(ok=True, message=f"waited {action.delay_ms}ms")
            if action.type == "finish":
                return ActionResult(ok=bool(action.success), message=action.message or "finished")
            return ActionResult(ok=False, message=f"unsupported action {action.type}")
        except Exception as e:
            return ActionResult(ok=False, message=str(e), stderr=repr(e))
    def logcat(self, serial: str, lines: int = 200) -> str:
        rc, out, err = self._serial(serial, "logcat", "-d", "-t", str(lines))
        return out if rc == 0 else err

_TINY_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/AwMDEwMDAwMDAwAkBgMB/DXemwAAAABJRU5ErkJggg==")

class FakeBackend:
    def __init__(self):
        self.screen = {"fake-android-001": "settings"}
        self.actions: list[dict] = []
    def list_devices(self) -> list[DeviceInfo]:
        return [DeviceInfo(serial="fake-android-001", state="device", model="Pixel_Fake", transport="fake")]
    def _xml(self, state: str) -> str:
        if state == "battery":
            return '<hierarchy><node text="Battery" resource-id="title" class="android.widget.TextView" bounds="[40,80][500,180]"/><node text="87%" resource-id="battery_percentage" class="android.widget.TextView" bounds="[40,240][300,340]"/></hierarchy>'
        return '<hierarchy><node text="Settings" resource-id="title" class="android.widget.TextView" bounds="[40,80][500,180]"/><node text="Network &amp; internet" resource-id="network" class="android.widget.TextView" clickable="true" bounds="[40,300][900,430]"/><node text="Battery" resource-id="battery" class="android.widget.TextView" clickable="true" bounds="[40,480][900,610]"/></hierarchy>'
    def observe(self, serial: str, artifact_dir: Path, step: int) -> Observation:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        state = self.screen.get(serial, "settings")
        xml = self._xml(state)
        shot = artifact_dir / f"step-{step:03d}.png"
        shot.write_bytes(_TINY_PNG)
        xmlp = artifact_dir / f"step-{step:03d}.xml"
        xmlp.write_text(xml, encoding="utf-8")
        return Observation(screenshot_path=str(shot), hierarchy_path=str(xmlp), hierarchy_xml=xml, elements=parse_elements(xml), width=1080, height=2400, activity=f"fake/{state}")
    def execute(self, serial: str, action: Action, observation: Observation) -> ActionResult:
        self.actions.append(action.model_dump())
        if action.type == "click":
            el = observation.elements[action.target_index] if action.target_index is not None and action.target_index < len(observation.elements) else None
            if el and "battery" in (el.text + el.resource_id).lower():
                self.screen[serial] = "battery"
                return ActionResult(ok=True, message="opened Battery")
            return ActionResult(ok=True, message="fake click")
        if action.type == "launch_app":
            self.screen[serial] = "settings"
            return ActionResult(ok=True, message="fake app launch")
        if action.type == "finish":
            return ActionResult(ok=bool(action.success), message=action.message or "finished")
        return ActionResult(ok=True, message=f"fake {action.type}")
    def logcat(self, serial: str, lines: int = 200) -> str:
        return "I/FakeDevice: healthy"

def make_backend() -> DeviceBackend:
    return FakeBackend() if os.getenv("ARTEMIS_FAKE_DEVICE", "0").lower() in {"1", "true", "yes"} else AdbBackend()
