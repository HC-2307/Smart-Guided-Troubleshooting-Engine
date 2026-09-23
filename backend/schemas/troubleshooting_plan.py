"""Pydantic data models for Stage 2 Troubleshooting Plan conforming to official schema.py."""
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Condition(str, Enum):
    greater = "greater"
    equal = "equal"
    less = "less"


class ResultTypes(str, Enum):
    boolean = "boolean"
    intNum = "integer"
    string = "str"
    floatNum = "float"


class ActionCategory(str, Enum):
    auto = "auto"
    manual = "manual"
    critical = "critical"


# Alias matching exact casing from schema.py
actionCategory = ActionCategory


class BaseDeeplink(BaseModel):
    deeplink: str


class Deeplink(BaseDeeplink):
    description: str
    message: Optional[str] = ""
    classes: Optional[Dict[str, str]] = None
    originalType: Optional[str] = None


class ValidationDeepLink(BaseDeeplink):
    key: str
    resultType: Optional[ResultTypes] = None
    condition: Optional[Condition] = None
    value: Optional[str] = None


class StepGroup(BaseModel):
    steps: List[str]
    validationDeeplink: Optional[ValidationDeepLink] = None
    actionableDeeplink: Optional[Deeplink] = None


class Action(BaseModel):
    actionName: str
    description: str
    stepGroups: List[StepGroup]
    category: Optional[ActionCategory] = ActionCategory.manual


class Goal(BaseModel):
    goal: str
    title: str
    actions: List[Action]
    score: float


class TroubleshootingPlan(BaseModel):
    """Troubleshooting plan returned by M1 containing contexts (list of Goal objects)."""
    contexts: List[Goal] = Field(default_factory=list)
    query_variations: Optional[List[str]] = Field(default_factory=list)


# Alias conforming to official schema ContextDeeplinkResponse
class ContextDeeplinkResponse(BaseModel):
    """RAG response containing a list of Goal objects."""
    contexts: List[Goal] = []
