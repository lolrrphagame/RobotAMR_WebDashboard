"""Single authoritative physical state; no frontend-side pose integration."""
from collections import deque
from dataclasses import dataclass, field

HOME = (1.0, 1.0, 0.0)
CHASSIS_SIZE = 0.250


@dataclass
class RobotState:
    pose: tuple[float, float, float] = HOME
    rpm: list[float] = field(default_factory=lambda: [0.0, 0.0])
    counts: list[float] = field(default_factory=lambda: [0.0, 0.0])
    trajectory: deque = field(default_factory=lambda: deque([HOME[:2]], maxlen=1200))
