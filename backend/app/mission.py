"""Bounded in-memory waypoints, mission lifecycle and a simple point follower."""
import math
from .drive import wrap_angle
from .models import Goal
from .navigation import plan_path


class MissionManager:
    def __init__(self, grid):
        self.grid = grid
        self.waypoints: dict[str, Goal] = {}
        self.status = "idle"
        self.goals: list[Goal] = []
        self.legs = []
        self.leg = 0
        self.cursor = 1
        self.progress = 0.0
        self.reason = "Select a destination on the map"

    @property
    def active(self):
        return self.status in ("running", "paused")

    def save(self, name, goal):
        if not self.grid.free(goal.x, goal.y):
            raise ValueError("Waypoint is occupied or too close to an obstacle")
        self.waypoints[name] = goal.model_copy(update={"name": name})

    def sequence(self, names):
        if any(name not in self.waypoints for name in names):
            raise ValueError("Save every waypoint in the sequence first")
        return [self.waypoints[name].model_copy() for name in names]

    def prepare(self, pose, goals):
        # Plan every leg before changing mission state; a failed plan is atomic.
        legs, start = [], pose
        for goal in goals:
            legs.append(plan_path(self.grid, start, (goal.x, goal.y)))
            start = (goal.x, goal.y)
        self.goals, self.legs = goals, legs
        self.leg, self.cursor, self.progress = 0, 1, 0.0
        self.status, self.reason = "ready", "Collision-aware grid path ready"

    def replan_remaining(self, pose):
        legs, start = [], pose
        for goal in self.goals[self.leg:]:
            legs.append(plan_path(self.grid, start, (goal.x, goal.y)))
            start = (goal.x, goal.y)
        self.legs[self.leg:] = legs
        self.cursor = 1
        self.status, self.reason = "running", "Navigation resumed from actual pose"

    def follow(self, pose):
        if self.status != "running":
            return 0.0, 0.0
        x, y, yaw = pose
        path, goal = self.legs[self.leg], self.goals[self.leg]
        while self.cursor < len(path) and math.dist((x, y), path[self.cursor]) < 0.035:
            self.cursor += 1
        consumed = sum(len(p) for p in self.legs[:self.leg]) + self.cursor
        self.progress = min(99.0, max(self.progress, consumed / sum(map(len, self.legs)) * 100))
        if self.cursor >= len(path):
            error = wrap_angle(goal.yaw - yaw)
            if abs(error) > 0.035:
                return 0.0, max(-0.65, min(0.65, error * 2.2))
            if self.leg + 1 < len(self.legs):
                self.leg += 1
                self.cursor = 1
                return 0.0, 0.0
            self.status, self.progress = "completed", 100.0
            self.reason = "Mission complete; final heading reached"
            return 0.0, 0.0
        tx, ty = path[self.cursor]
        distance = math.hypot(tx - x, ty - y)
        error = wrap_angle(math.atan2(ty - y, tx - x) - yaw)
        # Turn before translating. Low speed and dense path points favor clearance.
        linear = min(0.13, distance * 1.3) if abs(error) < 0.30 else 0.0
        return linear, max(-0.8, min(0.8, 2.2 * error))

    def snapshot(self):
        goal = self.goals[self.leg] if self.goals else None
        return {"status": self.status, "progress": round(self.progress, 1), "reason": self.reason,
                "destination": goal.model_dump() if goal else None,
                "current_waypoint": goal.name if goal else None,
                "waypoint_index": self.leg + 1 if goal else 0, "waypoint_count": len(self.goals),
                "path": [[x, y] for leg in self.legs for x, y in leg],
                "waypoints": {name: value.model_dump() for name, value in self.waypoints.items()}}
