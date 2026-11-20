import math
import pytest
from pydantic import ValidationError
from app.models import ControlCommand
from app.simulator import COMMAND_TIMEOUT, ENCODER_CPR, WHEEL_RADIUS, RobotSimulator


def test_differential_drive_and_encoder_conversion():
    robot = RobotSimulator()
    robot.command(ControlCommand(type="control", linear=0.25), "driver")
    expected = 0.25 * 60 / (2 * math.pi * WHEEL_RADIUS)
    assert robot.targets() == pytest.approx([expected, expected])
    robot.tick(0.1)
    assert 0 < robot.rpm[0] < expected
    assert robot.counts[0] == pytest.approx(robot.rpm[0] * ENCODER_CPR * 0.1 / 60)
    robot.command(ControlCommand(type="control", angular=1), "driver")
    assert robot.targets()[0] == -robot.targets()[1]
    assert robot.targets()[0] < 0


def test_watchdog_and_disconnect_clear_motion(monkeypatch):
    robot = RobotSimulator()
    robot.command(ControlCommand(type="control", linear=0.4), "driver")
    robot.tick()
    monkeypatch.setattr("app.simulator.time.monotonic", lambda: robot.last_command + COMMAND_TIMEOUT + 0.01)
    robot.tick()
    assert robot.targets() == [0, 0]
    assert robot.rpm == [0, 0]
    assert robot.owner is None
    robot.command(ControlCommand(type="control", angular=-0.5), "driver")
    robot.disconnect("observer")
    assert robot.owner == "driver"
    robot.disconnect("driver")
    assert robot.snapshot()["mode"] == "STANDBY"
    assert robot.rpm == [0, 0]


def test_controller_ownership_and_global_stop():
    robot = RobotSimulator()
    assert robot.command(ControlCommand(type="control", linear=0.2), "a")
    assert not robot.command(ControlCommand(type="control", linear=-0.2), "b")
    assert robot.linear == 0.2
    assert robot.command(ControlCommand(type="stop"), "b")
    assert robot.owner is None
    assert robot.command(ControlCommand(type="control", linear=-0.2), "b")


@pytest.mark.parametrize("payload", [
    {"type": "control", "linear": 0.7},
    {"type": "control", "angular": 2.1},
    {"type": "control", "linear": float("nan")},
    {"type": "control", "linear": float("inf")},
    {"type": "hardware"},
    {"type": "control", "gpio": 4},
])
def test_unsafe_or_invalid_commands_are_rejected(payload):
    with pytest.raises(ValidationError):
        ControlCommand.model_validate(payload)
