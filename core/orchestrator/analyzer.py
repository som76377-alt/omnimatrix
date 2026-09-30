from abc import ABC, abstractmethod

from core.router import RoutingRequirements


class TaskAnalyzer(ABC):
    """Converts a natural-language objective into routing requirements."""

    @abstractmethod
    def analyze(self, objective: str) -> RoutingRequirements:
        raise NotImplementedError


class BasicTaskAnalyzer(TaskAnalyzer):
    """
    Deterministic baseline analyzer.

    This is intentionally simple. A more capable analyzer can replace it
    later without changing the router or task model.
    """

    def analyze(self, objective: str) -> RoutingRequirements:
        text = objective.lower()

        capabilities: set[str] = {"reasoning"}

        if any(
            keyword in text
            for keyword in (
                "code",
                "coding",
                "program",
                "programming",
                "website",
                "app",
                "software",
                "bug",
                "debug",
            )
        ):
            capabilities.add("coding")

        if any(
            keyword in text
            for keyword in (
                "research",
                "researching",
                "investigate",
                "analyze sources",
            )
        ):
            capabilities.add("research")

        if any(
            keyword in text
            for keyword in (
                "browser",
                "website",
                "web page",
                "webpage",
            )
        ):
            capabilities.add("browser")

        if any(
            keyword in text
            for keyword in (
                "test",
                "testing",
                "tests",
                "qa",
                "quality assurance",
            )
        ):
            capabilities.add("testing")

        return RoutingRequirements(
            capabilities=frozenset(capabilities)
        )
