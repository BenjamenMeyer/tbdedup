import os
import os.path

from asyncslot import asyncSlot

from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTreeView,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtCore import (
    QDir,
)
#from PySide6.QtAsyncio as QtAsyncio

from tbdedup.gui import (
    searcher,
)

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.searcher = searcher.Searcher()
        self.searcher.progress.connect(asyncSlot(self.receive_progress))
        self.searcher.completed.connect(asyncSlot(self.receive_search_completed))

        self.setWindowTitle("Thunderbird MBox Deduplicator")
        layout = QVBoxLayout()

        # path selector
        path_selection_layout = QHBoxLayout()
        lbl_path = QLabel("Path")
        path_selection_layout.addWidget(lbl_path)
        self.txt_path_selector = QLineEdit()
        self.txt_path_selector.textChanged.connect(asyncSlot(self.path_selected_edited))
        path_selection_layout.addWidget(self.txt_path_selector)
        self.btn_path_selector = QPushButton("Select...")
        self.btn_path_selector.clicked.connect(asyncSlot(self.path_selection_clicked))
        path_selection_layout.addWidget(self.btn_path_selector)
        self.btn_path_search = QPushButton("Search")
        self.btn_path_search.clicked.connect(asyncSlot(self.path_search_clicked))
        path_selection_layout.addWidget(self.btn_path_search)
        layout.addLayout(path_selection_layout)

        # tree view
        self.tree_view = QTreeView()
        layout.addWidget(self.tree_view)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        self.status_bar = QStatusBar()
        layout.addWidget(self.status_bar)

        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    async def path_selection_clicked(self):
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Path",
            os.environ.get("HOME", "/"),
            QFileDialog.ExistingFile|QFileDialog.ShowDirsOnly|QFileDialog.DontResolveSymlinks|QDir.Hidden,
        )
        if folder_path:
            print(f"New folder: {folder_path}")
            self.txt_path_selector.setText(folder_path)
        else:
            print("Path selection cancelled")

    async def path_selected_edited(self, new_path):
        print(f"Path Text Changed: {new_path}")

    async def receive_progress(self, value):
        pass

    async def receive_search_completed(self):
        print("Search completed")
        print(f'Result type: {type(self.searcher.result)}')
        print(f"\tError: {self.searcher.error_result}")
        print(
            '\t'.join(
                [
                    v
                    for v in (
                        self.searcher.result
                        if self.searcher.result is not None
                        else []
                    )
                ]
            )
            if self.searcher.result
            else 'empty result'
        )
        # see self.searcher.result and self.searcher.error_result

    async def path_search_clicked(self):
        folder_path = self.txt_path_selector.text()
        if os.path.isdir(folder_path):
            print(f"Starting search of {folder_path}")
            await self.searcher.mbox_file_search(folder_path)
        else:
            print(f"Selected path ({folder_path}) is not a directory")
