"""Small, dependency-free JSON Schema subset for tool input validation.

Supported keywords: type, properties, required, additionalProperties, enum,
items, minLength, maxLength, minimum, maximum, minItems, and maxItems.
Unsupported schema keywords are rejected rather than silently ignored.
"""
from __future__ import annotations

from typing import Any, Mapping


_SUPPORTED_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
_SUPPORTED_KEYWORDS = {
    "type", "properties", "required", "additionalProperties", "enum",
    "items", "minLength", "maxLength", "minimum", "maximum",
    "minItems", "maxItems",
}


def validate_json_schema(value: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    """Return validation errors; malformed or unsupported schemas fail closed."""
    if not isinstance(schema, Mapping):
        raise ValueError("Tool parameter schema must be an object.")
    unknown = set(schema) - _SUPPORTED_KEYWORDS
    if unknown:
        raise ValueError(f"Unsupported schema keyword(s): {', '.join(sorted(unknown))}.")
    schema_type = schema.get("type")
    if schema_type is not None and schema_type not in _SUPPORTED_TYPES:
        raise ValueError(f"Unsupported schema type: {schema_type!r}.")
    if "enum" in schema and not isinstance(schema["enum"], list):
        raise ValueError("Schema 'enum' must be a list.")
    errors: list[str] = []

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value is not one of the allowed choices.")

    if schema_type == "object":
        if not isinstance(value, dict):
            return errors + [f"{path}: expected object."]
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        additional = schema.get("additionalProperties", True)
        if not isinstance(properties, Mapping):
            raise ValueError("Schema 'properties' must be an object.")
        if not isinstance(required, list) or any(not isinstance(k, str) for k in required):
            raise ValueError("Schema 'required' must be a list of property names.")
        if not isinstance(additional, bool):
            raise ValueError("Schema 'additionalProperties' must be a boolean.")
        for key in required:
            if key not in properties:
                raise ValueError(f"Required schema property {key!r} is not defined.")
            if key not in value:
                errors.append(f"{path}.{key}: required property is missing.")
        for key, item in value.items():
            if key not in properties:
                if not additional:
                    errors.append(f"{path}.{key}: additional property is not allowed.")
                continue
            errors.extend(validate_json_schema(item, properties[key], f"{path}.{key}"))
        return errors

    if schema_type == "array":
        if not isinstance(value, list):
            return errors + [f"{path}: expected array."]
        if "items" in schema:
            errors.extend(
                error
                for index, item in enumerate(value)
                for error in validate_json_schema(item, schema["items"], f"{path}[{index}]")
            )
        if "minItems" in schema and len(value) < _nonnegative_number(schema["minItems"], "minItems"):
            errors.append(f"{path}: must contain at least {schema['minItems']} items.")
        if "maxItems" in schema and len(value) > _nonnegative_number(schema["maxItems"], "maxItems"):
            errors.append(f"{path}: must contain at most {schema['maxItems']} items.")
        return errors

    if schema_type == "string":
        if not isinstance(value, str):
            return errors + [f"{path}: expected string."]
        if "minLength" in schema and len(value) < _nonnegative_number(schema["minLength"], "minLength"):
            errors.append(f"{path}: string is too short.")
        if "maxLength" in schema and len(value) > _nonnegative_number(schema["maxLength"], "maxLength"):
            errors.append(f"{path}: string is too long.")
    elif schema_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return errors + [f"{path}: expected number."]
        errors.extend(_check_numeric_bounds(value, schema, path))
    elif schema_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return errors + [f"{path}: expected integer."]
        errors.extend(_check_numeric_bounds(value, schema, path))
    elif schema_type == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{path}: expected boolean.")
    elif schema_type == "null" and value is not None:
        errors.append(f"{path}: expected null.")

    return errors


def _nonnegative_number(value: Any, name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"Schema '{name}' must be a non-negative number.")
    return value


def _number(value: Any, name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Schema {name!r} must be a number.")
    return value


def _check_numeric_bounds(value: int | float, schema: Mapping[str, Any], path: str) -> list[str]:
    errors = []
    if "minimum" in schema and value < _number(schema["minimum"], "minimum"):
        errors.append(f"{path}: value is below minimum.")
    if "maximum" in schema and value > _number(schema["maximum"], "maximum"):
        errors.append(f"{path}: value is above maximum.")
    return errors
