from __future__ import annotations
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field

class Profile(str, Enum):
    FLASH = "flash"
    PRO = "pro"

class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

class DeviceInfo(BaseModel):
    serial: str
    state: str = "device"
    model: str | None = None
    transport: str = "adb"

class UIElement(BaseModel):
    index: int
    text: str = ""
    resource_id: str = ""
    class_name: str = ""
    content_desc: str = ""
    bounds: tuple[int, int, int, int]
    @property
    def center(self) -> tuple[int, int]:
        l, t, r, b = self.bounds
        return ((l + r) // 2, (t + b) // 2)

class Observation(BaseModel):
    screenshot_path: str | None = None
    hierarchy_path: str | None = None
    hierarchy_xml: str = ""
    elements: list[UIElement] = Field(default_factory=list)
    width: int = 1080
    height: int = 2400
    activity: str | None = None

class Action(BaseModel):
    type: Literal["click", "long_press", "input_text", "swipe", "press_key", "launch_app", "install_apk", "open_link", "wait", "finish"]
    target_index: int | None = None
    target: tuple[int, int] | None = None
    target_description: str | None = None
    text: str | None = None
    package: str | None = None
    apk_path: str | None = None
    url: str | None = None
    key: str | None = None
    direction: str | None = None
    duration_ms: int = 300
    delay_ms: int = 750
    success: bool | None = None
    message: str | None = None

class ActionResult(BaseModel):
    ok: bool
    message: str = ""
    stdout: str = ""
    stderr: str = ""

class StepRecord(BaseModel):
    number: int
    thought: str
    action: Action
    result: ActionResult
    before: Observation
    after: Observation | None = None
    verification: str | None = None

class RunRequest(BaseModel):
    goal: str = Field(min_length=3)
    profile: Profile = Profile.FLASH
    device_serial: str | None = None
    max_steps: int = Field(default=20, ge=1, le=100)
    expected_output: str | None = None
    locked_app_package: str | None = None
    app_path: str | None = None
    verification_level: Literal["off", "final", "checkpoints", "strict"] = "final"
    explorer_mode: Literal["flash", "pro", "ultra"] = "flash"
    record_video: bool = False

class RunRecord(BaseModel):
    id: str
    goal: str
    profile: Profile
    status: RunStatus
    device_serial: str | None = None
    created_at: float
    updated_at: float
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    steps: int = 0

class ManageRequest(BaseModel):
    action: Literal["cancel", "pause", "resume"]
