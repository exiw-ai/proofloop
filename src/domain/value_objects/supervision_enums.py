from enum import Enum


class AnomalyType(str, Enum):
    STAGNATION = "stagnation"
    FLAKY_CHECK = "flaky_check"
    REGRESSION = "regression"
    CONTRACT_RISK = "contract_risk"
    LOOP_DETECTED = "loop_detected"


class SupervisionDecision(str, Enum):
    CONTINUE = "continue"
    REPLAN = "replan"
    DEEPEN_CONTEXT = "deepen_context"
    STOP = "stop"
    BLOCK = "block"


class RetryStrategy(str, Enum):
    CONTINUE_WITH_CONTEXT = "continue_with_context"
    ROLLBACK_AND_RETRY = "rollback_and_retry"
    STOP = "stop"
