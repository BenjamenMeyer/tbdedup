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
import asyncio
import os
import os.path

from PySide6.QtCore import (
    QItemSelectionModel,
    QStringListModel,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from thunderbirddedup import combinatory
from thunderbirddedup.gui import runner
from thunderbirddedup.planner import keys as planner_keys

TREE_COLUMNS = [
    "Logical Folder",
    "Copies",
    "Source Size",
    "Total Msgs",
    "Unique Msgs",
    "Dedup Size",
    "Status",
]


class MainWindow(QMainWindow):
    record_log = Signal(str)

    def __init__(self, initial_options=None):
        super().__init__()
        self.runner = runner.TbDedupRunner()
        self.runner.record_log.connect(self.log_receipt)
        self.runner.progress_updated.connect(self.on_progress_updated)
        self.runner.preplan_complete.connect(self.on_preplan_completed)
        self.runner.plan_dedup_updated.connect(self.on_plan_dedup_updated)
        self.runner.dedup_complete.connect(self.on_dedup_completed)
        self.runner.move_complete.connect(self.on_move_completed)
        self.record_log.connect(self.log_receipt)

        self._row_items_by_root = {}

        self.setWindowTitle("Thunderbird MBox Deduplicator")
        self.resize(1200, 820)

        main_layout = QVBoxLayout()

        # 1. Configuration Grid
        config_grid = QGridLayout()

        self.lbl_path = QLabel("Source Path:")
        self.txt_path = QLineEdit()
        self.txt_path.textChanged.connect(self.path_changed)
        self.btn_path = QPushButton("Select...")
        self.btn_path.clicked.connect(self.select_path)
        config_grid.addWidget(self.lbl_path, 0, 0)
        config_grid.addWidget(self.txt_path, 0, 1, 1, 3)
        config_grid.addWidget(self.btn_path, 0, 4)

        self.lbl_storage = QLabel("Work/Storage Dir:")
        self.txt_storage_path = QLineEdit()
        self.btn_storage_path = QPushButton("Select...")
        self.btn_storage_path.clicked.connect(self.select_storage_path)
        config_grid.addWidget(self.lbl_storage, 1, 0)
        config_grid.addWidget(self.txt_storage_path, 1, 1, 1, 3)
        config_grid.addWidget(self.btn_storage_path, 1, 4)

        self.lbl_output = QLabel("Output Tree Dir:")
        self.txt_output_path = QLineEdit()
        self.btn_output_path = QPushButton("Select...")
        self.btn_output_path.clicked.connect(self.select_output_path)
        config_grid.addWidget(self.lbl_output, 2, 0)
        config_grid.addWidget(self.txt_output_path, 2, 1, 1, 3)
        config_grid.addWidget(self.btn_output_path, 2, 4)

        self.lbl_folder_pattern = QLabel("Folder Pattern:")
        self.txt_folder_pattern = QLineEdit("Inbox.sbd/")
        self.lbl_hash_source = QLabel("Hash Source:")
        self.cmb_hash_source = QComboBox()
        self.cmb_hash_source.addItems(["parsed", "disk"])
        config_grid.addWidget(self.lbl_folder_pattern, 3, 0)
        config_grid.addWidget(self.txt_folder_pattern, 3, 1)
        config_grid.addWidget(self.lbl_hash_source, 3, 2)
        config_grid.addWidget(self.cmb_hash_source, 3, 3)

        main_layout.addLayout(config_grid)

        # 2. Middle Splitter: Left TreeView + Right Details ListView
        splitter = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        sel_bar = QHBoxLayout()
        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.clicked.connect(self.select_all_folders)
        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_deselect_all.clicked.connect(self.deselect_all_folders)
        sel_bar.addWidget(self.btn_select_all)
        sel_bar.addWidget(self.btn_deselect_all)
        sel_bar.addStretch()
        left_layout.addLayout(sel_bar)

        self.tv_mbox_files = QTreeView()
        self.tv_mbox_files.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(TREE_COLUMNS)
        self.tree_model.itemChanged.connect(self._on_tree_item_changed)
        self.tv_mbox_files.setModel(self.tree_model)
        self.tv_mbox_files.header().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.tv_mbox_files.selectionModel().currentChanged.connect(
            self.on_folder_selected
        )
        left_layout.addWidget(self.tv_mbox_files)
        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_group_details = QLabel("Select a folder group to view its copies.")
        self.lv_group_files = QListView()
        self.lv_group_files.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.files_model = QStringListModel()
        self.lv_group_files.setModel(self.files_model)
        right_layout.addWidget(self.lbl_group_details)
        right_layout.addWidget(self.lv_group_files)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter, stretch=3)

        # 3. Progress Bar & Step Buttons
        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        main_layout.addWidget(self.progress)

        actions_layout = QHBoxLayout()
        self.btn_search = QPushButton("1. Scan && Group Folders")
        self.btn_search.setEnabled(False)
        self.btn_search.clicked.connect(self.do_search)

        self.btn_dedup = QPushButton("2. Deduplicate Checked Folders")
        self.btn_dedup.setEnabled(False)
        self.btn_dedup.clicked.connect(self.do_deduplicate)

        self.btn_move = QPushButton("3. Move to Reconstructed Tree")
        self.btn_move.setEnabled(False)
        self.btn_move.clicked.connect(self.do_move)

        actions_layout.addWidget(self.btn_search)
        actions_layout.addWidget(self.btn_dedup)
        actions_layout.addWidget(self.btn_move)
        main_layout.addLayout(actions_layout)

        # 4. Log Output Area
        self.txt_logs = QTextEdit()
        self.txt_logs.setReadOnly(True)
        main_layout.addWidget(self.txt_logs, stretch=1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        main_widget = QWidget()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        if initial_options is not None and getattr(initial_options, "location", None):
            self.txt_path.setText(initial_options.location)

    def _schedule_coro(self, coro):
        try:
            loop = asyncio.get_running_loop()
            return loop.create_task(coro)
        except RuntimeError:
            return asyncio.run(coro)

    def build_options(self):
        storage_text = self.txt_storage_path.text().strip() or None
        output_text = self.txt_output_path.text().strip() or None
        pattern_text = self.txt_folder_pattern.text().strip() or "Inbox.sbd/"
        return runner.TbDedupOptions(
            location=self.txt_path.text().strip(),
            storage_location=storage_text,
            output_location=output_text,
            folder_pattern=pattern_text,
            msg_hash_source=self.cmb_hash_source.currentText(),
        )

    @Slot(str)
    def log_receipt(self, message):
        self.txt_logs.append(message)
        self.status_bar.showMessage(message)

    @Slot(int, int)
    def on_progress_updated(self, completed, total):
        if total > 0:
            self.progress.setMaximum(total)
            self.progress.setValue(completed)
        else:
            self.progress.setMaximum(100)
            self.progress.setValue(0)

    @Slot()
    def path_changed(self):
        path = self.txt_path.text().strip()
        search_enabled = os.path.isdir(path)
        self.btn_search.setEnabled(search_enabled)
        self.btn_dedup.setEnabled(False)
        self.btn_move.setEnabled(False)
        self.record_log.emit(f"Search enabled: {search_enabled}")

    def _choose_directory(self, line_edit, caption):
        current_path = line_edit.text().strip()
        folder_path = QFileDialog.getExistingDirectory(
            self,
            caption=caption,
            dir=(
                current_path
                if os.path.isdir(current_path)
                else os.environ.get("HOME", "/")
            ),
            options=QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if folder_path:
            self.record_log.emit(f"{caption}: {folder_path}")
            line_edit.setText(folder_path)
        else:
            self.record_log.emit(f"{caption} cancelled")

    @Slot()
    def select_path(self):
        self._choose_directory(self.txt_path, "Select Source Path")

    @Slot()
    def select_storage_path(self):
        self._choose_directory(self.txt_storage_path, "Select Work/Storage Directory")

    @Slot()
    def select_output_path(self):
        self._choose_directory(self.txt_output_path, "Select Output Directory")

    @Slot()
    def do_search(self):
        options = self.build_options()
        self.record_log.emit(f"Searching {options.location}...")
        self._schedule_coro(self.runner.scan_and_preplan(options))

    @Slot(object)
    def on_preplan_completed(self, preplanner):
        self.tree_model.removeRows(0, self.tree_model.rowCount())
        self._row_items_by_root.clear()
        self.files_model.setStringList([])

        dir_nodes = {}

        for root_file, plan in sorted(preplanner.plans()):
            parts = [p for p in root_file.split("/") if p]
            parent_item = self.tree_model.invisibleRootItem()
            prefix_parts = []
            for part in parts[:-1]:
                prefix_parts.append(part)
                dir_key = "/".join(prefix_parts)
                if dir_key not in dir_nodes:
                    dir_item = QStandardItem(part)
                    dir_item.setCheckable(True)
                    dir_item.setCheckState(Qt.Checked)
                    row = [dir_item] + [QStandardItem("") for _ in TREE_COLUMNS[1:]]
                    parent_item.appendRow(row)
                    dir_nodes[dir_key] = dir_item
                parent_item = dir_nodes[dir_key]

            leaf_name = parts[-1] if parts else root_file
            folder_item = QStandardItem(leaf_name)
            folder_item.setCheckable(True)
            folder_item.setCheckState(Qt.Checked)
            folder_item.setData(root_file, Qt.UserRole)

            source_bytes = sum(
                os.path.getsize(f) for f in plan.files if os.path.exists(f)
            )
            copies_item = QStandardItem(str(len(plan.files)))
            size_item = QStandardItem(combinatory.format_bytes(source_bytes))
            total_msgs_item = QStandardItem("-")
            unique_msgs_item = QStandardItem("-")
            dedup_size_item = QStandardItem("-")
            status_item = QStandardItem("Pending")

            row_items = [
                folder_item,
                copies_item,
                size_item,
                total_msgs_item,
                unique_msgs_item,
                dedup_size_item,
                status_item,
            ]
            parent_item.appendRow(row_items)
            self._row_items_by_root[root_file] = row_items

        self.tv_mbox_files.expandAll()
        self._update_dedup_button_state()
        self.btn_move.setEnabled(False)

    def _on_tree_item_changed(self, item):
        if item.column() != 0:
            return
        state = item.checkState()
        self.tree_model.blockSignals(True)
        try:
            self._set_children_check_state(item, state)
        finally:
            self.tree_model.blockSignals(False)
        self._update_dedup_button_state()

    def _set_children_check_state(self, parent_item, state):
        for row_idx in range(parent_item.rowCount()):
            child = parent_item.child(row_idx, 0)
            if child is not None:
                child.setCheckState(state)
                self._set_children_check_state(child, state)

    def get_checked_root_files(self):
        checked = []
        for root_file, row_items in self._row_items_by_root.items():
            if row_items[0].checkState() == Qt.Checked:
                checked.append(root_file)
        return checked

    def _update_dedup_button_state(self):
        self.btn_dedup.setEnabled(len(self.get_checked_root_files()) > 0)

    @Slot()
    def select_all_folders(self):
        self._set_all_check_states(Qt.Checked)

    @Slot()
    def deselect_all_folders(self):
        self._set_all_check_states(Qt.Unchecked)

    def _set_all_check_states(self, state):
        self.tree_model.blockSignals(True)
        try:
            root = self.tree_model.invisibleRootItem()
            self._set_children_check_state(root, state)
        finally:
            self.tree_model.blockSignals(False)
        self._update_dedup_button_state()

    def on_folder_selected(self, current_index, previous_index):
        if not current_index.isValid():
            return
        col0_index = current_index.siblingAtColumn(0)
        item = self.tree_model.itemFromIndex(col0_index)
        if item is None:
            return
        root_file = item.data(Qt.UserRole)
        if not root_file or self.runner.preplanner is None:
            self.lbl_group_details.setText(f"Directory: {item.text()}")
            self.files_model.setStringList([])
            return
        plan = dict(self.runner.preplanner.plans()).get(root_file)
        if plan is not None:
            self.lbl_group_details.setText(
                f"{root_file} ({len(plan.files)} MBOX copies)"
            )
            self.files_model.setStringList(plan.files)

    @Slot()
    def do_deduplicate(self):
        selected = self.get_checked_root_files()
        if not selected:
            return
        options = self.build_options()
        self.btn_dedup.setEnabled(False)
        self._schedule_coro(
            self.runner.deduplicate_selected(options, selected)
        )

    @Slot(str, object, str)
    def on_plan_dedup_updated(self, root_file, plan, status):
        row_items = self._row_items_by_root.get(root_file)
        if row_items is None:
            return
        stats = (plan.combinatory or {}).get(planner_keys.plan_stats, {})
        if stats:
            row_items[3].setText(
                str(stats.get(planner_keys.plan_stats_total_messages, 0))
            )
            row_items[4].setText(
                str(stats.get(planner_keys.plan_stats_unique_messages, 0))
            )
            row_items[5].setText(
                combinatory.format_bytes(
                    stats.get(planner_keys.plan_stats_dedup_bytes, 0)
                )
            )
        row_items[6].setText(status)

    @Slot(object, str, str)
    def on_dedup_completed(self, worker_results, temp_directory, reconstructed_root):
        if not self.txt_output_path.text().strip():
            self.txt_output_path.setText(reconstructed_root)
        self._update_dedup_button_state()
        self.btn_move.setEnabled(len(worker_results) > 0)

    @Slot()
    def do_move(self):
        options = self.build_options()
        target_root = (
            options.output_location or self.runner.reconstructed_root
        )
        summary = combinatory.build_summary_report(
            options,
            self.runner.temp_directory,
            target_root,
            self.runner.worker_results,
        )
        reply = QMessageBox.question(
            self,
            "Confirm Move to Reconstructed Tree",
            f"{summary}\n\nProceed with moving deduplicated MBOX files to:\n{target_root}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.btn_move.setEnabled(False)
            self._schedule_coro(
                self.runner.move_results(
                    options,
                    self.runner.worker_results,
                    target_root,
                )
            )
        else:
            self.record_log.emit(
                f"Move cancelled; deduplicated files remain in {self.runner.temp_directory}"
            )

    @Slot(str)
    def on_move_completed(self, operation_json_path):
        self.record_log.emit(f"Operation completed: {operation_json_path}")
