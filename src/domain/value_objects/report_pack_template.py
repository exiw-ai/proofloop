from enum import Enum

from pydantic import BaseModel


class ReportPackTemplate(str, Enum):
    GENERAL_DEFAULT = "general_default"
    ACADEMIC_REVIEW = "academic_review"
    MARKET_LANDSCAPE = "market_landscape"
    TECHNICAL_BEST_PRACTICES = "technical_best_practices"


class TemplateSpec(BaseModel, frozen=True):
    name: str
    required_files: list[str]


TEMPLATE_SPECS: dict[ReportPackTemplate, TemplateSpec] = {
    ReportPackTemplate.GENERAL_DEFAULT: TemplateSpec(
        name="General Default",
        required_files=[
            "executive_summary.md",
            "findings.md",
            "recommendations.md",
            "sources.md",
        ],
    ),
    ReportPackTemplate.ACADEMIC_REVIEW: TemplateSpec(
        name="Academic Review",
        required_files=[
            "abstract.md",
            "introduction.md",
            "methodology.md",
            "findings.md",
            "discussion.md",
            "gaps.md",
            "bibliography.md",
        ],
    ),
    ReportPackTemplate.MARKET_LANDSCAPE: TemplateSpec(
        name="Market Landscape",
        required_files=[
            "executive_summary.md",
            "market_overview.md",
            "competitor_analysis.md",
            "trends.md",
            "recommendations.md",
        ],
    ),
    ReportPackTemplate.TECHNICAL_BEST_PRACTICES: TemplateSpec(
        name="Technical Best Practices",
        required_files=[
            "summary.md",
            "current_state.md",
            "best_practices.md",
            "implementation_guide.md",
            "examples.md",
        ],
    ),
}
