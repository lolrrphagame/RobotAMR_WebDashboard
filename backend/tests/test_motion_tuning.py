import csv
import io
import json
import math

import pytest
from fastapi.testclient import TestClient

from app.configuration import ConfigurationError, ConfigurationStore
from app.drive import DriveConfig
from app.main import app
from app.models import ConfigurationCommand, ControlCommand, NavigationCommand
from app.operations import MissionDefinition, OperationsCommand
from app.simulator import AUTONOMOUS_TIMEOUT, COMMAND_TIMEOUT, RobotSimulator
from test_api import receive_type


DEFAULT_WHEELS = {"max_rpm": 40, "acceleration_rpm_s": 60}
DEFAULT_CAPS = {"max_linear": 0.13, "max_angular": 0.8}
TUNED_WHEELS = {"max_rpm": 20, "acceleration_rpm_s": 15}
HIGH_CAPS = {"max_linear": 0.18, "max_angular": 1.2}
RESTORE = {"type": "configuration", "action": "restore_motion_defaults"}
GOAL = {"x": 2, "y": 1.2}
MANUAL = ControlCommand(type="control", linear=0.3, angular=-0.8)
STOP = ControlCommand(type="stop")
RELEASE = ControlCommand(type="release")


def tuning(wheels=TUNED_WHEELS, caps=None):
    command = {"type": "configuration", "action": "set_motion_settings", "wheel_constraints": wheels}
    if caps is not None:
        command["autonomous_speed_limits"] = caps
    return command


def set_tuning(robot, wheels=TUNED_WHEELS, caps=None):
    return robot.command(ConfigurationCommand.model_validate(tuning(wheels, caps)), "owner")


def assert_kinematics(robot, rpm, slew, caps):
    config = robot.configuration.snapshot()
    geometry = robot.drive.config
    circumference_per_second = 2 * math.pi * geometry.wheel_radius / 60
    speed = rpm * circumference_per_second
    acceleration = slew * circumference_per_second
    angular = 2 * speed / geometry.wheel_separation
    limits = config["kinematic_limits"]
    assert config["effective_wheel_constraints"] == {"max_rpm": rpm, "acceleration_rpm_s": slew}
    assert limits["max_straight_linear"] == pytest.approx(speed)
    assert limits["max_in_place_angular"] == pytest.approx(angular)
    assert limits["max_straight_acceleration"] == pytest.approx(acceleration)
    assert limits["max_in_place_angular_acceleration"] == pytest.approx(2 * acceleration / geometry.wheel_separation)
    assert limits["effective_autonomous_speed_limits"] == pytest.approx({
        "max_linear": min(caps["max_linear"], speed), "max_angular": min(caps["max_angular"], angular),
    })


def test_default_geometry_speed_and_slew_remain_the_same():
    robot = RobotSimulator()
    drive = robot.snapshot()["drive"]
    assert (drive["wheel_radius"], drive["wheel_separation"], drive["encoder_cpr"]) == (0.0435, 0.3, 3960)
    assert robot.configuration.snapshot()["wheel_constraints"] == DEFAULT_WHEELS
    assert robot.configuration.snapshot()["autonomous_speed_limits"] == DEFAULT_CAPS
    assert_kinematics(robot, 40, 60, DEFAULT_CAPS)
    robot.command(ControlCommand(type="control", linear=0.3), "owner")
    robot.tick(0.1)
    assert robot.targets() == pytest.approx([40, 40])
    assert robot.rpm == pytest.approx([6, 6])


