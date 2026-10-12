import unittest

from core.tools.base import Tool, ToolResult
from core.tools.executor import ToolExecutor
from core.tools.permissions import ToolPermission
from core.tools.registry import ToolRegistry
from core.tools.request import ToolRequest


class SideEffectTool(Tool):
    name = "side-effect"
    description = "Test tool that records whether execution occurred."
    capabilities = frozenset({"testing"})
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1},
            "count": {"type": "integer", "minimum": 1, "maximum": 5},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def __init__(self):
        self.calls = 0

    def execute(self, **kwargs):
        self.calls += 1
        return ToolResult(success=True, output=kwargs)


class ToolSchemaValidationTests(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.tool = SideEffectTool()
        self.registry.register(self.tool)
        self.executor = ToolExecutor(self.registry)
        self.permission = ToolPermission.from_capabilities({"testing"})

    def execute(self, arguments):
        return self.executor.execute(
            ToolRequest(tool_name="side-effect", arguments=arguments),
            self.permission,
        )

    def test_valid_arguments_execute_once(self):
        result = self.execute({"path": "artifact.txt", "count": 3})
        self.assertTrue(result.success)
        self.assertEqual(self.tool.calls, 1)

    def test_missing_required_argument_is_rejected_before_side_effect(self):
        result = self.execute({"count": 2})
        self.assertFalse(result.success)
        self.assertIn("required property is missing", result.error)
        self.assertEqual(self.tool.calls, 0)

    def test_additional_argument_is_rejected_before_side_effect(self):
        result = self.execute({"path": "artifact.txt", "unexpected": True})
        self.assertFalse(result.success)
        self.assertIn("additional property is not allowed", result.error)
        self.assertEqual(self.tool.calls, 0)

    def test_wrong_type_and_numeric_bounds_are_rejected(self):
        wrong_type = self.execute({"path": "artifact.txt", "count": True})
        too_large = self.execute({"path": "artifact.txt", "count": 6})
        self.assertFalse(wrong_type.success)
        self.assertFalse(too_large.success)
        self.assertEqual(self.tool.calls, 0)

    def test_malformed_schema_fails_closed(self):
        self.tool.parameters_schema = {
            "type": "object",
            "properties": {"path": {"type": "not-a-real-type"}},
        }
        result = self.execute({"path": "artifact.txt"})
        self.assertFalse(result.success)
        self.assertIn("Invalid tool schema", result.error)
        self.assertEqual(self.tool.calls, 0)


if __name__ == "__main__":
    unittest.main()
