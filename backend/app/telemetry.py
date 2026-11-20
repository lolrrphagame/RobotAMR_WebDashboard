"""Serialize the authoritative simulator state for HTTP and WebSocket consumers."""
import math
import time
from .state import HOME, CHASSIS_SIZE
from datetime import datetime, timezone


def snapshot(robot):
    uptime = time.monotonic() - robot.started
    linear, angular = robot.drive.forward(robot.rpm)
    x, y, yaw = robot.state.pose
    config = robot.drive.config
    return {"type": "telemetry", "simulation": True,
            "timestamp": datetime.now(timezone.utc).isoformat(), "mode": robot.mode,
            "uptime": int(uptime), "linear_velocity": linear, "angular_velocity": angular,
            "pose": {"x": x, "y": y, "yaw": yaw, "frame_id": "map"},
            "home": {"x": HOME[0], "y": HOME[1], "yaw": HOME[2]},
            "trajectory": list(robot.state.trajectory), "navigation": robot.mission.snapshot(),
            "drive": {"max_rpm": config.max_rpm, "wheel_radius": config.wheel_radius,
                      "wheel_separation": config.wheel_separation, "encoder_cpr": config.encoder_cpr,
                      "encoder_polarity": config.encoder_polarity, "chassis_size": CHASSIS_SIZE},
            "motors": [{"name": name, "target_rpm": round(robot.targets()[i], 2),
                        "actual_rpm": round(robot.rpm[i], 2), "encoder_count": round(robot.counts[i]),
                        "raw_encoder_count": round(robot.counts[i] * config.encoder_polarity[i])}
                       for i, name in enumerate(("Left", "Right"))],
            "health": {"cpu_percent": round(26 + 5 * math.sin(uptime / 7), 1),
                       "temperature_c": round(43 + 2 * math.sin(uptime / 13), 1),
                       "memory_percent": 38, "battery_percent": 86, "battery_voltage": 12.4},
            "events": list(robot.events)}
