from enum import Enum


class ResearchType(str, Enum):
    ACADEMIC = "academic"
    MARKET = "market"
    TECHNICAL = "technical"
    GENERAL = "general"
