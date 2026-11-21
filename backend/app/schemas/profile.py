from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
ListItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]

class Experience(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: ShortText
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] = ""

class ProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    real_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    undergraduate_school: ShortText | None = None
    undergraduate_major: ShortText | None = None
    undergraduate_degree: ListItem | None = None
    graduate_school: ShortText | None = None
    graduate_major: ShortText | None = None
    graduation_year: int | None = Field(default=None, ge=1900, le=2100, strict=True)
    target_position: ShortText | None = None
    interested_industries: list[ListItem] = Field(default_factory=list, max_length=30)
    skills: list[ListItem] = Field(default_factory=list, max_length=30)
    internship_experience: list[Experience] = Field(default_factory=list, max_length=20)
    project_experience: list[Experience] = Field(default_factory=list, max_length=20)

class ProfileRead(ProfileWrite):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
