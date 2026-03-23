"""Generic JSON Schema validator extracted for reuse across governance modules.

Supports a subset of JSON Schema 2020-12 sufficient for SESSION_STATE and reason payloads:
- type: object, array, string, integer, boolean
- properties, required, additionalProperties
- items (for arrays)
- enum, minLength, minimum, maximum
- pattern (regex for strings)
"""

from __future__ import annotations

import re
from typing import Any


def validate_against_schema(
    *,
    schema: dict[str, object],
    value: object,
    path: str = "$",
) -> list[str]:
    """Validate a value against a JSON Schema subset.

    Returns a list of error strings, each prefixed with the path.
    Empty list means valid.
    """
    errors: list[str] = []

    expected_type = schema.get("type")

    if expected_type == "object":
        errors.extend(_validate_object(schema, value, path))
    elif expected_type == "array":
        errors.extend(_validate_array(schema, value, path))
    elif expected_type == "string":
        errors.extend(_validate_string(schema, value, path))
    elif expected_type == "integer":
        errors.extend(_validate_integer(schema, value, path))
    elif expected_type == "boolean":
        errors.extend(_validate_boolean(value, path))
    elif isinstance(expected_type, list):
        errors.extend(_validate_union(expected_type, schema, value, path))

    return errors


def _validate_object(schema: dict[str, object], value: object, path: str) -> list[str]:
    errors: list[str] = []

    if not isinstance(value, dict):
        return [f"{path}:expected object"]

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        properties = {}

    required = schema.get("required")
    if isinstance(required, list):
        for key in required:
            if isinstance(key, str) and key not in value:
                errors.append(f"{path}.{key}:required")

    if schema.get("additionalProperties") is False:
        allowed = {k for k in properties.keys() if isinstance(k, str)}
        for key in value.keys():
            if isinstance(key, str) and key not in allowed:
                errors.append(f"{path}.{key}:unexpected")

    for key, child in properties.items():
        if not isinstance(key, str) or key not in value or not isinstance(child, dict):
            continue
        errors.extend(validate_against_schema(schema=child, value=value[key], path=f"{path}.{key}"))

    return errors


def _validate_array(schema: dict[str, object], value: object, path: str) -> list[str]:
    errors: list[str] = []

    if not isinstance(value, list):
        return [f"{path}:expected array"]

    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for idx, item in enumerate(value):
            errors.extend(validate_against_schema(schema=item_schema, value=item, path=f"{path}[{idx}]"))

    min_items = schema.get("minItems")
    if isinstance(min_items, int) and len(value) < min_items:
        errors.append(f"{path}:minItems")

    max_items = schema.get("maxItems")
    if isinstance(max_items, int) and len(value) > max_items:
        errors.append(f"{path}:maxItems")

    return errors


def _validate_string(schema: dict[str, object], value: object, path: str) -> list[str]:
    errors: list[str] = []

    if not isinstance(value, str):
        return [f"{path}:expected string"]

    min_len = schema.get("minLength")
    if isinstance(min_len, int) and len(value) < min_len:
        errors.append(f"{path}:minLength")

    max_len = schema.get("maxLength")
    if isinstance(max_len, int) and len(value) > max_len:
        errors.append(f"{path}:maxLength")

    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        errors.append(f"{path}:enum")

    pattern = schema.get("pattern")
    if isinstance(pattern, str):
        if not re.match(pattern, value):
            errors.append(f"{path}:pattern")

    const = schema.get("const")
    if const is not None and value != const:
        errors.append(f"{path}:const")

    return errors


def _validate_integer(schema: dict[str, object], value: object, path: str) -> list[str]:
    errors: list[str] = []

    if not isinstance(value, int) or isinstance(value, bool):
        return [f"{path}:expected integer"]

    minimum = schema.get("minimum")
    if isinstance(minimum, int) and value < minimum:
        errors.append(f"{path}:minimum")

    maximum = schema.get("maximum")
    if isinstance(maximum, int) and value > maximum:
        errors.append(f"{path}:maximum")

    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        errors.append(f"{path}:enum")

    return errors


def _validate_boolean(value: object, path: str) -> list[str]:
    if isinstance(value, bool):
        return []
    return [f"{path}:expected boolean"]


def _validate_union(
    types: list[Any],
    schema: dict[str, object],
    value: object,
    path: str,
) -> list[str]:
    """Validate against a union type (type: [\"string\", \"null\"])."""
    for t in types:
        if t == "null" and value is None:
            return []
        if t == "string" and isinstance(value, str):
            return []
        if t == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return []
        if t == "boolean" and isinstance(value, bool):
            return []
        if t == "array" and isinstance(value, list):
            return []
        if t == "object" and isinstance(value, dict):
            return []
    return [f"{path}:no matching type in union"]
