"""Differential drive math in SI units. +x forward, +yaw CCW, both wheels +forward."""
import math
from dataclasses import dataclass

WHEEL_RADIUS = 0.0435
WHEEL_SEPARATION = 0.300
ENCODER_CPR = 3960
MAX_RPM = 40.0


def wrap_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


@dataclass(frozen=True)
class DriveConfig:
    wheel_radius: float = WHEEL_RADIUS
    wheel_separation: float = WHEEL_SEPARATION
    encoder_cpr: int = ENCODER_CPR
    max_rpm: float = MAX_RPM
    acceleration_rpm_s: float = 60.0
    encoder_polarity: tuple[int, int] = (1, -1)

    def __post_init__(self):
        if min(self.wheel_radius, self.wheel_separation, self.encoder_cpr,
               self.max_rpm, self.acceleration_rpm_s) <= 0:
            raise ValueError("Drive parameters must be positive")
        if len(self.encoder_polarity) != 2 or any(sign not in (-1, 1) for sign in self.encoder_polarity):
            raise ValueError("Encoder polarity must be +1 or -1")


class DifferentialDrive:
    def __init__(self, config: DriveConfig | None = None):
        self.config = config or DriveConfig()

    def unlimited(self, linear: float, angular: float) -> list[float]:
        c = self.config
        return [(linear + sign * angular * c.wheel_separation / 2)
               * 60 / (2 * math.pi * c.wheel_radius) for sign in (-1, 1)]
    def inverse(self, linear: float, angular: float) -> list[float]:
        """Body twist -> wheel RPM; proportional saturation preserves curvature."""
        rpm = self.unlimited(linear, angular)
        scale = self.wheel_limit_divisor(rpm)
        return [r / scale for r in rpm]

    def wheel_limit_divisor(self, rpm: list[float]) -> float:
        return max(1.0, max(map(abs, rpm)) / self.config.max_rpm)

    def forward(self, rpm: list[float]) -> tuple[float, float]:
        left, right = [r * 2 * math.pi * self.config.wheel_radius / 60 for r in rpm]
        return (left + right) / 2, (right - left) / self.config.wheel_separation

    def accelerate(self, rpm: list[float], target: list[float], dt: float) -> list[float]:
        delta = self.config.acceleration_rpm_s * dt
        return [max(-self.config.max_rpm, min(self.config.max_rpm,
                actual + max(-delta, min(delta, desired - actual))))
                for actual, desired in zip(rpm, target)]

    def integrate(self, pose: tuple[float, float, float], rpm: list[float], dt: float):
        x, y, yaw = pose
        linear, angular = self.forward(rpm)
        next_yaw = yaw + angular * dt
        if abs(angular) < 1e-9:
            x += linear * math.cos(yaw) * dt
            y += linear * math.sin(yaw) * dt
        else:
            x += linear / angular * (math.sin(next_yaw) - math.sin(yaw))
            y -= linear / angular * (math.cos(next_yaw) - math.cos(yaw))
        return x, y, wrap_angle(next_yaw)
