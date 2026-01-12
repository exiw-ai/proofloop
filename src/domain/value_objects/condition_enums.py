from enum import Enum


class ConditionRole(str, Enum):
    BLOCKING = "blocking"
    SIGNAL = "signal"
    OBSERVER = "observer"


class ApprovalStatus(str, Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class CheckStatus(str, Enum):
    NOT_RUN = "not_run"
    PASS = "pass"
    FAIL = "fail"
