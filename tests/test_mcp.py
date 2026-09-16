from artemis_mobile_agent import mcp_tools
from artemis_mobile_agent.devices import FakeBackend
from artemis_mobile_agent.engine import Engine
from artemis_mobile_agent.planner import HeuristicPlanner
from artemis_mobile_agent.store import TraceStore

def test_mcp_facade(tmp_path, monkeypatch):
    e = Engine(FakeBackend(), HeuristicPlanner(), TraceStore(tmp_path / "t"))
    monkeypatch.setattr(mcp_tools, "_engine", lambda: e)
    x = mcp_tools.mobile_run_task("Open Settings, go to Battery and verify battery percentage")
    assert x["trace_id"]
    e.wait(x["trace_id"])
    status = mcp_tools.mobile_manage_task("status", x["trace_id"])
    assert status["status"] == "succeeded"
    assert mcp_tools.mobile_get_device_state()["devices"]
    assert mcp_tools.mobile_inspect_trace(x["trace_id"])["steps"]
