import ast
import operator
from typing import Any

from core.tools.base import Tool, ToolExecutionError, ToolResult


class CalculatorTool(Tool):
    """Safely evaluate basic arithmetic expressions."""

    _operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "Evaluate a basic arithmetic expression."

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"calculation"})

    def execute(self, **kwargs: Any) -> ToolResult:
        expression = kwargs.get("expression")

        if not isinstance(expression, str) or not expression.strip():
            raise ToolExecutionError(
                "Calculator requires a non-empty expression."
            )

        try:
            tree = ast.parse(expression, mode="eval")
            result = self._evaluate(tree.body)
        except (SyntaxError, ValueError, TypeError, ZeroDivisionError) as exc:
            raise ToolExecutionError(
                f"Invalid arithmetic expression: {expression}"
            ) from exc

        return ToolResult(
            success=True,
            output=result,
        )

    def _evaluate(self, node: ast.AST) -> int | float:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                raise ValueError("Boolean values are not allowed.")

            if isinstance(node.value, (int, float)):
                return node.value

            raise ValueError("Only numeric constants are allowed.")

        if isinstance(node, ast.BinOp):
            operation = self._operators.get(type(node.op))

            if operation is None:
                raise ValueError("Unsupported arithmetic operator.")

            left = self._evaluate(node.left)
            right = self._evaluate(node.right)

            return operation(left, right)

        if isinstance(node, ast.UnaryOp):
            operation = self._operators.get(type(node.op))

            if operation is None:
                raise ValueError("Unsupported unary operator.")

            operand = self._evaluate(node.operand)

            return operation(operand)

        raise ValueError("Unsupported expression.")