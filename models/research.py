"""Versioned research contracts; source text is data, never instructions."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Requirement(BaseModel):
    id: str
    text: str


class Support(BaseModel):
    model_config = ConfigDict(extra='forbid')
    evidence_id: str
    quote: str = Field(min_length=1)
    relation: Literal['supports', 'contradicts'] = 'supports'


class Claim(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    text: str = Field(min_length=1, max_length=3000)
    supports: list[Support] = Field(default_factory=list, max_length=12)


class AnswerSection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question_id: str
    claims: list[Claim] = Field(default_factory=list, max_length=12)
    gaps: list[str] = Field(default_factory=list, max_length=8)


class StructuredReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = 1
    sections: list[AnswerSection] = Field(min_length=1, max_length=8)


class ClaimVerdict(BaseModel):
    claim_id: str
    status: Literal['supported', 'unsupported', 'conflicting', 'uncertain']
    explanation: str = Field(min_length=1)
    temporal_applicability: Literal['confirmed', 'unknown', 'not_applicable'] = 'unknown'


class SectionVerdict(BaseModel):
    question_id: str
    complete: bool
    explanation: str = Field(min_length=1)
    next_queries: list[str] = Field(default_factory=list, max_length=2)


class SemanticReview(BaseModel):
    claims: list[ClaimVerdict]
    questions: list[SectionVerdict]
    task_compliant: bool
    issues: list[str] = Field(default_factory=list)
