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
import os.path

from asyncslot import asyncSlot
from PySide6.QtCore import (
    QDir,
    Signal,
    Slot,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from thunderbirddedup.gui import (
    runner,
)


class MainWindow(QMainWindow):
    search_path = Signal(str)
    record_log = Signal(str)

    def __init__(self):
        super().__init__()
        self.runner = runner.TbDedupRunner()
        self.runner.record_log.connect(self.record_log)
        # self.search_path.connect(asyncSlot(self.runner.preplan))
        self.search_path.connect(self.runner.preplan)

        self.setWindowTitle("Thunderbird MBox Deduplicator")
        layout = QVBoxLayout()

        # path selector
        self.lbl_path = QLabel("Path")
        self.txt_path = QLineEdit()
        self.txt_path.textChanged.connect(self.path_changed)
        self.btn_path = QPushButton("Select...")
        self.btn_path.clicked.connect(self.select_path)
        self.btn_search = QPushButton("Search")
        self.btn_search.setEnabled(False)
        self.btn_search.clicked.connect(self.do_search)

        ps_layout = QHBoxLayout()
        ps_layout.addWidget(self.lbl_path)
        ps_layout.addWidget(self.txt_path)
        ps_layout.addWidget(self.btn_path)
        ps_layout.addWidget(self.btn_search)
        layout.addLayout(ps_layout)

        # tree view
        self.tv_mbox_files = QTreeView()
        layout.addWidget(self.tv_mbox_files)

        # log data
        self.txt_logs = QTextEdit()
        self.txt_logs.setReadOnly(True)
        self.record_log.connect(self.log_receipt)
        layout.addWidget(self.txt_logs)

        main_widget = QWidget()
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)

    @Slot(str)
    def log_receipt(self, message):
        self.txt_logs.append(message)

    @Slot()
    def path_changed(self):
        path = self.txt_path.text()
        search_enabled = os.path.isdir(path)
        self.btn_search.setEnabled(search_enabled)
        self.record_log.emit(f"Search enabled: {search_enabled}")

    @Slot()
    def select_path(self):
        current_path = self.txt_path.text()
        folder_path = QFileDialog.getExistingDirectory(
            self,
            caption="Select Path",
            dir=(
                current_path
                if os.path.isdir(current_path)
                else os.environ.get("HOME", "/")
            ),
            options=QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if folder_path:
            self.record_log.emit(f"New folder: {folder_path}")
            self.txt_path.setText(folder_path)
        else:
            self.record_log.emit("Path selection cancelled")

    @Slot()
    def do_search(self):
        path = self.txt_path.text()
        self.record_log.emit(f"Searching {path}...")
        self.search_path.emit(path)

    @Slot()
    def preplan_completed(self):
        self.record_log.emit(f"Completed preplanning")
