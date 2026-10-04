from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=10)


class AgentRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    max_steps: int | None = Field(default=None, ge=1, le=12)


class CitationOut(BaseModel):
    n: int
    chunk_id: int
    doc_id: str
    ordinal: int
    text: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    run_id: str
    latency_ms: float


class StepOut(BaseModel):
    n: int
    thought: str
    tool: str
    args: dict
    observation: str


class AgentResponse(QueryResponse):
    steps: list[StepOut]
    fallback_used: bool
    parse_failures: int
