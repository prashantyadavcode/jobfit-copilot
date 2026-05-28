from pydantic import BaseModel, Field


class AnalyzeTextRequest(BaseModel):
    resume_text: str = Field(..., min_length=30)
    jd_text: str = Field(..., min_length=30)


class AnalyzeResponse(BaseModel):
    score: float
    matched_skills: list[str]
    missing_skills: list[str]
    suggestions: list[str]
    resume_summary: dict
    jd_summary: dict


class LatexSectionsRequest(BaseModel):
    latex_code: str = Field(..., min_length=20)


class LatexRewriteRequest(BaseModel):
    latex_code: str = Field(..., min_length=20)
    selected_section_ids: list[str] = Field(default_factory=list)
    jd_text: str = Field(..., min_length=30)
    missing_skills: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
