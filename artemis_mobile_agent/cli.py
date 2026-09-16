from __future__ import annotations
import json
import typer
from .engine import Engine
from .models import Profile, RunRequest

app = typer.Typer(no_args_is_help=True)

@app.command()
def devices():
    """List attached Android devices."""
    typer.echo(json.dumps([d.model_dump() for d in Engine().devices()], indent=2))

@app.command()
def diagnose():
    typer.echo(json.dumps(Engine().diagnose(), indent=2))

@app.command()
def run(goal: str, profile: Profile = Profile.FLASH, device_serial: str | None = None, max_steps: int = 20):
    e = Engine()
    r = e.submit(RunRequest(goal=goal, profile=profile, device_serial=device_serial, max_steps=max_steps))
    r = e.wait(r.id, timeout=300)
    typer.echo(json.dumps(e.trace(r.id), indent=2, default=str))
    raise typer.Exit(0 if r.status.value == "succeeded" else 2)

@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run("artemis_mobile_agent.api:app", host=host, port=port, reload=False)

if __name__ == "__main__":
    app()
