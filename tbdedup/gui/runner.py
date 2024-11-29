from PyQt5.QtCore import (
    QObject,
    QRunnable,
    pyqtSignal,
)

class RunnerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(tuple) # tuple on error
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
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
