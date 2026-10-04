"""A bounded arithmetic evaluator. It never executes Python source."""

import ast
import math
from decimal import Decimal, DecimalException, localcontext

from pydantic import BaseModel

MAX_EXPRESSION_LENGTH = 200
MAX_AST_NODES = 64
MAX_ABSOLUTE_VALUE = Decimal("1e12")


class CalculationError(ValueError):
    """The expression is outside the calculator's supported grammar or limits."""


class CalculationResult(BaseModel):
    expression: str
    result: int | float


def evaluate(expression: str) -> CalculationResult:
    if not expression.strip():
        raise CalculationError("Expression cannot be empty.")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise CalculationError("Expression is too long.")

    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise CalculationError("Invalid arithmetic expression.") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
        raise CalculationError("Expression is too complex.")

    def bounded(value: Decimal) -> Decimal:
        if not value.is_finite() or abs(value) > MAX_ABSOLUTE_VALUE:
            raise CalculationError("Number exceeds the calculator limit.")
        return value

    def visit(node: ast.AST) -> Decimal:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if isinstance(node.value, float) and not math.isfinite(node.value):
                raise CalculationError("Numbers must be finite.")
            return bounded(Decimal(str(node.value)))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return bounded(value if isinstance(node.op, ast.UAdd) else -value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                return bounded(left + right)
            if isinstance(node.op, ast.Sub):
                return bounded(left - right)
            if isinstance(node.op, ast.Mult):
                return bounded(left * right)
            if right == 0:
                raise CalculationError("Division by zero is not allowed.")
            return bounded(left / right)
        raise CalculationError("Only numbers, parentheses, +, -, *, and / are supported.")

    try:
        with localcontext() as context:
            context.prec = 28
            value = visit(tree)
    except DecimalException as exc:
        raise CalculationError("The expression could not be calculated.") from exc

    result = int(value) if value == value.to_integral_value() else float(value)
    return CalculationResult(expression=expression, result=result)
