"""Single simulation coordinator: arbitration, plant stepping and mission safety."""
import math
import time
from collections import deque
from datetime import datetime, timezone
from .drive import DifferentialDrive, DriveConfig, WHEEL_RADIUS, WHEEL_SEPARATION, ENCODER_CPR
from .mission import MissionManager
from .models import ControlCommand, NavigationCommand, Goal, WaypointCommand
from .navigation import OccupancyGrid
from .state import HOME, RobotState
from .telemetry import snapshot

COMMAND_TIMEOUT = 0.6
AUTONOMOUS_TIMEOUT = 1.5


class RobotSimulator:
    def __init__(self, config: DriveConfig | None = None, grid=None):
        self.started = time.monotonic()
        self.last_command = self.last_lease = 0.0
        self.owner = None
        self.linear = self.angular = 0.0
        self.state = RobotState()
        self.drive = DifferentialDrive(config)
        self.grid = grid or OccupancyGrid()
        if not self.grid.free(*self.state.pose[:2]):
            raise ValueError("Home pose lacks robot footprint clearance in the supplied map")
        self.mission = MissionManager(self.grid)
        self.collision_origin = None
        self.collision_source = None
        self.manual_collision_command = None
        self.events = deque(maxlen=60)
        self.event_id = 0
        self.log("info", "Navigation simulator initialized. All hardware interfaces disabled.")

    @property
    def rpm(self):
        return self.state.rpm

    @property
    def counts(self):
        return self.state.counts

    @property
    def mode(self):
        return "AUTONOMOUS" if self.mission.active else "MANUAL" if self.owner else "STANDBY"

    def log(self, level, message):
        self.event_id += 1
        self.events.appendleft({"id": self.event_id, "time": datetime.now(timezone.utc).isoformat(),
                                "level": level, "message": message})

    def halt(self):
        self.linear = self.angular = 0.0
        self.state.rpm = [0.0, 0.0]

    def stop(self, reason="STOP: motion and mission cancelled"):
        active = self.owner is not None or self.mission.status != "idle"
        self.halt()
        self.owner = None
        self.manual_collision_command = None
        self.mission.reset(reason, outcome="cancelled")
        if active:
            self.log("warning", reason)

    def collision_stop(self, autonomous):
        """Record one warning per collision episode; never invent a manual mission."""
        source = "Autonomous navigation" if autonomous else "Manual motion"
        if not autonomous:
            self.manual_collision_command = (self.owner, self.linear, self.angular)
        x, y = self.state.pose[:2]
        reason = (f"{source} collision prevented at ({x:.2f}, {y:.2f}) m: "
                  f"{self.grid.clearance:.3f} m footprint clearance required. Motion stopped. ")
        if not self.grid.free(x, y):
            reason += "Current pose is obstructed; restore map clearance before moving."
        elif autonomous:
            reason += "STOP/cancel to clear the failed mission, or plan a new safe route."
        else:
            reason += "Release input and drive away from the obstacle."
        self.halt()
        self.owner = None
        if autonomous:
            self.mission.status, self.mission.reason = "blocked", reason
        if self.collision_origin is None or self.collision_source != source:
            self.log("warning", reason)
            self.collision_origin = (x, y)
            self.collision_source = source

    def release(self, client, reason="Manual input released"):
        if self.manual_collision_command and self.manual_collision_command[0] == client:
            self.manual_collision_command = None
        if self.owner == client and not self.mission.active:
            self.halt()
            self.owner = None
            self.log("info", reason)

    def disconnect(self, client):
        if self.manual_collision_command and self.manual_collision_command[0] == client:
            self.manual_collision_command = None
        if self.owner != client:
            return
        if self.mission.active:
            self.halt()
            self.owner = None
            self.mission.status = "paused"
            self.mission.reason = "Controller disconnected. Resume explicitly to continue."
            self.log("warning", self.mission.reason)
        else:
            self.release(client, "Controller disconnected. Commands cleared.")

    def command(self, command, client: str):
        if isinstance(command, WaypointCommand):
            if command.action == "save":
                self.mission.save(command.name, command.goal)
                self.log("info", f"Waypoint {command.name} saved")
            else:
                self.mission.waypoints.pop(command.name, None)
                self.log("info", f"Waypoint {command.name} deleted")
            return True
        if isinstance(command, NavigationCommand):
            return self.navigate(command, client)
        if command.type == "stop":
            self.stop()
            return True
        if command.type == "release":
            self.release(client)
            return True
        if command.type == "heartbeat":
            if self.owner == client:
                self.last_lease = time.monotonic()
            return True
        if self.mission.active or self.owner not in (None, client):
            return False
        # A held input cannot repeatedly restart after its collision stop.
        if self.manual_collision_command == (client, command.linear, command.angular):
            return True
        self.manual_collision_command = None
        if command.linear == 0 and command.angular == 0:
            self.release(client)
            return True
        if self.mission.status != "idle":
            self.mission.reset("Mission cleared for manual control", outcome="cancelled")
        if self.owner is None and self.collision_origin is None:
            self.log("info", "Manual simulation command engaged (40 RPM wheel limit)")
        self.owner = client
        self.linear, self.angular = command.linear, command.angular
        self.last_command = time.monotonic()
        return True

    def navigate(self, command, client):
        action = command.action
        if action == "cancel":
            self.stop("Navigation cancelled")
            return True
        if self.owner not in (None, client) or (self.owner is not None and not self.mission.active):
            return False
        if action == "pause":
            if self.mission.status != "running":
                raise ValueError("Only a running mission can be paused")
            self.halt()
            self.mission.status, self.mission.reason = "paused", "Navigation paused"
        elif action == "resume":
            if self.mission.status != "paused":
                raise ValueError("Only a paused mission can be resumed")
            # Replan remaining legs from current actual pose; no teleport or stale path.
            self.mission.replan_remaining(self.state.pose)
            self.owner = client
            self.last_lease = time.monotonic()
        else:
            if self.mission.active:
                raise ValueError("Cancel the current mission before planning another")
            goals = (self.mission.sequence(command.waypoints) if action == "sequence" else
                     [Goal(x=HOME[0], y=HOME[1], yaw=HOME[2], name="Home")] if action == "home" else [command.goal])
            self.mission.prepare(self.state.pose, goals)
            if action != "plan":
                self.mission.status, self.mission.reason = "running", "Following simulated grid path"
                self.owner = client
                self.last_lease = time.monotonic()
        self.log("info", f"Navigation {action}: {self.mission.reason}")
        return True

    def targets(self):
        return self.drive.inverse(self.linear, self.angular)

    def tick(self, dt=0.1):
        if not 0 < dt <= 1:
            raise ValueError("Simulation timestep must be in (0, 1]")
        if self.owner is not None:
            if self.mission.active:
                if time.monotonic() - self.last_lease >= AUTONOMOUS_TIMEOUT:
                    self.disconnect(self.owner)
                    self.mission.reason = "Controller heartbeat expired. Mission paused."
                    self.log("warning", self.mission.reason)
            elif time.monotonic() - self.last_command >= COMMAND_TIMEOUT:
                self.release(self.owner, "Command watchdog expired. Commands cleared.")
        steps = math.ceil(dt / 0.02)
        step = dt / steps
        for _ in range(steps):
            if self.mission.status == "running":
                if not self.grid.free(*self.state.pose[:2]):
                    self.collision_stop(autonomous=True)
                    break
                self.linear, self.angular = self.mission.follow(self.state.pose)
                if self.mission.status == "completed":
                    self.halt()
                    self.owner = None
                    self.log("info", self.mission.reason)
                    self.mission.reset(self.mission.reason, outcome="completed")
            target = self.targets()
            actual = self.drive.accelerate(self.rpm, target, step)
            average = [(old + new) / 2 for old, new in zip(self.rpm, actual)]
            next_pose = self.drive.integrate(self.state.pose, average, step)
            moving = any(abs(rpm) > 1e-12 for rpm in average)
            if moving and not self.grid.segment_free(self.state.pose, next_pose):
                self.collision_stop(autonomous=self.mission.status == "running")
                break
            self.state.pose = next_pose
            self.state.rpm = actual
            for i in range(2):
                self.counts[i] += average[i] * self.drive.config.encoder_cpr * step / 60
            if self.collision_origin is not None and math.dist(self.state.pose[:2], self.collision_origin) >= 0.1:
                self.collision_origin = self.collision_source = None
        point = self.state.pose[:2]
        if math.dist(self.state.trajectory[-1], point) > 0.015:
            self.state.trajectory.append(point)

    def snapshot(self):
        return snapshot(self)
