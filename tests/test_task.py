import unittest

from core.orchestrator.task import Task, TaskStatus


class TaskTests(unittest.TestCase):
    def test_new_task_starts_pending(self):
        task = Task(objective="Test task")

        self.assertEqual(task.status, TaskStatus.PENDING)

    def test_pending_task_can_start(self):
        task = Task(objective="Test task")

        task.start()

        self.assertEqual(task.status, TaskStatus.RUNNING)

    def test_running_task_can_complete(self):
        task = Task(objective="Test task")

        task.start()
        task.complete()

        self.assertEqual(task.status, TaskStatus.COMPLETED)

    def test_running_task_can_fail(self):
        task = Task(objective="Test task")

        task.start()
        task.fail()

        self.assertEqual(task.status, TaskStatus.FAILED)


class InvalidTaskTransitionTests(unittest.TestCase):
    def test_pending_task_cannot_complete(self):
        task = Task(objective="Test task")

        with self.assertRaises(RuntimeError):
            task.complete()

    def test_pending_task_cannot_fail(self):
        task = Task(objective="Test task")

        with self.assertRaises(RuntimeError):
            task.fail()

    def test_completed_task_cannot_start(self):
        task = Task(objective="Test task")
        task.start()
        task.complete()

        with self.assertRaises(RuntimeError):
            task.start()

    def test_completed_task_cannot_fail(self):
        task = Task(objective="Test task")
        task.start()
        task.complete()

        with self.assertRaises(RuntimeError):
            task.fail()

    def test_failed_task_cannot_start(self):
        task = Task(objective="Test task")
        task.start()
        task.fail()

        with self.assertRaises(RuntimeError):
            task.start()

    def test_failed_task_cannot_complete(self):
        task = Task(objective="Test task")
        task.start()
        task.fail()

        with self.assertRaises(RuntimeError):
            task.complete()

if __name__ == "__main__":
    unittest.main()
