import unittest

from core.tools.base import Tool, ToolResult
from core.tools.registry import ToolRegistry
from core.tools.implementations.calculator import CalculatorTool
from core.tools.bootstrap import build_tool_registry
from core.tools.request import ToolRequest
from core.tools.permissions import ToolPermission
from core.tools.executor import ToolExecutor


class TestTool(Tool):
    """Simple fake tool used only for testing."""

    @property
    def name(self) -> str:
        return "test-tool"

    @property
    def description(self) -> str:
        return "A tool used for registry tests."

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"testing"})

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=True,
            output="test output",
        )


class SecondTestTool(Tool):
    """Second fake tool used to test multiple registrations."""

    @property
    def name(self) -> str:
        return "second-tool"

    @property
    def description(self) -> str:
        return "A second test tool."

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"testing"})

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=True,
            output="second output",
        )


class ToolResultTests(unittest.TestCase):
    def test_successful_result(self) -> None:
        result = ToolResult(
            success=True,
            output="hello",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, "hello")
        self.assertIsNone(result.error)

    def test_failed_result(self) -> None:
        result = ToolResult(
            success=False,
            error="Something went wrong.",
        )

        self.assertFalse(result.success)
        self.assertIsNone(result.output)
        self.assertEqual(result.error, "Something went wrong.")

class CalculatorToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calculator = CalculatorTool()

    def test_basic_arithmetic(self) -> None:
        result = self.calculator.execute(
            expression="2 + 3 * 4",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, 14)

    def test_division(self) -> None:
        result = self.calculator.execute(
            expression="10 / 4",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, 2.5)

    def test_capability(self) -> None:
        self.assertEqual(
            self.calculator.capabilities,
            frozenset({"calculation"}),
        )

    def test_empty_expression_fails(self) -> None:
        from core.tools.base import ToolExecutionError

        with self.assertRaises(ToolExecutionError):
            self.calculator.execute(expression="")

    def test_unsupported_expression_fails(self) -> None:
        from core.tools.base import ToolExecutionError

        with self.assertRaises(ToolExecutionError):
            self.calculator.execute(
                expression="__import__('os').system('echo unsafe')",
            )

    def test_division_by_zero_fails(self) -> None:
        from core.tools.base import ToolExecutionError

        with self.assertRaises(ToolExecutionError):
            self.calculator.execute(
                expression="10 / 0",
            )
class ToolRegistryTests(unittest.TestCase):
    def test_register_and_get_tool(self) -> None:
        registry = ToolRegistry()
        tool = TestTool()

        registry.register(tool)

        self.assertTrue(registry.has("test-tool"))
        self.assertIs(registry.get("test-tool"), tool)
    def test_tool_exposes_capabilities(self) -> None:
        tool = TestTool()

        self.assertEqual(
            tool.capabilities,
            frozenset({"testing"}),
        )

    def test_duplicate_tool_registration_fails(self) -> None:
        registry = ToolRegistry()

        registry.register(TestTool())

        with self.assertRaises(ValueError):
            registry.register(TestTool())

    def test_unknown_tool_fails(self) -> None:
        registry = ToolRegistry()

        with self.assertRaises(KeyError):
            registry.get("missing-tool")

    def test_list_returns_registered_tools(self) -> None:
        registry = ToolRegistry()

        first = TestTool()
        second = SecondTestTool()

        registry.register(first)
        registry.register(second)

        tools = registry.list()

        self.assertEqual(len(tools), 2)
        self.assertIs(tools[0], first)
        self.assertIs(tools[1], second)

    def test_tool_name_cannot_be_empty(self) -> None:
        class EmptyNameTool(Tool):
            @property
            def name(self) -> str:
                return "   "

            @property
            def description(self) -> str:
                return "Invalid tool."

            @property
            def capabilities(self) -> frozenset[str]:
                return frozenset({"testing"})

            def execute(self, **kwargs) -> ToolResult:
                return ToolResult(success=True)

        registry = ToolRegistry()

        with self.assertRaises(ValueError):
            registry.register(EmptyNameTool())

class ToolBootstrapTests(unittest.TestCase):
    def test_default_registry_contains_calculator(self) -> None:
        registry = build_tool_registry()

        self.assertTrue(registry.has("calculator"))

        calculator = registry.get("calculator")

        self.assertEqual(
            calculator.name,
            "calculator",
        )

        self.assertEqual(
            calculator.capabilities,
            frozenset({"calculation"}),
        )

    def test_default_registry_calculator_executes(self) -> None:
        registry = build_tool_registry()

        result = registry.get("calculator").execute(
            expression="6 * 7",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, 42)
class ToolRequestTests(unittest.TestCase):
    def test_request_stores_tool_name_and_arguments(self) -> None:
        request = ToolRequest(
            tool_name="calculator",
            arguments={"expression": "2 + 2"},
        )

        self.assertEqual(request.tool_name, "calculator")
        self.assertEqual(
            request.arguments,
            {"expression": "2 + 2"},
        )

    def test_empty_tool_name_fails(self) -> None:
        with self.assertRaises(ValueError):
            ToolRequest(
                tool_name="   ",
                arguments={},
            )

    def test_arguments_must_be_dictionary(self) -> None:
        with self.assertRaises(TypeError):
            ToolRequest(
                tool_name="calculator",
                arguments="2 + 2",
            )
class ToolPermissionTests(unittest.TestCase):
    def test_permission_allows_required_capabilities(self) -> None:
        permission = ToolPermission.from_capabilities(
            {"calculation", "testing"},
        )

        self.assertTrue(
            permission.allows(
                frozenset({"calculation"}),
            )
        )

    def test_permission_rejects_missing_capability(self) -> None:
        permission = ToolPermission.from_capabilities(
            {"calculation"},
        )

        self.assertFalse(
            permission.allows(
                frozenset({"terminal"}),
            )
        )

    def test_permission_requires_all_capabilities(self) -> None:
        permission = ToolPermission.from_capabilities(
            {"calculation"},
        )

        self.assertFalse(
            permission.allows(
                frozenset({"calculation", "terminal"}),
            )
        )

    def test_empty_capability_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ToolPermission.from_capabilities(
                {"calculation", "   "},
            )

    def test_empty_permission_is_valid(self) -> None:
        permission = ToolPermission.from_capabilities(set())

        self.assertTrue(
            permission.allows(frozenset())
        )

        self.assertFalse(
            permission.allows(
                frozenset({"calculation"}),
            )
        )
class ToolExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_tool_registry()
        self.executor = ToolExecutor(self.registry)

    def test_authorized_tool_executes(self) -> None:
        request = ToolRequest(
            tool_name="calculator",
            arguments={"expression": "6 * 7"},
        )

        permission = ToolPermission.from_capabilities(
            {"calculation"},
        )

        result = self.executor.execute(
            request,
            permission,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, 42)

    def test_unauthorized_tool_is_rejected(self) -> None:
        request = ToolRequest(
            tool_name="calculator",
            arguments={"expression": "6 * 7"},
        )

        permission = ToolPermission.from_capabilities(
            set(),
        )

        result = self.executor.execute(
            request,
            permission,
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.error,
            "Permission denied for tool: calculator",
        )

    def test_unknown_tool_raises_error(self) -> None:
        request = ToolRequest(
            tool_name="missing-tool",
            arguments={},
        )

        permission = ToolPermission.from_capabilities(
            {"testing"},
        )

        with self.assertRaises(KeyError):
            self.executor.execute(
                request,
                permission,
            )
if __name__ == "__main__":
    unittest.main()