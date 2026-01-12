from pydantic import BaseModel

from src.infrastructure.utils.json_extractor import extract_json


def parse_agent_json[T](
    response: str,
    fallback: T,
    model: type[BaseModel] | None = None,
) -> T:
    try:
        data = extract_json(response)
        if model is not None:
            return model.model_validate(data)  # type: ignore[return-value]
        return data  # type: ignore[no-any-return]
    except Exception:
        return fallback
