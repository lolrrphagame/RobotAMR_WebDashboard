from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from .drive import MAX_ACCELERATION_RPM_S, MAX_RPM


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ControlCommand(StrictModel):
    type: Literal["control", "stop", "release", "heartbeat"]
    linear: float = Field(default=0, ge=-0.6, le=0.6)
    angular: float = Field(default=0, ge=-2, le=2)


class Goal(StrictModel):
    x: float = Field(ge=0, le=8)
    y: float = Field(ge=0, le=6)
    yaw: float = Field(default=0, ge=-3.141593, le=3.141593)
    name: str = Field(default="Destination", max_length=32)


class NavigationCommand(StrictModel):
    type: Literal["navigation"]
    action: Literal["plan", "start", "pause", "resume", "cancel", "home", "sequence"]
    goal: Goal | None = None
    waypoints: list[Literal["A", "B", "C"]] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_action(self):
        if self.action in ("plan", "start") and self.goal is None:
            raise ValueError("A destination is required")
        if self.action == "sequence" and not self.waypoints:
            raise ValueError("Choose at least one waypoint")
        return self


class WaypointCommand(StrictModel):
    type: Literal["waypoint"]
    action: Literal["save", "delete"] = "save"
    name: Literal["A", "B", "C"]
    goal: Goal | None = None

    @model_validator(mode="after")
    def validate_save(self):
        if self.action == "save" and self.goal is None:
            raise ValueError("A waypoint pose is required")
        return self


AUTONOMOUS_SPEED_LIMIT_RANGES = {
    "max_linear": {"min": 0.01, "max": 0.18},
    "max_angular": {"min": 0.1, "max": 1.2},
}


class AutonomousSpeedLimits(StrictModel):
    """SI limits within the standalone straight-line and turn-in-place envelopes."""

    max_linear: float = Field(strict=True, ge=AUTONOMOUS_SPEED_LIMIT_RANGES["max_linear"]["min"],
                              le=AUTONOMOUS_SPEED_LIMIT_RANGES["max_linear"]["max"])
    max_angular: float = Field(strict=True, ge=AUTONOMOUS_SPEED_LIMIT_RANGES["max_angular"]["min"],
                               le=AUTONOMOUS_SPEED_LIMIT_RANGES["max_angular"]["max"])


WHEEL_CONSTRAINT_RANGES = {
    "max_rpm": {"min": 10, "max": MAX_RPM},
    "acceleration_rpm_s": {"min": 10, "max": MAX_ACCELERATION_RPM_S},
}


class WheelConstraints(StrictModel):
    max_rpm: float = Field(default=MAX_RPM, strict=True, ge=WHEEL_CONSTRAINT_RANGES["max_rpm"]["min"], le=MAX_RPM)
    acceleration_rpm_s: float = Field(default=MAX_ACCELERATION_RPM_S, strict=True,
                                      ge=WHEEL_CONSTRAINT_RANGES["acceleration_rpm_s"]["min"], le=MAX_ACCELERATION_RPM_S)


class ConfigurationCommand(StrictModel):
    type: Literal["configuration"]
    action: Literal["set_home", "current_home", "reset_home", "set_autonomous_speed_limits",
                    "set_motion_settings", "restore_motion_defaults"]
    goal: Goal | None = None
    autonomous_speed_limits: AutonomousSpeedLimits | None = None
    wheel_constraints: WheelConstraints | None = None

    @model_validator(mode="after")
    def validate_action(self):
        if self.action == "set_home" and self.goal is None:
            raise ValueError("Select a Home pose first")
        if self.action == "set_autonomous_speed_limits":
            if self.autonomous_speed_limits is None or self.goal is not None:
                raise ValueError("Provide both autonomous speed limits without a Home pose")
        elif self.action == "set_motion_settings":
            if self.goal is not None or (self.autonomous_speed_limits is None and self.wheel_constraints is None):
                raise ValueError("Provide autonomous speed limits, wheel constraints, or both without a Home pose")
        elif self.autonomous_speed_limits is not None:
            raise ValueError("Use a motion settings action to change autonomous speed limits")
        if self.wheel_constraints is not None:
            if self.action != "set_motion_settings":
                raise ValueError("Use set_motion_settings to change wheel constraints")
            if self.wheel_constraints.model_fields_set != set(WHEEL_CONSTRAINT_RANGES):
                raise ValueError("Provide both wheel constraints")
        if self.action == "restore_motion_defaults" and self.goal is not None:
            raise ValueError("Restoring motion defaults does not accept a Home pose")
        return self


command_adapter = TypeAdapter(Annotated[ControlCommand | NavigationCommand | WaypointCommand | ConfigurationCommand, Field(discriminator="type")])