def test_tuned_saturation_and_slew_apply_to_manual_and_autonomous(monkeypatch):
    robot = RobotSimulator()
    old_pose = robot.state.pose
    assert set_tuning(robot, caps=HIGH_CAPS)
    assert robot.mode == "STANDBY" and robot.rpm == [0, 0] and robot.state.pose == old_pose
    assert_kinematics(robot, 20, 15, HIGH_CAPS)

    robot.command(MANUAL, "owner")
    robot.tick(0.1)
    assert robot.rpm == pytest.approx([1.5, 1.5])
    limited = robot.snapshot()["diagnostics"]["motion"]["limited"]
    assert max(map(abs, robot.targets())) == pytest.approx(20)
    assert limited["angular"] / limited["linear"] == pytest.approx(-0.8 / 0.3)
    robot.command(RELEASE, "owner")
    assert robot.rpm == [0, 0]

    robot.command(NavigationCommand(type="navigation", action="start", goal=GOAL), "owner")
    monkeypatch.setattr(robot.mission, "follow", lambda _: (0.3, -1.6))
    robot.tick(0.1)
    diag = robot.snapshot()["diagnostics"]
    assert diag["motion"]["autonomous_limit_active"] and diag["saturation"]["active"]
    assert robot.rpm == pytest.approx([1.5, 1.5])
    assert max(map(abs, robot.targets())) == pytest.approx(20)
    limited = diag["motion"]["limited"]
    assert limited["angular"] / limited["linear"] == pytest.approx(-1.6 / 0.3)


@pytest.mark.parametrize("injected, expected", [((8, 7), (8, 7)), ((80, 90), (40, 60))])
def test_injected_drive_constraints_are_ceiling_and_geometry_is_preserved(tmp_path, injected, expected):
    store = ConfigurationStore(tmp_path / "robot-config.json")
    base = DriveConfig(max_rpm=injected[0], acceleration_rpm_s=injected[1], wheel_radius=0.05,
                       wheel_separation=0.4, encoder_cpr=1000, encoder_polarity=(-1, 1))
    robot = RobotSimulator(base, store=store)
    assert_kinematics(robot, *expected, DEFAULT_CAPS)
    set_tuning(robot)
    loaded = RobotSimulator(base, store=store)
    assert_kinematics(loaded, min(expected[0], 20), min(expected[1], 15), DEFAULT_CAPS)
    loaded.command(ConfigurationCommand.model_validate(RESTORE), "owner")
    assert_kinematics(loaded, *expected, DEFAULT_CAPS)
    drive = loaded.drive.config
    assert (drive.wheel_radius, drive.wheel_separation, drive.encoder_cpr, drive.encoder_polarity) == (0.05, 0.4, 1000, (-1, 1))


@pytest.mark.parametrize("wheels", [
    {"max_rpm": 9.9, "acceleration_rpm_s": 40}, {"max_rpm": 40.01, "acceleration_rpm_s": 40},
    {"max_rpm": 20, "acceleration_rpm_s": 9.99}, {"max_rpm": 20, "acceleration_rpm_s": 60.01},
    {"max_rpm": "20", "acceleration_rpm_s": 20}, {"max_rpm": 20, "acceleration_rpm_s": True},
    {"max_rpm": 20}, {"max_rpm": 20, "acceleration_rpm_s": 20, "wheel_radius": 0.05},
])
def test_invalid_update_rejects_the_whole_payload(wheels, tmp_path):
    path = tmp_path / "robot-config.json"
    with TestClient(app) as client:
        assert client.post("/api/configuration", json=tuning()).status_code == 200
        baseline = path.read_bytes()
        response = client.post("/api/configuration", json=tuning(wheels, HIGH_CAPS))
        assert response.status_code == 422
        assert path.read_bytes() == baseline
        config = client.get("/api/configuration").json()
        assert config["wheel_constraints"] == TUNED_WHEELS
        assert config["autonomous_speed_limits"] == DEFAULT_CAPS


