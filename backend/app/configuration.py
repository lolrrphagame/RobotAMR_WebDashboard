"""Validated robot configuration, independent of live pose and mission state."""
import json
import os
import tempfile
from pathlib import Path
from typing import Literal
from pydantic import Field
from .models import AUTONOMOUS_SPEED_LIMIT_RANGES, AutonomousSpeedLimits, Goal, StrictModel
from .state import HOME


class ConfigurationError(ValueError):
    """Rejected configuration updates never alter motion or ownership."""


class ConfigurationConflict(ConfigurationError):
    pass


class SavedConfiguration(StrictModel):
    version: Literal[1] = 1
    home: Goal = Field(default_factory=lambda: Goal(x=HOME[0], y=HOME[1], yaw=HOME[2], name="Home"))
    waypoints: dict[Literal["A", "B", "C"], Goal] = Field(default_factory=dict)
    autonomous_speed_limits: AutonomousSpeedLimits = Field(
        default_factory=lambda: AutonomousSpeedLimits(max_linear=0.13, max_angular=0.8))


class ConfigurationStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def read(self):
        if not self.path.exists():
            return None
        with self.path.open(encoding="utf-8") as handle:
            raw = handle.read(65537)
        if len(raw) > 65536:
            raise ValueError("Configuration file exceeds 64 KiB")
        return json.loads(raw)

    def write(self, config: SavedConfiguration):
        temp_path = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".robot-config-", suffix=".tmp", delete=False) as handle:
                temp_path = Path(handle.name)
                json.dump(config.model_dump(), handle, indent=2, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        except OSError as exc:
            raise ValueError("Configuration save failed; no change applied. Check local storage permissions and space.") from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)


class ConfigurationManager:
    def __init__(self, grid, store=None):
        self.grid, self.store = grid, store
        self.value = SavedConfiguration()
        self.warnings = []
        if store is not None:
            try:
                raw = store.read()
                if raw is not None:
                    if not isinstance(raw, dict) or raw.get("version") != 1:
                        raise ValueError("Unsupported configuration version")
                    try:
                        home = Goal.model_validate(raw.get("home"))
                        self.validate_pose(home, "Saved Home")
                        self.value.home = home.model_copy(update={"name": "Home"})
                    except ValueError:
                        self.warnings.append("Saved Home is invalid for this map; using default Home.")
                    points = raw.get("waypoints", {})
                    if not isinstance(points, dict):
                        raise ValueError("Invalid waypoint configuration")
                    for name, payload in points.items():
                        try:
                            if name not in ("A", "B", "C"):
                                raise ValueError("Unknown waypoint")
                            goal = Goal.model_validate(payload)
                            self.validate_pose(goal, f"Saved waypoint {name}")
                            self.value.waypoints[name] = goal.model_copy(update={"name": name})
                        except ValueError:
                            self.warnings.append(f"Saved waypoint {name[:16]} is invalid and was skipped.")
                    if "autonomous_speed_limits" in raw:
                        try:
                            self.value.autonomous_speed_limits = AutonomousSpeedLimits.model_validate(
                                raw["autonomous_speed_limits"])
                        except ValueError:
                            self.warnings.append("Saved autonomous speed limits are invalid; using simulation defaults.")
            except (OSError, ValueError) as exc:
                self.value = SavedConfiguration()
                self.warnings.append(f"Configuration could not be restored ({type(exc).__name__}); using defaults. Original file preserved.")
        if not grid.free(self.value.home.x, self.value.home.y):
            raise ValueError("Home pose lacks robot footprint clearance in the supplied map")

    def validate_pose(self, goal, label):
        if not self.grid.free(goal.x, goal.y):
            raise ValueError(f"{label} ({goal.x:.2f}, {goal.y:.2f}) lacks {self.grid.clearance:.3f} m footprint clearance; choose free space.")

    def commit(self, home=None, waypoints=None, autonomous_speed_limits=None):
        candidate = SavedConfiguration(
            home=home if home is not None else self.value.home,
            waypoints=waypoints if waypoints is not None else self.value.waypoints,
            autonomous_speed_limits=(autonomous_speed_limits if autonomous_speed_limits is not None
                                     else self.value.autonomous_speed_limits),
        )
        self.validate_pose(candidate.home, "Home")
        for name, goal in candidate.waypoints.items():
            self.validate_pose(goal, f"Waypoint {name}")
        if self.store is not None:
            self.store.write(candidate)
        self.value = candidate
        self.warnings = []

    def snapshot(self):
        return {**self.value.model_dump(), "simulation": True, "map_id": self.grid.snapshot()["id"],
                "autonomous_speed_limit_ranges": AUTONOMOUS_SPEED_LIMIT_RANGES,
                "storage": "local-file" if self.store is not None else "memory",
                "load_warnings": self.warnings}
