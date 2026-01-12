from pydantic import BaseModel


class ConditionParams(BaseModel, frozen=True):
    """Parameters for condition verification.

    Currently empty as params are not actively used in the codebase, but
    provides type safety and extensibility for future use.
    """

    pass
