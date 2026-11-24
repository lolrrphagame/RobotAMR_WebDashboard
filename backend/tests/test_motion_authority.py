import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import ConfigurationCommand, ControlCommand, NavigationCommand
from app.operations import MissionDefinition, OperationsCommand
from app.simulator import AUTONOMOUS_TIMEOUT, COMMAND_TIMEOUT, RobotSimulator
from test_api import receive_mode, receive_type


DEFAULT_LIMITS = {"max_linear": 0.13, "max_angular": 0.8}
LOW_LIMITS = {"max_linear": 0.05, "max_angular": 0.25}
GOAL = {"x": 2, "y": 1.2}


def limit_update(limits=LOW_LIMITS):
    return {"type": "configuration", "action": "set_autonomous_speed_limits",
            "autonomous_speed_limits": limits}


def start_mission(robot, source, step="pose"):
    if source == "navigation":
        robot.command(NavigationCommand(type="navigation", action="start", goal=GOAL), "owner")
    else:
        steps = [{"kind": "pose", "pose": GOAL}] if step == "pose" else [{"kind": "wait", "seconds": 10}]
        robot.operations.create(MissionDefinition(name="Test mission", steps=steps))
        robot.command(OperationsCommand(type="operations", action="start_next"), "owner")


@pytest.mark.parametrize("source", ["navigation", "operations"])
def test_autonomous_authority_reserves_motion_and_scales_both_command_axes(source):
    robot = RobotSimulator()
    robot.command(ConfigurationCommand.model_validate(limit_update()), "operator")
    assert robot.mode == "STANDBY"
    # Start within the point follower's translation gate with a heading error.
    robot.state.pose = (1, 1, 0.6)
    start_mission(robot, source)
    manual = ControlCommand(type="control", linear=0.16, angular=0.6)
    assert not robot.command(manual, "owner")
    assert not robot.command(manual, "other")
    robot.tick(0.02)

    frame = robot.snapshot()
    motion = frame["diagnostics"]["motion"]
    request = motion["requested"]
    limited = motion["limited"]
    assert frame["mode"] == "AUTONOMOUS"
    assert frame["configuration"]["autonomous_speed_limits"] == LOW_LIMITS
    assert request["linear"] > LOW_LIMITS["max_linear"]
    assert request["angular"] > LOW_LIMITS["max_angular"]
    assert limited["linear"] == pytest.approx(LOW_LIMITS["max_linear"])
    assert 0 < limited["angular"] <= LOW_LIMITS["max_angular"]
    assert limited["angular"] / limited["linear"] == pytest.approx(request["angular"] / request["linear"])
    assert motion["limit_active"] and motion["autonomous_limit_active"]
    assert motion["measured"]["linear"] == frame["linear_velocity"]
    assert motion["measured"]["angular"] == frame["angular_velocity"]
    assert motion["measured"]["linear"] < limited["linear"]
    assert robot.targets() == pytest.approx(robot.drive.inverse(limited["linear"], limited["angular"]))

    robot.command(ControlCommand(type="stop"), "other")
    assert robot.mode == "STANDBY"
    assert robot.rpm == robot.targets() == [0, 0]
    assert robot.safety["stop_generation"] == 1 and robot.safety["stop_active"]
    assert not robot.command(manual, "owner")
    robot.command(ControlCommand(type="release"), "owner")
    assert robot.command(manual, "owner")
    assert robot.mode == "MANUAL"
    motion = robot.snapshot()["diagnostics"]["motion"]
    assert not motion["autonomous_limit_active"]
    assert motion["limited"]["linear"] > LOW_LIMITS["max_linear"]
    assert motion["limited"]["angular"] > LOW_LIMITS["max_angular"]


def test_angular_cap_and_wheel_saturation_apply_in_sequence(monkeypatch):
    robot = RobotSimulator()
    robot.command(ConfigurationCommand.model_validate(
        limit_update({"max_linear": 0.18, "max_angular": 1.2})), "operator")
    start_mission(robot, "navigation")
    monkeypatch.setattr(robot.mission, "follow", lambda _: (0.16, -1.6))
    robot.tick(0.1)
    diagnostics = robot.snapshot()["diagnostics"]
    motion = diagnostics["motion"]
    assert motion["autonomous_limit_active"] and diagnostics["saturation"]["active"]
    assert diagnostics["saturation"]["requested_rpm"] == pytest.approx(robot.drive.unlimited(0.12, -1.2))
    assert max(map(abs, robot.targets())) == pytest.approx(40)
    assert motion["limited"]["angular"] / motion["limited"]["linear"] == pytest.approx(-10)
    assert -1.2 < motion["limited"]["angular"] < 0


@pytest.mark.parametrize("limits", [
    {"max_linear": 0, "max_angular": 0.8},
    {"max_linear": 0.181, "max_angular": 0.8},
    {"max_linear": 0.13, "max_angular": 0.09},
    {"max_linear": 0.13, "max_angular": 1.21},
    {"max_linear": "0.13", "max_angular": 0.8},
    {"max_linear": 0.13, "max_angular": True},
    {"max_linear": 0.13},
    {"max_linear": 0.13, "max_angular": 0.8, "rpm": 45},
    None,
])
def test_configuration_api_rejects_invalid_limits(limits):
    with TestClient(app) as client:
        response = client.post("/api/configuration", json=limit_update(limits))
        assert response.status_code == 422, response.text
        assert client.get("/api/configuration").json()["autonomous_speed_limits"] == DEFAULT_LIMITS


