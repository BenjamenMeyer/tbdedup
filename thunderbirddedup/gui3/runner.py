"""
Copyright 2023-2026 Benjamen R. Meyer

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
from PyQt5.QtCore import (
    QObject,
    QRunnable,
    pyqtSignal,
)


class RunnerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(tuple)  # tuple on error
    result = pyqtSignal(object)
    progress = pyqtSignal(int)


class Runner(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = RunnerSignals()
        self.kwargs['progress_callback'] = self.signals.progress

    async def run(self):
        try:
            result = await self.fn(
                *self.args,
                **self.kwargs,
            )
        except Exception:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
