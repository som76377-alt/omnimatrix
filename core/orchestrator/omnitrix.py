from core.models.base import ModelAdapter
from core.orchestrator.task import Task


class Omnitrix:
    """
    Central orchestration authority.

    At v0.1 this class deliberately does very little.
    The architecture comes before autonomy.
    """

    def __init__(self, model: ModelAdapter) -> None:
        self.model = model

    def run(self, objective: str) -> str:
        task = Task(objective=objective)
        task.start()

        response = self.model.generate(objective)

        task.complete()
        return response.content
