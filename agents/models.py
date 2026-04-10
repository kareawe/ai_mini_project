from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


AgentStatus = Literal["success", "partial", "failed"]
RelationshipType = Literal[
    "research_collab",
    "business_partnership",
    "supply_chain",
    "candidate_only",
]


class EvidenceItem(BaseModel):
    title: str
    url: str = ""
    source_type: Literal["paper", "news", "company", "patent", "rag_pdf", "other"]
    published_date: str | None = None
    company_names: List[str] = Field(default_factory=list)
    technology_names: List[str] = Field(default_factory=list)
    stance: Literal["positive", "negative", "neutral", "mixed"] = "neutral"
    snippet: str = ""
    content: str = ""
    relevance_score: float = 0.0
    confidence_score: float = 0.0
    relationship_type: RelationshipType | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ValidatedFact(BaseModel):
    claim: str
    technology: str
    company: str | None = None
    trl_signal: str | None = None
    threat_signal: str | None = None
    confidence: float
    evidence_ids: List[str] = Field(default_factory=list)
    evidence_summary: str
    source_types: List[str] = Field(default_factory=list)
    caveat: str = ""


class CompanyProfile(BaseModel):
    company_name: str
    role: Literal["competitor", "partner_candidate", "partner", "supplier", "unknown"] = "unknown"
    technologies: List[str] = Field(default_factory=list)
    relationship_type: RelationshipType = "candidate_only"
    summary: str = ""
    supporting_evidence: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    notes: str = ""


class AgentRunResult(BaseModel):
    agent_name: str
    status: AgentStatus
    retry_count: int = 0
    validation_passed: bool = False
    warnings: List[str] = Field(default_factory=list)
    raw_items: List[EvidenceItem] = Field(default_factory=list)
    validated_facts: List[ValidatedFact] = Field(default_factory=list)
    company_profiles: List[CompanyProfile] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)


class DraftResult(BaseModel):
    agent_name: str = "DraftGenerationAgent"
    status: AgentStatus
    retry_count: int = 0
    validation_passed: bool = False
    warnings: List[str] = Field(default_factory=list)
    markdown_report: str = ""


class FinalArtifactResult(BaseModel):
    markdown_path: str
    html_path: str
    pdf_path: str


class RunContext(BaseModel):
    root_dir: str
    data_dir: str
    outputs_dir: str
    user_query: str
    target_technologies: List[str]
    our_company: str  
    run_id: str


class SupervisorState(BaseModel):
    user_query: str
    target_technologies: List[str]
    status: Literal["running", "done", "failed"]
    rag_result: Optional[AgentRunResult] = None
    web_result: Optional[AgentRunResult] = None
    competitor_result: Optional[AgentRunResult] = None
    draft_result: Optional[DraftResult] = None
    final_result: Optional[FinalArtifactResult] = None