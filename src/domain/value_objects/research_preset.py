from enum import Enum

from pydantic import BaseModel


class ResearchPreset(str, Enum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    THOROUGH = "thorough"
    EXHAUSTIVE = "exhaustive"


class PresetParams(BaseModel, frozen=True):
    min_sources: int
    coverage: float
    synthesis_passes: int
    max_iterations: int
    max_hours: int


PRESET_PARAMS: dict[ResearchPreset, PresetParams] = {
    ResearchPreset.MINIMAL: PresetParams(
        min_sources=1,
        coverage=0.0,  # No coverage required for minimal
        synthesis_passes=1,
        max_iterations=1,  # Just one discovery iteration
        max_hours=1,
    ),
    ResearchPreset.STANDARD: PresetParams(
        min_sources=30,
        coverage=0.8,
        synthesis_passes=1,
        max_iterations=60,
        max_hours=6,
    ),
    ResearchPreset.THOROUGH: PresetParams(
        min_sources=50,
        coverage=0.9,
        synthesis_passes=2,
        max_iterations=100,
        max_hours=12,
    ),
    ResearchPreset.EXHAUSTIVE: PresetParams(
        min_sources=100,
        coverage=0.95,
        synthesis_passes=3,
        max_iterations=200,
        max_hours=24,
    ),
}
