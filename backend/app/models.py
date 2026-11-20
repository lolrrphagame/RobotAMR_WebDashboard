from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


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


class ConfigurationCommand(StrictModel):
    type: Literal["configuration"]
    action: Literal["set_home", "current_home", "reset_home"]
    goal: Goal | None = None

    @model_validator(mode="after")
    def validate_home(self):
        if self.action == "set_home" and self.goal is None:
            raise ValueError("Select a Home pose first")
        return self


command_adapter = TypeAdapter(Annotated[ControlCommand | NavigationCommand | WaypointCommand | ConfigurationCommand, Field(discriminator="type")])
