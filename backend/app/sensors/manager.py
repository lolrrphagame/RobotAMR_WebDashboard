"""One bounded sensor cache, stepped by the existing robot simulation clock."""
import time
import math
from .lidar import VirtualLidar
from .camera import PlaceholderCamera


class SensorManager:
    def __init__(self, grid, pose, timestamp, now=None):
        self.lidar = VirtualLidar(grid)
        self.camera = PlaceholderCamera()
        self.elapsed = 0.0
        self.last_reported_error = None
        self.update(pose, timestamp, time.monotonic() if now is None else now)

    def update(self, pose, timestamp, now):
        try:
            self.lidar.capture(tuple(pose), timestamp, now)
        except Exception:
            # A visualization adapter failure must not disable STOP or physics.
            self.lidar.error = "Virtual LiDAR scan generation failed; robot control and collision guard remain independent."

    def step(self, dt, pose, timestamp, now):
        self.elapsed += dt
        interval = 1 / self.lidar.config.update_hz
        if self.elapsed + 1e-9 >= interval:
            periods = math.floor((self.elapsed + 1e-9) / interval)
            self.elapsed = max(0.0, self.elapsed - periods * interval)
            self.update(pose, timestamp, now)
        error = self.lidar.error
        report = error if error and error != self.last_reported_error else None
        self.last_reported_error = error
        return report

    def snapshot(self, include_data=True, now=None):
        now = time.monotonic() if now is None else now
        return {"lidar": self.lidar.snapshot(now, include_data),
                "camera": self.camera.snapshot(now, include_data)}
