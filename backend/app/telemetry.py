"""Serialize the authoritative simulator state for HTTP and WebSocket consumers."""
import math
import time
from .state import CHASSIS_SIZE
from .diagnostics import motor_measurements, diagnostics
from datetime import datetime, timezone


def snapshot(robot):
    uptime = robot.sample_uptime
    linear, angular = robot.drive.forward(robot.rpm)
    x, y, yaw = robot.state.pose
    config = robot.drive.config
    home = robot.configuration.value.home
    return {"type": "telemetry", "simulation": True, "session_id": robot.session_id,
            "timestamp": robot.sample_timestamp, "mode": robot.mode,
            "uptime": int(uptime), "linear_velocity": linear, "angular_velocity": angular,
            "pose": {"x": x, "y": y, "yaw": yaw, "frame_id": "map"},
            "home": {"x": home.x, "y": home.y, "yaw": home.yaw},
            "clearance": {"pose_clear": robot.grid.free(x, y),
                          "radius": robot.grid.clearance},
            "trajectory": list(robot.state.trajectory), "navigation": robot.mission.snapshot(),
            "drive": {"max_rpm": config.max_rpm, "wheel_radius": config.wheel_radius,
                      "wheel_separation": config.wheel_separation, "encoder_cpr": config.encoder_cpr,
                      "acceleration_rpm_s": config.acceleration_rpm_s,
                      "encoder_polarity": config.encoder_polarity, "chassis_size": CHASSIS_SIZE},
            "sensors": robot.sensors.snapshot(include_data=False),
            "operations": {"active": robot.operations.current, "queue_count": len(robot.operations.queue)},
            "configuration": robot.configuration.snapshot(),
            "diagnostics": diagnostics(robot),
            "motors": motor_measurements(robot),
            "health": {"cpu_percent": round(26 + 5 * math.sin(uptime / 7), 1),
                       "temperature_c": round(43 + 2 * math.sin(uptime / 13), 1),
                       "memory_percent": 38, "battery_percent": 86, "battery_voltage": 12.4},
            "events": list(robot.events)}
