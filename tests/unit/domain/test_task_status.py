from src.domain.value_objects.task_status import TaskStatus


def test_task_status_values():
    assert TaskStatus.INTAKE.value == "intake"
    assert TaskStatus.DONE.value == "done"
    assert TaskStatus.BLOCKED.value == "blocked"
    assert TaskStatus.STOPPED.value == "stopped"


def test_task_status_is_terminal():
    terminal = {TaskStatus.DONE, TaskStatus.BLOCKED, TaskStatus.STOPPED}
    for status in TaskStatus:
        if status in terminal:
            assert status.value in ["done", "blocked", "stopped"]
