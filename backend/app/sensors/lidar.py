"""Deterministic, point-origin grid raycasting; independent of robot dynamics."""
import math
from dataclasses import dataclass
from .contracts import Freshness, SensorFrame


@dataclass(frozen=True)
class VirtualLidarConfig:
    beam_count: int = 181
    field_of_view: float = math.pi
    range_max: float = 5.0
    update_hz: float = 5.0

    def __post_init__(self):
        if not isinstance(self.beam_count, int) or not 2 <= self.beam_count <= 361:
            raise ValueError("Virtual LiDAR requires 2–361 beams")
        if not 0 < self.field_of_view <= 2 * math.pi:
            raise ValueError("Virtual LiDAR field of view must be in (0, 2π]")
        if not 0 < self.range_max <= 20 or not 0 < self.update_hz <= 5:
            raise ValueError("Virtual LiDAR range must be <=20 m and rate <=5 Hz")


def raycast(grid, x, y, angle, range_max=5.0):
    """Return (distance_m, hit). Outside/unknown/occupied cells stop the ray.

    DDA traverses exact cell boundaries. Corner ties check both adjacent cells
    so a grazing occupied corner cannot disappear between marching samples.
    A no-return uses finite range_max plus hit=False, never Infinity/NaN.
    """
    if not all(math.isfinite(v) for v in (x, y, angle, range_max)) or range_max <= 0:
        raise ValueError("Ray inputs must be finite and maximum range positive")
    cx, cy = grid.cell((x, y))

    def occupied(ix, iy):
        return not (0 <= ix < grid.width and 0 <= iy < grid.height) or grid.data[iy * grid.width + ix] != 0

    if occupied(cx, cy):
        return 0.0, True
    dx, dy = math.cos(angle), math.sin(angle)
    dx = 0.0 if abs(dx) < 1e-12 else dx
    dy = 0.0 if abs(dy) < 1e-12 else dy
    sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
    size = grid.resolution
    tx = max(0.0, (grid.origin[0] + (cx + (dx > 0)) * size - x) / dx) if dx else math.inf
    ty = max(0.0, (grid.origin[1] + (cy + (dy > 0)) * size - y) / dy) if dy else math.inf
    delta_x, delta_y = (size / abs(dx) if dx else math.inf), (size / abs(dy) if dy else math.inf)
    for _ in range(grid.width + grid.height + 2):
        distance = min(tx, ty)
        if distance > range_max:
            return range_max, False
        if math.isclose(tx, ty, rel_tol=0, abs_tol=1e-10):
            if occupied(cx + sx, cy) or occupied(cx, cy + sy):
                return distance, True
            cx, cy = cx + sx, cy + sy
            tx, ty = tx + delta_x, ty + delta_y
        elif tx < ty:
            cx, tx = cx + sx, tx + delta_x
        else:
            cy, ty = cy + sy, ty + delta_y
        if occupied(cx, cy):
            return distance, True
    raise RuntimeError("Grid ray traversal exceeded finite cell budget")


class VirtualLidar:
    def __init__(self, grid, config=None):
        self.grid, self.config = grid, config or VirtualLidarConfig()
        c = self.config
        self.frame = SensorFrame(sensor_type="lidar_2d", source="SIMULATED", status="INITIALIZING",
            frame_id="virtual_laser", metadata={"beam_count": c.beam_count,
                "angle_min": -c.field_of_view / 2, "angle_max": c.field_of_view / 2,
                "angle_increment": c.field_of_view / (c.beam_count - 1), "range_min": 0.0,
                "range_max": c.range_max, "scan_time": 1 / c.update_hz, "time_increment": 0.0,
                "nominal_hz": c.update_hz, "min_obstacle_distance": None, "hit_count": 0,
                "units": {"range": "m", "angle": "rad"}, "map_frame": grid.frame_id,
                "mount": {"x": 0.0, "y": 0.0, "yaw": 0.0}},
            interface={"connection_state": "DISABLED", "planned_topic": "/scan",
                       "message_types": ["sensor_msgs/LaserScan"],
                       "note": "Virtual grid scan, not a ROS message or physical LiDAR specification."})
        self.last_update = None
        self.error = None

    def capture(self, pose, timestamp, now):
        x, y, yaw = tuple(pose)
        c = self.config
        ranges, hits = [], []
        for i in range(c.beam_count):
            angle = yaw - c.field_of_view / 2 + i * c.field_of_view / (c.beam_count - 1)
            distance, hit = raycast(self.grid, x, y, angle, c.range_max)
            ranges.append(round(max(0.0, min(c.range_max, distance)), 4))
            hits.append(hit)
        detected = [distance for distance, hit in zip(ranges, hits) if hit]
        self.frame = self.frame.model_copy(update={"status": "READY", "timestamp": timestamp,
            "sequence": self.frame.sequence + 1,
            "metadata": {**self.frame.metadata, "min_obstacle_distance": min(detected) if detected else None,
                         "hit_count": sum(hits)},
            "payload": {"ranges": ranges, "hits": hits,
                        "acquisition_pose": {"x": x, "y": y, "yaw": yaw, "frame_id": self.grid.frame_id}}})
        self.last_update, self.error = now, None

    def snapshot(self, now, include_data=True):
        age = max(0.0, (now - self.last_update) * 1000) if self.last_update is not None else None
        stale = age is None or age > 1000
        status = "ERROR" if self.error else "STALE" if stale and self.last_update is not None else self.frame.status
        frame = self.frame.model_copy(update={"status": status, "error": self.error,
            "freshness": Freshness(age_ms=round(age, 1) if age is not None else None, stale=stale)})
        result = frame.model_dump(exclude={"payload"} if not include_data else set())
        if self.error and include_data:
            result["payload"] = None
        return result
