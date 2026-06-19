#          Copyright 2026 Shiver Contributors
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import threading
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Generator


class TaskContext(threading.local):
    # thread local storage to track build context across threads
    def __init__(self) -> None:
        # current build destination path
        self._dest: Path | None = None
        # stack to track active tasks
        self._task_stack: list[tuple[str, str]] = []
        # task keys -> source and task dependencies
        self._tracked_deps: dict[tuple[str, str], dict[str, list[object]]] = {}

    @property
    def dest(self) -> Path:
        # prevent accessing destination outside an active runner scope
        # idiot proofing is needed
        if self._dest is None:
            raise RuntimeError("ctx.dest accessed outside of an active task execution.")
        return self._dest

    @dest.setter
    def dest(self, path: Path) -> None:
        self._dest = path

    @contextmanager
    def set_dest(self, path: Path) -> Generator[None, None, None]:
        # temporarily override the destination path and restore it after
        old_dest = self._dest
        self._dest = path
        try:
            yield
        finally:
            self._dest = old_dest

    def push_task(self, module_name: str, task_name: str) -> None:
        # make new task on the execution stack and init tracking maps
        key = (module_name, task_name)
        self._task_stack.append(key)
        self._tracked_deps[key] = {"sources": [], "tasks": []}

    def pop_task(self) -> None:
        # p u r g e the top task from the stack once execution is done
        if self._task_stack:
            _ = self._task_stack.pop()

    def record_source(self, mod_name: str, fn_name: str, current_hash: str) -> None:
        # record a source file directory hash with the currently active task
        if self._task_stack:
            active_key = self._task_stack[-1]
            record: list[object] = [mod_name, fn_name, current_hash]
            # do not duplicate identical source records
            if record not in self._tracked_deps[active_key]["sources"]:
                self._tracked_deps[active_key]["sources"].append(record)

    def record_upstream_hit(
        self, mod_name: str, fn_name: str, serialized_val: object
    ) -> None:
        # log a cache hit into current task deps
        if self._task_stack:
            parent_key = self._task_stack[-1]
            record: list[object] = [mod_name, fn_name, serialized_val]
            self._tracked_deps[parent_key]["tasks"].append(record)

    def record_upstream_miss(
        self, mod_name: str, fn_name: str, serialized_val: object
    ) -> None:
        # log a cache miss into parent task as it started this subtask
        if len(self._task_stack) > 1:
            parent_key = self._task_stack[-2]
            record: list[object] = [mod_name, fn_name, serialized_val]
            self._tracked_deps[parent_key]["tasks"].append(record)

    def get_dependencies(
        self, module_name: str, task_name: str
    ) -> dict[str, list[object]]:
        # get collected source and task dependencies for a specific task
        return self._tracked_deps.get(
            (module_name, task_name), {"sources": [], "tasks": []}
        )


# global thread local for context management
ctx = TaskContext()
