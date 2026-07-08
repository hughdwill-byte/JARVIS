"""MCP tool-schema sanitising for Anthropic compatibility.

The Anthropic API rejects `oneOf`/`allOf`/`anyOf` (and anything not typed as an
object) at the top level of a tool's input_schema, and a single bad tool 400s
the entire turn. Real connectors (Microsoft 365 / Graph, Canvas) ship such
tools, so MCP schemas must be normalised before they're sent.
"""

from app.brain.mcp_client import sanitize_input_schema


def test_wellformed_object_schema_passes_through_untouched():
    schema = {"type": "object",
              "properties": {"q": {"type": "string"}},
              "required": ["q"]}
    assert sanitize_input_schema(schema) is schema


def test_top_level_anyof_is_coerced_to_object():
    schema = {"anyOf": [{"type": "object"}, {"type": "string"}]}
    out = sanitize_input_schema(schema)
    assert out["type"] == "object"
    for combinator in ("anyOf", "oneOf", "allOf"):
        assert combinator not in out


def test_top_level_oneof_and_allof_are_coerced():
    for key in ("oneOf", "allOf"):
        out = sanitize_input_schema({key: [{"type": "object"}]})
        assert out["type"] == "object"
        assert key not in out


def test_properties_and_required_are_preserved_when_present():
    schema = {
        "anyOf": [{"required": ["a"]}, {"required": ["b"]}],
        "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
        "required": ["a"],
    }
    out = sanitize_input_schema(schema)
    assert out["properties"] == {"a": {"type": "string"}, "b": {"type": "integer"}}
    assert out["required"] == ["a"]


def test_required_entries_without_matching_property_are_dropped():
    schema = {"anyOf": [{}], "required": ["ghost"]}
    out = sanitize_input_schema(schema)
    # "ghost" isn't in properties, so it can't remain required (would itself
    # be an invalid schema).
    assert "required" not in out
    assert out == {"type": "object", "properties": {}}


def test_missing_type_is_coerced_to_object():
    # e.g. a top-level "$ref" schema, or one that just forgot "type"
    out = sanitize_input_schema({"properties": {"x": {"type": "string"}}})
    assert out["type"] == "object"
    assert out["properties"] == {"x": {"type": "string"}}


def test_non_dict_schema_becomes_empty_object():
    assert sanitize_input_schema(None) == {"type": "object", "properties": {}}
    assert sanitize_input_schema("nonsense") == {"type": "object", "properties": {}}


def test_nested_combinators_are_left_alone():
    # Anthropic only forbids combinators at the TOP level; nested ones inside a
    # property are valid and must not be stripped.
    schema = {"type": "object",
              "properties": {"body": {"anyOf": [{"type": "string"}, {"type": "null"}]}}}
    out = sanitize_input_schema(schema)
    assert out is schema
    assert "anyOf" in out["properties"]["body"]
