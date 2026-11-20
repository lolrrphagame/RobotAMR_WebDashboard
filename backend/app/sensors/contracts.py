"""Transport-neutral adapter envelope for future LaserScan/Image conversions."""
from typing import Any, Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field


class Freshness(BaseModel):
    age_ms: float | None = None
    stale: bool = True
    timeout_ms: int = 1000


class SensorFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    sensor_type: Literal["lidar_2d", "camera"]
    source: Literal["SIMULATED", "PLACEHOLDER", "DISABLED"]
    status: Literal["INITIALIZING", "READY", "NOT_CONNECTED", "DISABLED", "STALE", "ERROR"]
    timestamp: str | None = None
    frame_id: str
    sequence: int = Field(default=0, ge=0)
    freshness: Freshness = Field(default_factory=Freshness)
    error: str | None = None
    metadata: dict[str, Any]
    interface: dict[str, Any]
    payload: dict[str, Any] | None = None


class SensorAdapter(Protocol):
    def snapshot(self, now: float, include_data: bool = True) -> dict: ...
