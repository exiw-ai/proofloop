from enum import Enum


class StagnationAction(str, Enum):
    CONTINUE = "continue"
    RELAX_CONDITIONS = "relax"
    ESCALATE_TO_USER = "escalate"
    FINALIZE_PARTIAL = "finalize"
