from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class TopicInput(StrictModel):
    title: str = Field(min_length=3, max_length=300)
    reader_question: str = Field(min_length=5, max_length=2000)
    track: str = Field(min_length=2, max_length=120)
    priority: int = Field(default=0, ge=0, le=100)
    notes: str = Field(default='', max_length=10000)

class TopicEdit(TopicInput):
    expected_version: int
    archived: bool = False

class Brief(StrictModel):
    audience: str = Field(default='CEOs and managers', max_length=1000)
    scenario: str = Field(default='', max_length=3000)
    scope: str = Field(min_length=5, max_length=5000)
    exclusions: str = Field(default='', max_length=3000)
    target_words: int = Field(default=800, ge=400, le=2000)
    diagram: bool = True
    source_urls: list[str] = Field(default_factory=list, max_length=20)

    @field_validator('source_urls')
    @classmethod
    def urls(cls, values):
        from app.services.content_policy import safe_url
        if any(not safe_url(value) for value in values):
            raise ValueError('Sources must be public HTTPS URLs.')
        return values

class BriefEdit(StrictModel):
    expected_version: int
    brief: Brief

class RunInput(StrictModel):
    provider: Literal["openai", "gemini"] = "openai"
    stage: Literal['research', 'generate', 'qa', 'fix']
    request_key: str = Field(min_length=10, max_length=100)
    expected_version: int
    version_id: int | None = None

class DraftPayload(StrictModel):
    title: str = Field(min_length=3, max_length=300)
    slug: str = Field(min_length=3, max_length=180, pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    content: str = Field(min_length=100, max_length=100000)
    excerpt: str = Field(min_length=10, max_length=1000)
    meta_description: str = Field(min_length=10, max_length=300)
    tags: list[str] = Field(max_length=8)
    diagram_alt: str = Field(max_length=1000)
    unresolved_claims: list[str] = Field(max_length=30)
    seo_title: str = Field(default='', max_length=300)
    category: str = Field(default='', max_length=120)
    subcategory: str = Field(default='', max_length=120)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    language: str = Field(default='en', max_length=20)
    schema_type: Literal['Article', 'BlogPosting', 'TechArticle'] = 'Article'
    open_graph_title: str = Field(default='', max_length=300)
    open_graph_description: str = Field(default='', max_length=1000)

class VersionInput(StrictModel):
    expected_version: int
    base_version_id: int
    payload: DraftPayload

class SaveDraftInput(StrictModel):
    expected_version: int
    version_id: int
    article_fingerprint: str | None = None

class ImportInput(StrictModel):
    csv_text: str = Field(max_length=2_000_000)
    apply: bool = False

class EvidenceClaim(StrictModel):
    claim: str
    source_urls: list[str]
    evidence: str
    qualification: str

class ResearchPackage(StrictModel):
    summary: str
    claims: list[EvidenceClaim]
    gaps: list[str]
    ready: bool

class Finding(StrictModel):
    severity: Literal['error', 'warning', 'info']
    category: str
    message: str

class QAOutput(StrictModel):
    findings: list[Finding]
