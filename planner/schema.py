from typing import Any, Dict, List
from pydantic import BaseModel, Field, ConfigDict


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_label: str
    api_call: str
    args: Dict[str, Any] = Field(default_factory=dict)
    expected_state: Dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: str
    slots: Dict[str, Any] = Field(default_factory=dict)
    steps: List[Step]
    sources: List[str] = Field(default_factory=list)
    confidence: float
