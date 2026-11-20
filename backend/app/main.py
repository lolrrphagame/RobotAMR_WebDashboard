import asyncio
import json
import os
import time
from contextlib import asynccontextmanager, suppress
from uuid import uuid4
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from .models import ControlCommand
from .simulator import RobotSimulator

@asynccontextmanager
async def lifespan(app):
    app.state.robot = RobotSimulator()
    async def simulate():
        previous = time.monotonic()
        while True:
            await asyncio.sleep(0.1)
            now = time.monotonic()
            app.state.robot.tick(min(now - previous, 0.25))
            previous = now
    task = asyncio.create_task(simulate())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    app.state.robot.stop("Service shutdown")

app = FastAPI(title="PBL4 AMR Simulation API", lifespan=lifespan)
origins = os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=["*"])

@app.get("/api/health")
def health():
    return {"status": "ok", "simulation": True, "hardware_enabled": False}

@app.get("/api/robot/status")
def status():
    return app.state.robot.snapshot()

@app.websocket("/ws/telemetry")
async def telemetry(socket: WebSocket):
    if socket.headers.get("origin") not in origins and socket.headers.get("origin") is not None:
        await socket.close(code=1008)
        return
    await socket.accept()
    robot = app.state.robot
    client = str(uuid4())
    async def receive():
        while True:
            try:
                raw = await socket.receive_text()
                if len(raw) > 2048:
                    raise ValueError("Command too large")
                command = ControlCommand.model_validate(json.loads(raw))
                if not robot.command(command, client):
                    await socket.send_json({"type": "error", "message": "Another simulation client holds control."})
            except (ValidationError, ValueError, json.JSONDecodeError):
                robot.disconnect(client)
                await socket.send_json({"type": "error", "message": "Invalid control command. Controller commands cleared."})
    async def send():
        while True:
            await socket.send_json(robot.snapshot())
            await asyncio.sleep(0.1)
    tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        robot.disconnect(client)
