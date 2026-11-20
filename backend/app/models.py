from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class ControlCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    type: Literal["control", "stop"]
    linear: float = Field(default=0, ge=-0.6, le=0.6)
    angular: float = Field(default=0, ge=-2, le=2)