@pytest.mark.parametrize("value", ["NaN", "1e400", "-1e400"])
def test_nonfinite_wheel_setting_returns_422(value):
    command = tuning({"max_rpm": 20, "acceleration_rpm_s": "VALUE"}, HIGH_CAPS)
    body = json.dumps(command).replace('"VALUE"', value)
    with TestClient(app) as client:
        response = client.post("/api/configuration", content=body, headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        config = client.get("/api/configuration").json()
        assert config["wheel_constraints"] == DEFAULT_WHEELS and config["autonomous_speed_limits"] == DEFAULT_CAPS


def test_legacy_config_wheel_only_save_restart_and_restore(tmp_path):
    path = tmp_path / "robot-config.json"
    legacy = {"version": 1, "home": {"x": 2, "y": 2, "yaw": 0.4},
              "waypoints": {"B": GOAL}, "autonomous_speed_limits": HIGH_CAPS}
    path.write_text(json.dumps(legacy))
    with TestClient(app) as client:
        original = client.get("/api/configuration").json()
        assert original["wheel_constraints"] == DEFAULT_WHEELS
        assert json.loads(path.read_text()) == legacy
        with client.websocket_connect("/ws/telemetry") as ws:
            ws.send_json(tuning({"max_rpm": 10, "acceleration_rpm_s": 10}))
            receive_type(ws, "ack")
        assert client.get("/api/configuration").json()["autonomous_speed_limits"] == HIGH_CAPS
    with TestClient(app) as client:
        status = client.get("/api/robot/status").json()
        assert status["drive"]["max_rpm"] == status["drive"]["acceleration_rpm_s"] == 10
        assert status["mode"] == "STANDBY"
        response = client.post("/api/configuration", json=RESTORE)
        assert response.status_code == 200
        config = response.json()
        assert config["wheel_constraints"] == DEFAULT_WHEELS and config["autonomous_speed_limits"] == DEFAULT_CAPS
        assert config["home"] == original["home"] and config["waypoints"] == original["waypoints"]
        assert json.loads(path.read_text())["wheel_constraints"] == DEFAULT_WHEELS
        assert client.get("/api/robot/status").json()["mode"] == "STANDBY"


def test_invalid_saved_wheel_values_keep_valid_other_settings(tmp_path):
    path = tmp_path / "robot-config.json"
    saved = {"version": 1, "home": {"x": 2, "y": 2}, "waypoints": {"A": GOAL},
             "autonomous_speed_limits": HIGH_CAPS, "wheel_constraints": {"max_rpm": 50}}
    path.write_text(json.dumps(saved))
    with TestClient(app) as client:
        config = client.get("/api/configuration").json()
        assert config["wheel_constraints"] == DEFAULT_WHEELS
        assert config["autonomous_speed_limits"] == HIGH_CAPS
        assert config["home"]["x"] == 2 and config["waypoints"]["A"]["x"] == GOAL["x"]
        assert "Saved wheel constraints are invalid" in config["load_warnings"][0]
        assert json.loads(path.read_text()) == saved


def test_failed_persistence_does_not_modify_live_drive_or_configuration(tmp_path, monkeypatch):
    store = ConfigurationStore(tmp_path / "robot-config.json")
    robot = RobotSimulator(store=store)
    set_tuning(robot)
    saved = store.path.read_bytes()
    configuration = robot.configuration.snapshot()
    drive = robot.drive.config

    def fail(*_):
        raise OSError("simulated disk failure")

    monkeypatch.setattr("app.configuration.os.replace", fail)
    with pytest.raises(ConfigurationError, match="no change applied"):
        set_tuning(robot, DEFAULT_WHEELS, HIGH_CAPS)
    assert robot.configuration.snapshot() == configuration and robot.drive.config == drive
    assert store.path.read_bytes() == saved and list(tmp_path.iterdir()) == [store.path]


@pytest.mark.parametrize("state", ["manual", "running", "paused", "wait", "paused-wait"])
def test_save_and_restore_conflict_while_control_is_reserved(state):
    with TestClient(app) as client:
        robot = app.state.robot

        def reserve():
            if state == "manual":
                robot.command(MANUAL, "owner")
            elif "wait" in state:
                robot.operations.create(MissionDefinition(name="WAIT test", steps=[{"kind": "wait", "seconds": 10}]))
                robot.command(OperationsCommand(type="operations", action="start_next"), "owner")
            else:
                robot.command(NavigationCommand(type="navigation", action="start", goal=GOAL), "owner")
            robot.tick(0.02)
            if "paused" in state:
                robot.disconnect("owner")

        client.portal.call(reserve)
        for action in (tuning(), RESTORE):
            response = client.post("/api/configuration", json=action)
            assert response.status_code == 409
            if "wait" in state:
                assert "WAIT" in response.json()["detail"]
        if state == "manual":
            assert any(robot.rpm)
            client.portal.call(robot.command, STOP, "other")
            assert robot.rpm == robot.targets() == [0, 0]
            assert not client.portal.call(robot.command, MANUAL, "owner")
            assert client.post("/api/configuration", json=RESTORE).status_code == 409
            client.portal.call(robot.command, RELEASE, "owner")
        else:
            client.portal.call(robot.command, STOP, "other")
        assert client.post("/api/configuration", json=tuning()).status_code == 200
        assert robot.safety["stop_generation"] == 1 and robot.mode == "STANDBY"


def test_minimum_slew_does_not_delay_watchdog_collision_or_autonomous_lease(monkeypatch):
    robot = RobotSimulator()
    set_tuning(robot, {"max_rpm": 10, "acceleration_rpm_s": 10})
    robot.command(MANUAL, "owner")
    robot.tick()
    assert any(robot.rpm)
    now = robot.last_command + COMMAND_TIMEOUT + 0.01
    monkeypatch.setattr("app.simulator.time.monotonic", lambda: now)
    robot.tick()
    assert robot.rpm == [0, 0] and robot.safety["watchdog"] == "expired"

    robot.command(MANUAL, "owner")
    robot.tick()
    assert any(robot.rpm)
    with monkeypatch.context() as collision:
        collision.setattr(robot.grid, "segment_free", lambda *_: False)
        pose = robot.state.pose
        robot.tick()
        assert robot.rpm == [0, 0] and robot.state.pose == pose and robot.counters["collisions"] == 1
        with pytest.raises(ConfigurationError, match="Release manual input"):
            set_tuning(robot)
    robot.command(RELEASE, "owner")
    robot.command(NavigationCommand(type="navigation", action="start", goal=GOAL), "owner")
    robot.tick()
    assert any(robot.rpm)
    now = robot.last_lease + AUTONOMOUS_TIMEOUT + 0.01
    robot.tick()
    assert robot.rpm == [0, 0] and robot.mission.status == "paused" and robot.safety["watchdog"] == "expired"


def test_motion_history_and_csv_use_authoritative_frame_and_session():
    with TestClient(app) as client:
        robot = app.state.robot

        def motion_frame():
            assert set_tuning(robot)
            robot.command(ControlCommand(type="control", linear=0.08, angular=-2), "owner")
            robot.tick()
            return robot.snapshot()

        frame = client.portal.call(motion_frame)
        motion = frame["diagnostics"]["motion"]
        assert frame["diagnostics"]["integration_status"] == {
            "backend": "simulation", "ros2_connected": False, "nav2_connected": False, "esp32_s3_connected": False,
        }
        body = client.get("/api/diagnostics/history").json()
        rows = {sample["timestamp"]: sample for sample in body["samples"]}
        sample = rows[frame["timestamp"]]
        assert sample["session_id"] == frame["session_id"] == body["session_id"]
        values = {"requested_linear": motion["requested"]["linear"], "requested_angular": motion["requested"]["angular"],
                  "limited_linear": motion["limited"]["linear"], "limited_angular": motion["limited"]["angular"],
                  "linear_velocity": motion["measured"]["linear"], "angular_velocity": motion["measured"]["angular"],
                  "left_error_rpm": frame["motors"][0]["tracking_error_rpm"],
                  "right_error_rpm": frame["motors"][1]["tracking_error_rpm"]}
        assert {key: sample[key] for key in values} == values
        assert values["left_error_rpm"] > 0 > values["right_error_rpm"]
        table = csv.DictReader(io.StringIO(client.get("/api/diagnostics/history?format=csv").text))
        exported = next(row for row in table if row["timestamp"] == frame["timestamp"])
        assert exported["session_id"] == frame["session_id"]
        assert {key: float(exported[key]) for key in values} == values
