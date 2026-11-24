"""Simulation measurements and honest unavailable contracts for future adapters."""
import math
import time


def motor_measurements(robot):
    c = robot.drive.config
    targets = robot.targets()
    return [{"name": name, "source": "simulation", "target_rpm": round(targets[i], 2),
             "actual_rpm": round(robot.rpm[i], 2),
             "tracking_error_rpm": round(round(targets[i], 2) - round(robot.rpm[i], 2), 2),
             "encoder_count": round(robot.counts[i]),
             "raw_encoder_count": round(robot.counts[i] * c.encoder_polarity[i]),
             "wheel_velocity": robot.rpm[i] * 2 * math.pi * c.wheel_radius / 60,
             "travel_distance": robot.counts[i] / c.encoder_cpr * 2 * math.pi * c.wheel_radius,
             "pi": {"source": "unavailable", "kp": None, "ki": None, "pwm": None,
                    "control_error": None, "integral_term": None}}
            for i, name in enumerate(("Left", "Right"))]


def interfaces():
    return {"ros2": {"name": "ROS 2 Humble", "source": "disabled", "connected": False,
                      "last_message_at": None, "observed_hz": None,
                      "diagnostics_contract": "diagnostic_msgs/DiagnosticArray on /diagnostics (planned)",
                      "planned": [
                          {"node": "amr_base_controller", "topic": "/cmd_vel", "message_type": "geometry_msgs/Twist", "expected_hz": 20},
                          {"node": "amr_base_controller", "topic": "/odom", "message_type": "nav_msgs/Odometry", "expected_hz": 20},
                          {"node": "robot_state_publisher", "topic": "/tf", "message_type": "tf2_msgs/TFMessage", "expected_hz": 20},
                          {"node": "lidar_driver", "topic": "/scan", "message_type": "sensor_msgs/LaserScan", "expected_hz": 10},
                          {"node": "camera_driver", "topic": "/camera/image_raw", "message_type": "sensor_msgs/Image", "expected_hz": 15}]},
            "uart": {"name": "ESP32-S3 / UART", "source": "disabled", "connected": False,
                     "planned_baud": 57600, "last_message_at": None, "heartbeat": None, "watchdog": None,
                     "tx_bytes": None, "rx_bytes": None, "command_count": None, "fault_count": None}}


def diagnostics(robot):
    linear, angular, autonomous_limit_active = robot.drive_request()
    unlimited = robot.drive.unlimited(linear, angular)
    scale = robot.drive.wheel_limit_divisor(unlimited)
    limited_v, limited_w = robot.drive.forward(robot.targets())
    measured_v, measured_w = robot.drive.forward(robot.rpm)
    age = None
    if robot.owner is not None:
        age = max(0, (time.monotonic() - (robot.last_lease if robot.autonomous_active else robot.last_command)) * 1000)
    return {"source": "simulation", "model": "Acceleration-limited differential drive",
            "motion": {"requested": {"linear": robot.linear, "angular": robot.angular},
                       "limited": {"linear": limited_v, "angular": limited_w},
                       "measured": {"linear": measured_v, "angular": measured_w},
                       "limit_active": autonomous_limit_active or scale > 1.0,
                       "autonomous_limit_active": autonomous_limit_active},
            "saturation": {"active": scale > 1.0, "scale": 1 / scale,
                           "requested_rpm": unlimited, "limit_rpm": robot.drive.config.max_rpm},
            "safety": {**robot.safety, "command_age_ms": age, "manual_timeout_ms": 600,
                       "autonomous_timeout_ms": 1500, "collision_guard": robot.collision_origin is not None,
                       "autonomous_limits_blocked_reason": robot.autonomous_limits_blocked_reason()},
            "counters": dict(robot.counters), "interfaces": interfaces(),
            "integration_status": {"backend": "simulation", "ros2_connected": False,
                                   "nav2_connected": False, "esp32_s3_connected": False}}


def history_sample(frame):
    left, right = frame["motors"]
    motion = frame["diagnostics"]["motion"]
    return {"timestamp": frame["timestamp"], "session_id": frame["session_id"], "source": "simulation", "mode": frame["mode"],
            "x": frame["pose"]["x"], "y": frame["pose"]["y"], "yaw": frame["pose"]["yaw"],
            "linear_velocity": frame["linear_velocity"], "angular_velocity": frame["angular_velocity"],
            "requested_linear": motion["requested"]["linear"], "requested_angular": motion["requested"]["angular"],
            "limited_linear": motion["limited"]["linear"], "limited_angular": motion["limited"]["angular"],
            "left_target_rpm": left["target_rpm"], "left_actual_rpm": left["actual_rpm"],
            "right_target_rpm": right["target_rpm"], "right_actual_rpm": right["actual_rpm"],
            "left_error_rpm": left["tracking_error_rpm"], "right_error_rpm": right["tracking_error_rpm"],
            "left_encoder_count": left["encoder_count"], "right_encoder_count": right["encoder_count"],
            "left_travel_m": left["travel_distance"], "right_travel_m": right["travel_distance"],
            "saturated": frame["diagnostics"]["saturation"]["active"],
            **frame["health"]}
