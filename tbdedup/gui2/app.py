from asyncslot import asyncSlot

from PyQt5.QtWidgets import (
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

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Thunderbird MBox Deduplicator")
        layout = QVBoxLayout()

        # path selector
        path_selection_layout = QHBoxLayout()
        lbl_path = QLabel("Path")
        path_selection_layout.addWidget(lbl_path)
        self.txt_path_selector = QLineEdit()
        path_selection_layout.addWidget(self.txt_path_selector)
        self.btn_path_selector = QPushButton("Select...")
        path_selection_layout.addWidget(self.btn_path_selector)
        self.btn_path_search = QPushButton("Search")
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