@pytest.mark.parametrize("number", ["NaN", "1e400", "-1e400"])
def test_non_finite_limits_return_a_validation_error(number):
    body = json.dumps(limit_update({"max_linear": "VALUE", "max_angular": 0.8})).replace('"VALUE"', number)
    with TestClient(app) as client:
        response = client.post("/api/configuration", content=body, headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert client.get("/api/configuration").json()["autonomous_speed_limits"] == DEFAULT_LIMITS


def test_operator_socket_uses_the_same_motion_guard_and_configuration():
    with TestClient(app) as client, client.websocket_connect("/ws/telemetry") as ws:
        ws.send_json(limit_update())
        receive_type(ws, "ack")
        ws.send_json({"type": "navigation", "action": "start", "goal": GOAL})
        running = receive_mode(ws, "AUTONOMOUS")
        assert running["configuration"]["autonomous_speed_limits"] == LOW_LIMITS
        ws.send_json(limit_update(DEFAULT_LIMITS))
        assert "running or paused mission" in receive_type(ws, "error")["message"]
        assert client.get("/api/configuration").json()["autonomous_speed_limits"] == LOW_LIMITS


@pytest.mark.parametrize("state", ["manual", "coasting", "navigation", "operations"])
def test_configuration_updates_are_blocked_until_motion_and_missions_are_inactive(state):
    with TestClient(app) as client:
        robot = app.state.robot
        if state == "manual":
            robot.command(ControlCommand(type="control", linear=0.12), "owner")
        elif state == "coasting":
            # Residual wheel movement must also block updates if no command owns motion.
            robot.state.rpm = [10, -10]
        else:
            client.portal.call(start_mission, robot, state, "wait")
            client.portal.call(robot.tick, 0.02)
            assert robot.mode == "AUTONOMOUS"
        response = client.post("/api/configuration", json=limit_update())
        assert response.status_code == 409
        assert response.json()["detail"] == robot.autonomous_limits_blocked_reason()
        if state in ("navigation", "operations"):
            client.portal.call(robot.disconnect, "owner")
            assert robot.mode == "AUTONOMOUS" and robot.owner is None and robot.rpm == [0, 0]
            assert client.post("/api/configuration", json=limit_update()).status_code == 409
        assert client.get("/api/configuration").json()["autonomous_speed_limits"] == DEFAULT_LIMITS
        client.portal.call(robot.command, ControlCommand(type="stop"), "other")
        assert client.post("/api/configuration", json=limit_update()).status_code == 200
        assert robot.safety["stop_active"] and robot.safety["stop_generation"] == 1


def test_legacy_configuration_and_limits_persist_without_resetting_saved_poses(tmp_path):
    path = tmp_path / "robot-config.json"
    legacy = {"version": 1, "home": {"x": 2, "y": 2, "yaw": 0.4},
              "waypoints": {"B": {"x": 2, "y": 1, "yaw": 0.5}}}
    path.write_text(json.dumps(legacy))
    with TestClient(app) as client:
        original = client.get("/api/configuration").json()
        assert original["autonomous_speed_limits"] == DEFAULT_LIMITS
        assert json.loads(path.read_text()) == legacy
        response = client.post("/api/configuration", json=limit_update())
        assert response.status_code == 200
        assert client.post("/api/waypoints", json={
            "type": "waypoint", "name": "A", "goal": {"x": 1, "y": 2},
        }).status_code == 200
    with TestClient(app) as client:
        restored = client.get("/api/configuration").json()
        assert restored["version"] == 1 and restored["home"] == original["home"]
        assert restored["waypoints"]["B"] == original["waypoints"]["B"]
        assert restored["waypoints"]["A"]["y"] == 2
        assert restored["autonomous_speed_limits"] == LOW_LIMITS
        assert client.get("/api/robot/status").json()["mode"] == "STANDBY"


def test_invalid_saved_limits_do_not_discard_valid_home_or_waypoints(tmp_path):
    path = tmp_path / "robot-config.json"
    contents = json.dumps({"version": 1, "home": {"x": 2, "y": 2},
                           "waypoints": {"A": GOAL},
                           "autonomous_speed_limits": {"max_linear": 0.25, "max_angular": 0.8}})
    path.write_text(contents)
    with TestClient(app) as client:
        current = client.get("/api/configuration").json()
        assert current["autonomous_speed_limits"] == DEFAULT_LIMITS
        assert current["home"]["x"] == 2 and current["waypoints"]["A"]["x"] == 2
        assert "Saved autonomous speed limits are invalid" in current["load_warnings"][0]
        assert path.read_text() == contents


def test_manual_watchdog_and_autonomous_lease_still_halt_with_new_limits(monkeypatch):
    robot = RobotSimulator()
    robot.command(ConfigurationCommand.model_validate(limit_update()), "operator")
    robot.command(ControlCommand(type="control", linear=0.12), "owner")
    robot.tick()
    assert any(robot.rpm)
    now = robot.last_command + COMMAND_TIMEOUT + 0.01
    monkeypatch.setattr("app.simulator.time.monotonic", lambda: now)
    robot.tick()
    assert robot.mode == "STANDBY" and robot.rpm == robot.targets() == [0, 0]
    assert robot.safety["watchdog"] == "expired"

    start_mission(robot, "navigation")
    robot.tick()
    assert any(robot.rpm)
    now = robot.last_lease + AUTONOMOUS_TIMEOUT + 0.01
    robot.tick()
    assert robot.mode == "AUTONOMOUS" and robot.mission.status == "paused"
    assert robot.rpm == robot.targets() == [0, 0]
    assert robot.safety["watchdog"] == "expired" and robot.owner is None
