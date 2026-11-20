"""Pure simulated differential-drive plant; replace via an adapter in a later phase."""
import math
import time
from collections import deque
from datetime import datetime, timezone
from .models import ControlCommand

WHEEL_RADIUS = 0.0435
WHEEL_SEPARATION = 0.300
ENCODER_CPR = 3960
COMMAND_TIMEOUT = 0.6

class RobotSimulator:
    def __init__(self):
        self.started = time.monotonic()
        self.last_command = 0.0
        self.owner = None
        self.linear = self.angular = 0.0
        self.rpm = [0.0, 0.0]
        self.counts = [0.0, 0.0]
        self.events = deque(maxlen=60)
        self.event_id = 0
        self.log("info", "Simulation initialized. Hardware interfaces disabled.")

    def log(self, level, message):
        self.event_id += 1
        self.events.appendleft({"id": self.event_id, "time": datetime.now(timezone.utc).isoformat(), "level": level, "message": message})

    def stop(self, reason="Stop command received"):
        active = self.owner is not None or self.linear != 0 or self.angular != 0
        self.linear = self.angular = 0.0
        self.owner = None
        # Immediate simulated stop, including actual wheel speed.
        self.rpm = [0.0, 0.0]
        if active:
            self.log("warning", reason)

    def command(self, command: ControlCommand, client: str):
        if command.type == "stop":
            self.stop()
            return True
        if self.owner not in (None, client):
            return False
        if command.linear == 0 and command.angular == 0:
            self.stop()
            return True
        if self.owner is None:
            self.log("info", "Manual simulation command engaged")
        self.owner = client
        self.linear, self.angular = command.linear, command.angular
        self.last_command = time.monotonic()
        return True

    def disconnect(self, client):
        if self.owner == client:
            self.stop("Controller disconnected. Commands cleared.")

    def targets(self):
        return [(self.linear + sign * self.angular * WHEEL_SEPARATION / 2) * 60 / (2 * math.pi * WHEEL_RADIUS) for sign in (-1, 1)]

    def tick(self, dt=0.1):
        if self.owner is not None and time.monotonic() - self.last_command >= COMMAND_TIMEOUT:
            self.stop("Command watchdog expired. Commands cleared.")
        for i, target in enumerate(self.targets()):
            self.rpm[i] += (target - self.rpm[i]) * (1 - math.exp(-dt / 0.22))
            self.counts[i] += self.rpm[i] * ENCODER_CPR * dt / 60

    def snapshot(self):
        uptime = time.monotonic() - self.started
        targets = self.targets()
        velocity = [rpm * 2 * math.pi * WHEEL_RADIUS / 60 for rpm in self.rpm]
        return {"type": "telemetry", "simulation": True, "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": "MANUAL" if self.owner else "STANDBY", "uptime": int(uptime),
                "linear_velocity": sum(velocity) / 2, "angular_velocity": (velocity[1] - velocity[0]) / WHEEL_SEPARATION,
                "motors": [{"name": name, "target_rpm": round(targets[i], 2), "actual_rpm": round(self.rpm[i], 2), "encoder_count": round(self.counts[i])} for i, name in enumerate(("Left", "Right"))],
                "health": {"cpu_percent": round(26 + 5 * math.sin(uptime / 7), 1), "temperature_c": round(43 + 2 * math.sin(uptime / 13), 1), "memory_percent": 38, "battery_percent": 86, "battery_voltage": 12.4},
                "events": list(self.events)}
