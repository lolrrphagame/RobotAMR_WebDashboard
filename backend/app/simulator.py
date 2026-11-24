"""Single simulation coordinator: arbitration, plant stepping and mission safety."""
import math
import json
import time
from collections import deque
from datetime import datetime, timezone
from uuid import uuid4
from .drive import DriveConfig, WHEEL_RADIUS, WHEEL_SEPARATION, ENCODER_CPR
from .mission import MissionManager
from .models import ControlCommand, NavigationCommand, Goal, WaypointCommand, ConfigurationCommand, WheelConstraints
from .navigation import OccupancyGrid
from .state import HOME, RobotState
from .telemetry import snapshot
from .configuration import ConfigurationManager, ConfigurationError, ConfigurationConflict, default_autonomous_speed_limits
from .diagnostics import history_sample
from .sensors.manager import SensorManager
from .operations import Operations, OperationsCommand

COMMAND_TIMEOUT = 0.6
AUTONOMOUS_TIMEOUT = 1.5


class RobotSimulator:
    def __init__(self, config: DriveConfig | None = None, grid=None, store=None, operations_store=None):
        self.session_id = uuid4().hex
        self.started = time.monotonic()
        self.sample_timestamp = datetime.now(timezone.utc).isoformat()
        self.sample_uptime = 0.0
        self.inhibited_clients = set()
        # A safety halt can stop the wheels before the controlling input is released.
        self.manual_release_pending = set()
        self.last_command = self.last_lease = 0.0
        self.owner = None
        self.linear = self.angular = 0.0
        self.state = RobotState()
        self.grid = grid or OccupancyGrid()
        self.configuration = ConfigurationManager(self.grid, store, config)
        self.drive = self.configuration.drive
        home = self.configuration.value.home
        self.state = RobotState(pose=(home.x, home.y, home.yaw),
                                trajectory=deque([(home.x, home.y)], maxlen=1200))
        self.mission = MissionManager(self.grid)
        self.mission.waypoints = self.configuration.value.waypoints
        self.collision_origin = None
        self.collision_source = None
        self.manual_collision_command = None
        self.events = deque(maxlen=60)
        self.event_id = 0
        self.history = deque(maxlen=600)
        self.safety = {"stop_active": False, "last_stop_reason": None, "watchdog": "idle"}
        self.counters = {"control_commands": 0, "navigation_commands": 0, "configuration_commands": 0,
                         "stop_commands": 0, "rejected_commands": 0, "watchdog_expirations": 0,
                         "collisions": 0, "ws_rx_frames": 0}
        self.sensors = SensorManager(self.grid, self.state.pose, self.sample_timestamp)
        self.log("info", "Navigation simulator initialized. All hardware interfaces disabled.")
        for warning in self.configuration.warnings:
            self.log("warning", warning)
        self.operations = Operations(self, operations_store)
        self.history.append(history_sample(self.snapshot()))

    @property
    def rpm(self):
        return self.state.rpm

    @property
    def counts(self):
        return self.state.counts

    @property
    def autonomous_active(self):
        return self.mission.active or (hasattr(self,"operations") and self.operations.active)

    @property
    def mode(self):
        return "AUTONOMOUS" if self.autonomous_active else "MANUAL" if self.owner else "STANDBY"

    def log(self, level, message):
        self.event_id += 1
        self.events.appendleft({"id": self.event_id, "time": datetime.now(timezone.utc).isoformat(),
                                "level": level, "message": message})

    def halt(self):
        self.linear = self.angular = 0.0
        self.state.rpm = [0.0, 0.0]

    def stop(self, reason="STOP: motion and mission cancelled"):
        self.safety["stop_generation"] = self.safety.get("stop_generation",0)+1
        self.safety.update(stop_active=True, last_stop_reason=reason, watchdog="disarmed")
        self.counters["stop_commands"] += 1
        if self.owner is not None and not self.autonomous_active:
            self.manual_release_pending.add(self.owner)
        self.halt()
        if self.owner is not None:self.inhibited_clients.add(self.owner)
        self.operations.finish("cancelled",reason)
        active = self.owner is not None or self.mission.status != "idle"
        self.halt()
        self.owner = None
        self.manual_collision_command = None
        self.mission.reset(reason, outcome="cancelled")
        if active:
            self.log("warning", reason)

    def collision_stop(self, autonomous):
        """Record one warning per collision episode; never invent a manual mission."""
        self.safety["watchdog"] = "disarmed"
        self.counters["collisions"] += 1
        source = "Autonomous navigation" if autonomous else "Manual motion"
        if not autonomous:
            self.manual_collision_command = (self.owner, self.linear, self.angular)
            if self.owner is not None:
                self.manual_release_pending.add(self.owner)
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
        self.inhibited_clients.discard(client)
        self.manual_release_pending.discard(client)
        if self.manual_collision_command and self.manual_collision_command[0] == client:
            self.manual_collision_command = None
        if self.owner == client and not self.autonomous_active:
            self.halt()
            self.safety["watchdog"] = "disarmed"
            self.owner = None
            self.log("info", reason)

    def disconnect(self, client):
        self.inhibited_clients.discard(client)
        self.manual_release_pending.discard(client)
        if self.manual_collision_command and self.manual_collision_command[0] == client:
            self.manual_collision_command = None
        if self.owner != client:
            return
        self.safety["watchdog"] = "disconnected"
        if self.operations.active:
            self.operations.pause("Controller disconnected or heartbeat expired; explicit resume required",release=True)
            return
        if self.autonomous_active:
            self.halt()
            self.owner = None
            self.mission.status = "paused"
            self.mission.reason = "Controller disconnected. Resume explicitly to continue."
            self.log("warning", self.mission.reason)
        else:
            self.release(client, "Controller disconnected. Commands cleared.")
            self.safety["watchdog"] = "disconnected"

    def command(self, command, client: str):
        if isinstance(command, OperationsCommand):
            if command.action=='start_next':self.operations.start(client)
            elif command.action=='resume':self.operations.resume(client)
            elif command.action=='cancel':self.stop('Operations mission cancelled')
            else:
                if self.owner!=client or not self.operations.active:raise ValueError('Only the current operator can pause this mission')
                self.operations.pause()
            return True
        if isinstance(command, ConfigurationCommand):
            if command.action == "set_autonomous_speed_limits":
                return self.configure_motion(command.autonomous_speed_limits)
            if command.action == "set_motion_settings":
                return self.configure_motion(command.autonomous_speed_limits, command.wheel_constraints)
            if command.action == "restore_motion_defaults":
                return self.configure_motion(default_autonomous_speed_limits(), WheelConstraints())
            return self.configure_home(command)
        if isinstance(command, WaypointCommand):
            self.counters["configuration_commands"] += 1
            points = dict(self.configuration.value.waypoints)
            if command.action == "save":
                points[command.name] = command.goal.model_copy(update={"name": command.name})
            else:
                points.pop(command.name, None)
            try:
                self.configuration.commit(waypoints=points)
            except ValueError as exc:
                raise ConfigurationError(str(exc)) from exc
            self.mission.waypoints = self.configuration.value.waypoints
            self.log("info", f"Waypoint {command.name} {command.action} committed")
            return True
        if isinstance(command, NavigationCommand):
            self.counters["navigation_commands"] += 1
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
        self.counters["control_commands"] += 1
        if self.autonomous_active or self.owner not in (None, client):
            self.counters["rejected_commands"] += 1
            return False
        if client in self.inhibited_clients:return False
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
            self.log("info", f"Manual simulation command engaged ({self.drive.config.max_rpm:g} RPM wheel limit)")
        self.safety.update(stop_active=False, watchdog="armed_manual")
        self.owner = client
        self.linear, self.angular = command.linear, command.angular
        self.last_command = time.monotonic()
        return True

    def configure_home(self, command):
        self.counters["configuration_commands"] += 1
        if self.autonomous_active:
            raise ConfigurationConflict("Home cannot change during a running or paused mission. Cancel the mission first.")
        home = (Goal(x=HOME[0], y=HOME[1], yaw=HOME[2], name="Home") if command.action == "reset_home" else
                Goal(x=self.state.pose[0], y=self.state.pose[1], yaw=self.state.pose[2], name="Home")
                if command.action == "current_home" else command.goal.model_copy(update={"name": "Home"}))
        try:
            self.configuration.commit(home=home)
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc
        self.log("info", f"Home saved at ({home.x:.2f}, {home.y:.2f}), yaw {home.yaw:.2f} rad. Robot pose unchanged.")
        return True

    def autonomous_limits_blocked_reason(self) -> str | None:
        if self.operations.active:
            return "Motion settings cannot change during an active Mission Operations reservation, including a running or paused mission or a WAIT step."
        if self.autonomous_active:
            return "Motion settings cannot change during a running or paused mission."
        if self.owner is not None or self.manual_release_pending or self.linear or self.angular or any(self.rpm):
            return "Release manual input and wait for the simulated robot to stop before saving."
        return None

    def configure_motion(self, limits=None, wheel_constraints=None):
        self.counters["configuration_commands"] += 1
        if reason := self.autonomous_limits_blocked_reason():
            raise ConfigurationConflict(reason)
        try:
            self.configuration.commit(autonomous_speed_limits=limits, wheel_constraints=wheel_constraints)
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc
        self.log("info", "Motion settings saved for simulation.")
        return True

    def navigate(self, command, client):
        action = command.action
        if self.operations.active:
            if action=='cancel':self.stop('Navigation cancel: operations mission cancelled');return True
            if action=='pause' and self.owner==client:self.operations.pause();return True
            if action=='resume':self.operations.resume(client);return True
            raise ValueError('Mission Operations owns navigation; cancel it before starting a map mission')
        if action == "cancel":
            self.stop("Navigation cancelled")
            return True
        if self.owner not in (None, client) or (self.owner is not None and not self.autonomous_active):
            self.counters["rejected_commands"] += 1
            return False
        if action == "pause":
            if self.mission.status != "running":
                raise ValueError("Only a running mission can be paused")
            self.halt()
            self.mission.status, self.mission.reason = "paused", "Navigation paused"
            self.safety["watchdog"] = "paused"
        elif action == "resume":
            if self.mission.status != "paused":
                raise ValueError("Only a paused mission can be resumed")
            # Replan remaining legs from current actual pose; no teleport or stale path.
            self.mission.replan_remaining(self.state.pose)
            self.owner = client
            self.last_lease = time.monotonic()
            self.safety.update(stop_active=False, watchdog="armed_autonomous")
        else:
            if self.autonomous_active:
                raise ValueError("Cancel the current mission before planning another")
            goals = (self.mission.sequence(command.waypoints) if action == "sequence" else
                     [self.configuration.value.home.model_copy()] if action == "home" else [command.goal])
            self.mission.prepare(self.state.pose, goals)
            if action != "plan":
                self.mission.status, self.mission.reason = "running", "Following simulated grid path"
                self.owner = client
                self.last_lease = time.monotonic()
                self.safety.update(stop_active=False, watchdog="armed_autonomous")
        self.log("info", f"Navigation {action}: {self.mission.reason}")
        return True

    def drive_request(self) -> tuple[float, float, bool]:
        """Apply both autonomous caps with one scale so the requested curvature is preserved."""
        divisor = 1.0
        if self.autonomous_active:
            limits = self.configuration.value.autonomous_speed_limits
            divisor = max(divisor, abs(self.linear) / limits.max_linear,
                          abs(self.angular) / limits.max_angular)
        return self.linear / divisor, self.angular / divisor, divisor > 1.0

    def targets(self):
        linear, angular, _ = self.drive_request()
        return self.drive.inverse(linear, angular)

    def tick(self, dt=0.1):
        if not 0 < dt <= 1:
            raise ValueError("Simulation timestep must be in (0, 1]")
        if self.owner is not None:
            if self.autonomous_active:
                if time.monotonic() - self.last_lease >= AUTONOMOUS_TIMEOUT:
                    self.disconnect(self.owner)
                    self.mission.reason = "Controller heartbeat expired. Mission paused."
                    self.log("warning", self.mission.reason)
                    self.safety["watchdog"] = "expired"
                    self.counters["watchdog_expirations"] += 1
            elif time.monotonic() - self.last_command >= COMMAND_TIMEOUT:
                self.release(self.owner, "Command watchdog expired. Commands cleared.")
                self.safety["watchdog"] = "expired"
                self.counters["watchdog_expirations"] += 1
        previous_pose = self.state.pose
        self.operations.before_tick(dt)
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
                    if not self.operations.active:self.owner = None
                    self.log("info", self.mission.reason)
                    self.mission.reset(self.mission.reason, outcome="completed")
                    if self.operations.active:self.operations.complete_step()
                    else:self.safety["watchdog"] = "disarmed"
            target = self.targets()
            actual = self.drive.accelerate(self.rpm, target, step)
            average = [(old + new) / 2 for old, new in zip(self.rpm, actual)]
            next_pose = self.drive.integrate(self.state.pose, average, step)
            moving = any(abs(rpm) > 1e-12 for rpm in average)
            if moving and not self.grid.segment_free(self.state.pose, next_pose):
                self.collision_stop(autonomous=self.mission.status == "running")
                break
            if self.operations.current and self.operations.current["status"]=="running":
                self.operations.current["distance"] += math.dist(self.state.pose[:2],next_pose[:2])
            self.state.pose = next_pose
            self.state.rpm = actual
            for i in range(2):
                self.counts[i] += average[i] * self.drive.config.encoder_cpr * step / 60
            if self.collision_origin is not None and math.dist(self.state.pose[:2], self.collision_origin) >= 0.1:
                self.collision_origin = self.collision_source = None
        self.operations.after_tick(dt, previous_pose)
        point = self.state.pose[:2]
        if math.dist(self.state.trajectory[-1], point) > 0.015:
            self.state.trajectory.append(point)

        self.sample_timestamp = datetime.now(timezone.utc).isoformat()
        self.sample_uptime = time.monotonic() - self.started
        sensor_error = self.sensors.step(dt, self.state.pose, self.sample_timestamp, time.monotonic())
        if sensor_error:
            self.log("error", sensor_error)
        self.history.append(history_sample(self.snapshot()))

    def broadcast_snapshot(self):
        # One encoded-state preparation per physics update/transition, shared by observers.
        key=(self.sample_timestamp,self.event_id,self.owner,self.mission.status,self.safety.get('stop_generation',0))
        if getattr(self,'_broadcast_key',None)!=key:
            self._broadcast_frame=self.snapshot();self._broadcast_key=key
        return self._broadcast_frame

    def broadcast_text(self):
        """Encode once per authoritative frame, shared by every telemetry consumer."""
        frame=self.broadcast_snapshot()
        if getattr(self,'_broadcast_text_frame',None) is not frame:
            self._broadcast_text=json.dumps(frame,ensure_ascii=False,allow_nan=False,separators=(',',':'))
            self._broadcast_text_frame=frame
        return self._broadcast_text

    def snapshot(self):
        return snapshot(self)
