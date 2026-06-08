"""GUI 后台任务管理。"""

from __future__ import annotations

import json
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


TERMINAL_STATUS = {"success", "failed", "cancelled"}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class TaskState:
    task_id: str
    task_type: str
    status: str = "pending"
    progress: float = 0.0
    total: int = 0
    done: int = 0
    success: int = 0
    failed: int = 0
    current: str = ""
    message: str = ""
    logs: list[str] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    cancel_requested: bool = False
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


class TaskManager:
    """本地单用户任务管理器，任务状态持久化到 outputs/.gui/tasks.json。"""

    def __init__(self, max_workers: int = 3, max_logs: int = 300, store_path: str | Path | None = None):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, TaskState] = {}
        self._lock = threading.RLock()
        self._max_logs = max_logs
        self._store_path = Path(store_path) if store_path else None
        self._load()

    def _load(self) -> None:
        if not self._store_path or not self._store_path.exists():
            return
        try:
            raw = json.loads(self._store_path.read_text(encoding="utf-8"))
            for item in raw.get("tasks", []):
                if item.get("status") in {"pending", "running"}:
                    item["status"] = "cancelled"
                    item["message"] = "服务重启，任务已中断"
                    item["cancel_requested"] = True
                task = TaskState(**{k: v for k, v in item.items() if k in TaskState.__dataclass_fields__})
                self._tasks[task.task_id] = task
        except Exception:
            self._tasks = {}

    def _persist(self) -> None:
        if not self._store_path:
            return
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            tasks = [asdict(t) for t in sorted(self._tasks.values(), key=lambda item: item.created_at, reverse=True)]
            tmp = self._store_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._store_path)
        except Exception:
            pass

    def create_task(
        self,
        task_type: str,
        func: Callable[[str, Callable[..., None], Callable[[], bool]], dict[str, Any] | None],
    ) -> str:
        task_id = f"{task_type}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        state = TaskState(task_id=task_id, task_type=task_type)
        with self._lock:
            self._tasks[task_id] = state
            self._persist()
        self._executor.submit(self._run_task, task_id, func)
        return task_id

    def _run_task(
        self,
        task_id: str,
        func: Callable[[str, Callable[..., None], Callable[[], bool]], dict[str, Any] | None],
    ) -> None:
        self.update(task_id, status="running", message="任务开始")
        try:
            result = func(
                task_id,
                lambda **kwargs: self.update(task_id, **kwargs),
                lambda: self.is_cancel_requested(task_id),
            )
            state = self.get_task(task_id)
            if state.get("cancel_requested") or state.get("status") == "cancelled":
                self.update(task_id, status="cancelled", message="任务已取消")
            else:
                self.update(task_id, status="success", progress=100.0, message="任务完成", result=result or {})
        except Exception as exc:  # noqa: BLE001
            self.update(task_id, status="failed", message=f"任务失败: {exc}", log=traceback.format_exc(limit=6))

    def update(self, task_id: str, **kwargs: Any) -> None:
        log = kwargs.pop("log", None)
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            for key, value in kwargs.items():
                if hasattr(task, key) and value is not None:
                    setattr(task, key, value)
            if log:
                for line in str(log).splitlines():
                    if line.strip():
                        task.logs.append(f"[{now_iso()}] {line}")
                if len(task.logs) > self._max_logs:
                    task.logs = task.logs[-self._max_logs :]
            task.updated_at = now_iso()
            self._persist()

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise KeyError(task_id)
            return asdict(task)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(t) for t in sorted(self._tasks.values(), key=lambda item: item.created_at, reverse=True)]

    def cancel_task(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise KeyError(task_id)
            task.cancel_requested = True
            if task.status in {"pending"}:
                task.status = "cancelled"
            task.message = "已请求取消，等待当前步骤结束"
            task.updated_at = now_iso()
            self._persist()

    def clear_logs(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise KeyError(task_id)
            task.logs = []
            task.updated_at = now_iso()
            self._persist()

    def delete_task(self, task_id: str) -> None:
        with self._lock:
            if task_id not in self._tasks:
                raise KeyError(task_id)
            del self._tasks[task_id]
            self._persist()

    def clear_tasks(self) -> None:
        with self._lock:
            self._tasks.clear()
            self._persist()

    def is_cancel_requested(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            return bool(task and task.cancel_requested)
