import json
from typing import Any


def extract_json(response: str) -> Any:
    """Extract and parse JSON from agent response, handling markdown code
    blocks and text around JSON.

    Returns the parsed JSON which may be a dict or list depending on the
    JSON structure.
    """
    response = response.strip()
    json_str = response

    # Handle markdown code blocks (```json ... ``` or ``` ... ```)
    if "```" in response:
        lines = response.split("\n")
        json_lines: list[str] = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```") and not in_block:
                in_block = True
                continue
            if line.strip().startswith("```") and in_block:
                break
            if in_block:
                json_lines.append(line)
        if json_lines:
            json_str = "\n".join(json_lines)
    else:
        # Find JSON object or array boundaries
        obj_start = response.find("{")
        arr_start = response.find("[")

        if arr_start != -1 and (obj_start == -1 or arr_start < obj_start):
            # Array comes first
            end = response.rfind("]") + 1
            if arr_start != -1 and end > arr_start:
                json_str = response[arr_start:end]
        elif obj_start != -1:
            # Object comes first
            end = response.rfind("}") + 1
            if end > obj_start:
                json_str = response[obj_start:end]

    return json.loads(json_str)
