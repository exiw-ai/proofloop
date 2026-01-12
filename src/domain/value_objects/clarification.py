from pydantic import BaseModel


class ClarificationOption(BaseModel):
    """An option for a clarification question."""

    key: str
    label: str
    description: str = ""


class ClarificationQuestion(BaseModel):
    """A question to clarify ambiguous requirements."""

    id: str
    question: str
    context: str = ""
    options: list[ClarificationOption]
    allow_custom: bool = True
    default_option: str | None = None  # Key of the "decide for me" option


class ClarificationAnswer(BaseModel):
    """User's answer to a clarification question."""

    question_id: str
    selected_option: str  # Key of selected option, or "custom"
    custom_value: str | None = None  # If custom answer


# Standard "decide for me" option that should be included in questions
DECIDE_FOR_ME_OPTION = ClarificationOption(
    key="_auto",
    label="Decide for me",
    description="Let the agent choose based on best practices",
)
