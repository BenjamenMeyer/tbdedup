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
    QApplication,
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
    "Saved",
    "Status",
]
DIR_KEY_ROLE = Qt.UserRole + 1


class MainWindow(QMainWindow):
    record_log = Signal(str)

    def __init__(self, initial_options=None):
        super().__init__()
        self.runner = runner.TbDedupRunner()
        self.runner.record_log.connect(self.log_receipt)
        self.runner.progress_updated.connect(self.on_progress_updated)
        self.runner.overall_progress_updated.connect(
            self.on_overall_progress_updated
        )
        self.runner.copy_progress_updated.connect(self.on_copy_progress_updated)
        self.runner.file_progress_updated.connect(self.on_file_progress_updated)
        self.runner.write_progress_updated.connect(
            self.on_write_progress_updated
        )
        self.runner.plan_live_status_updated.connect(
            self.on_plan_live_status_updated
        )
        self.runner.preplan_complete.connect(self.on_preplan_completed)
        self.runner.plan_dedup_updated.connect(self.on_plan_dedup_updated)
        self.runner.dedup_complete.connect(self.on_dedup_completed)
        self.runner.move_complete.connect(self.on_move_completed)
        self.runner.operation_cancelled.connect(self.on_operation_cancelled)
        self.record_log.connect(self.log_receipt)

        self._row_items_by_root = {}
        self._dir_rows_by_key = {}
        self._leaf_stats = {}
        self._active_task = None

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

        # 3. Four-Tier Progress Bars & Step Buttons
        self.progress_overall = QProgressBar()
        self.progress_overall.setMinimum(0)
        self.progress_overall.setMaximum(100)
        self.progress_overall.setValue(0)
        self.progress_overall.setTextVisible(True)
        self.progress_overall.setFormat("Overall Folder Groups: Idle")
        self.progress = self.progress_overall
        main_layout.addWidget(self.progress_overall)

        self.progress_copies = QProgressBar()
        self.progress_copies.setMinimum(0)
        self.progress_copies.setMaximum(100)
        self.progress_copies.setValue(0)
        self.progress_copies.setTextVisible(True)
        self.progress_copies.setFormat("Folder Copies: Idle")
        main_layout.addWidget(self.progress_copies)

        self.progress_file = QProgressBar()
        self.progress_file.setMinimum(0)
        self.progress_file.setMaximum(1000)
        self.progress_file.setValue(0)
        self.progress_file.setTextVisible(True)
        self.progress_file.setFormat("Current Copy Read: Idle")
        main_layout.addWidget(self.progress_file)

        self.progress_write = QProgressBar()
        self.progress_write.setMinimum(0)
        self.progress_write.setMaximum(100)
        self.progress_write.setValue(0)
        self.progress_write.setTextVisible(True)
        self.progress_write.setFormat("Deduplicated Output Write: Idle")
        main_layout.addWidget(self.progress_write)

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

        self.btn_cancel = QPushButton("Cancel Operation")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.do_cancel)

        actions_layout.addWidget(self.btn_search)
        actions_layout.addWidget(self.btn_dedup)
        actions_layout.addWidget(self.btn_move)
        actions_layout.addWidget(self.btn_cancel)
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

    def _on_task_done(self, task):
        if self._active_task is task:
            self._active_task = None
            self.btn_cancel.setEnabled(False)

    def _schedule_coro(self, coro):
        self.btn_cancel.setEnabled(True)
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(coro)
            self._active_task = task
            task.add_done_callback(self._on_task_done)
            return task
        except RuntimeError:
            try:
                return asyncio.run(coro)
            finally:
                self._active_task = None
                self.btn_cancel.setEnabled(False)

    def closeEvent(self, event):
        if self._active_task is not None and not self._active_task.done():
            self._active_task.cancel()
        super().closeEvent(event)

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

    @staticmethod
    def _update_bar(bar, current, total, label=None):
        if total > 0:
            bar.setMaximum(total)
            bar.setValue(min(current, total))
        elif total == 0 and current == 0 and label and "Scanning" in label:
            bar.setMaximum(0)
            bar.setValue(0)
        else:
            bar.setMaximum(100)
            bar.setValue(0)
        if label is not None:
            bar.setFormat(label)

    @Slot(int, int)
    def on_progress_updated(self, completed, total):
        self._update_bar(self.progress_overall, completed, total)

    @Slot(int, int, str)
    def on_overall_progress_updated(self, completed, total, label):
        self._update_bar(self.progress_overall, completed, total, label)

    @Slot(int, int, str)
    def on_copy_progress_updated(self, completed, total, label):
        self._update_bar(self.progress_copies, completed, total, label)

    @Slot(int, int, str)
    def on_file_progress_updated(self, current, maximum, label):
        self._update_bar(self.progress_file, current, maximum, label)

    @Slot(int, int, str)
    def on_write_progress_updated(self, written, total, label):
        self._update_bar(self.progress_write, written, total, label)

    @Slot()
    def do_cancel(self):
        if self._active_task is not None and not self._active_task.done():
            self.btn_cancel.setEnabled(False)
            self.record_log.emit("Cancelling current operation...")
            self._active_task.cancel()

    @Slot(str)
    def on_operation_cancelled(self, message):
        self.btn_cancel.setEnabled(False)
        self.btn_search.setEnabled(os.path.exists(self.txt_path.text()))
        self._update_dedup_button_state()
        self.btn_move.setEnabled(len(self.runner.worker_results) > 0)
        self._update_bar(self.progress_overall, 0, 100, f"Cancelled: {message}")
        self._update_bar(self.progress_copies, 0, 100, "Folder Copies: Cancelled")
        self._update_bar(self.progress_file, 0, 1000, "Current Copy Read: Cancelled")
        self._update_bar(
            self.progress_write, 0, 100, "Deduplicated Output Write: Cancelled"
        )

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
        self._dir_rows_by_key.clear()
        self._leaf_stats.clear()
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
                    dir_item.setData(dir_key, DIR_KEY_ROLE)
                    row = [dir_item] + [QStandardItem("") for _ in TREE_COLUMNS[1:]]
                    parent_item.appendRow(row)
                    dir_nodes[dir_key] = dir_item
                    self._dir_rows_by_key[dir_key] = row
                parent_item = dir_nodes[dir_key]

            leaf_name = parts[-1] if parts else root_file
            folder_item = QStandardItem(leaf_name)
            folder_item.setCheckable(True)
            folder_item.setCheckState(Qt.Checked)
            folder_item.setData(root_file, Qt.UserRole)

            source_bytes = sum(
                os.path.getsize(f) for f in plan.files if os.path.exists(f)
            )
            num_copies = len(plan.files)
            copies_item = QStandardItem(str(num_copies))
            size_item = QStandardItem(combinatory.format_bytes(source_bytes))
            total_msgs_item = QStandardItem("-")
            unique_msgs_item = QStandardItem("-")
            dedup_size_item = QStandardItem("-")
            saved_item = QStandardItem("-")
            status_item = QStandardItem("Pending")

            row_items = [
                folder_item,
                copies_item,
                size_item,
                total_msgs_item,
                unique_msgs_item,
                dedup_size_item,
                saved_item,
                status_item,
            ]
            parent_item.appendRow(row_items)
            self._row_items_by_root[root_file] = row_items
            self._leaf_stats[root_file] = {
                "copies_done": 0,
                "copies_total": num_copies,
                "source_bytes": source_bytes,
                "total_msgs": None,
                "unique_msgs": None,
                "dedup_bytes": None,
                "status": "Pending",
            }

        self._update_all_sbd_summaries()
        self.tv_mbox_files.expandAll()
        self._update_dedup_button_state()
        self.btn_move.setEnabled(False)

    def _compute_sbd_summary(self, dir_key):
        prefix = dir_key + "/"
        descendants = [
            stats
            for rf, stats in self._leaf_stats.items()
            if rf.startswith(prefix)
        ]
        folder_count = len(descendants)
        copies_done = sum(d["copies_done"] for d in descendants)
        copies_total = sum(d["copies_total"] for d in descendants)
        source_bytes = sum(d["source_bytes"] for d in descendants)

        completed_leaves = [
            d for d in descendants if d["dedup_bytes"] is not None
        ]
        completed_count = len(completed_leaves)
        moved_count = sum(1 for d in descendants if d["status"] == "Moved")
        skipped_count = sum(1 for d in descendants if d["status"] == "Skipped")
        selected_count = folder_count - skipped_count
        active_count = sum(
            1
            for d in descendants
            if d["status"]
            not in ("Pending", "Skipped", "Deduplicated", "Moved", "Failed")
        )

        if completed_leaves:
            total_msgs = sum(d["total_msgs"] or 0 for d in completed_leaves)
            unique_msgs = sum(d["unique_msgs"] or 0 for d in completed_leaves)
            dedup_bytes = sum(d["dedup_bytes"] or 0 for d in completed_leaves)
            comp_source_bytes = sum(d["source_bytes"] for d in completed_leaves)
            saved_bytes = max(0, comp_source_bytes - dedup_bytes)
            saved_pct = (
                (saved_bytes / comp_source_bytes) * 100.0
                if comp_source_bytes > 0
                else 0.0
            )
        else:
            total_msgs = None
            unique_msgs = None
            dedup_bytes = None
            saved_bytes = None
            saved_pct = 0.0

        if folder_count > 0 and skipped_count == folder_count:
            status_text = "Skipped"
        elif selected_count > 0 and moved_count == selected_count:
            status_text = f"Moved ({moved_count}/{selected_count})"
        elif selected_count > 0 and completed_count == selected_count:
            status_text = f"Deduplicated ({completed_count}/{selected_count})"
        elif active_count > 0 or completed_count > 0:
            status_text = f"Active ({completed_count}/{selected_count} done)"
        elif skipped_count > 0:
            status_text = f"Pending ({selected_count}/{folder_count} folders)"
        else:
            status_text = f"Pending ({folder_count} folders)"

        return {
            "folder_count": folder_count,
            "completed_count": completed_count,
            "copies_done": copies_done,
            "copies_total": copies_total,
            "source_bytes": source_bytes,
            "total_msgs": total_msgs,
            "unique_msgs": unique_msgs,
            "dedup_bytes": dedup_bytes,
            "saved_bytes": saved_bytes,
            "saved_pct": saved_pct,
            "status_text": status_text,
        }

    def _update_sbd_summary_row(self, dir_key):
        row = self._dir_rows_by_key.get(dir_key)
        if row is None:
            return
        summary = self._compute_sbd_summary(dir_key)
        if summary["copies_done"] > 0:
            row[1].setText(
                f"{summary['copies_done']} / {summary['copies_total']}"
            )
        else:
            row[1].setText(str(summary["copies_total"]))
        row[2].setText(combinatory.format_bytes(summary["source_bytes"]))
        if summary["total_msgs"] is not None:
            removed = max(0, summary["total_msgs"] - summary["unique_msgs"])
            row[3].setText(f"{summary['total_msgs']:,}")
            row[4].setText(f"{summary['unique_msgs']:,} (-{removed:,})")
            row[5].setText(combinatory.format_bytes(summary["dedup_bytes"]))
            row[6].setText(
                f"{combinatory.format_bytes(summary['saved_bytes'])} "
                f"({summary['saved_pct']:.1f}%)"
            )
        else:
            row[3].setText("-")
            row[4].setText("-")
            row[5].setText("-")
            row[6].setText("-")
        row[7].setText(summary["status_text"])

    def _update_ancestor_sbd_summaries(self, root_file):
        parts = [p for p in root_file.split("/") if p]
        prefix_parts = []
        for part in parts[:-1]:
            prefix_parts.append(part)
            dir_key = "/".join(prefix_parts)
            self._update_sbd_summary_row(dir_key)

    def _update_all_sbd_summaries(self):
        for dir_key in self._dir_rows_by_key:
            self._update_sbd_summary_row(dir_key)

    def _sync_selection_statuses(self):
        for root_file, row_items in self._row_items_by_root.items():
            leaf = self._leaf_stats.get(root_file)
            if leaf is None:
                continue
            if leaf["status"] in ("Pending", "Skipped"):
                new_status = (
                    "Pending"
                    if row_items[0].checkState() == Qt.Checked
                    else "Skipped"
                )
                leaf["status"] = new_status
                row_items[7].setText(new_status)
        self._update_all_sbd_summaries()

    def _on_tree_item_changed(self, item):
        if item.column() != 0:
            return
        state = item.checkState()
        self.tree_model.blockSignals(True)
        try:
            self._set_children_check_state(item, state)
            self._sync_selection_statuses()
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
            self._sync_selection_statuses()
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
            dir_key = item.data(DIR_KEY_ROLE)
            if dir_key and dir_key in self._dir_rows_by_key:
                summary = self._compute_sbd_summary(dir_key)
                self.lbl_group_details.setText(
                    f"Subtree Summary: {dir_key} "
                    f"({summary['folder_count']} folders, {summary['copies_total']} copies)"
                )
                details = [
                    f"Subtree Path: {dir_key}",
                    f"Logical Subfolders: {summary['folder_count']} ({summary['completed_count']} deduplicated)",
                    f"Total MBOX Copies: {summary['copies_done']} / {summary['copies_total']}",
                    f"Total Source Size: {combinatory.format_bytes(summary['source_bytes'])}",
                ]
                if summary["dedup_bytes"] is not None:
                    removed = max(
                        0, (summary["total_msgs"] or 0) - (summary["unique_msgs"] or 0)
                    )
                    details.extend(
                        [
                            f"Messages Indexed: {summary['total_msgs']:,}",
                            f"Unique Messages Kept: {summary['unique_msgs']:,} ({removed:,} duplicates removed)",
                            f"Deduplicated Size: {combinatory.format_bytes(summary['dedup_bytes'])}",
                            f"Space Saved: {combinatory.format_bytes(summary['saved_bytes'])} ({summary['saved_pct']:.1f}%)",
                        ]
                    )
                self.files_model.setStringList(details)
            else:
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

    @Slot(str, str, str)
    def on_plan_live_status_updated(self, root_file, copies_text, status_text):
        row_items = self._row_items_by_root.get(root_file)
        if row_items is None:
            return
        row_items[1].setText(copies_text)
        row_items[7].setText(status_text)
        leaf = self._leaf_stats.get(root_file)
        if leaf is not None:
            parts = copies_text.split("/")
            if len(parts) == 2:
                try:
                    leaf["copies_done"] = int(parts[0].strip())
                except ValueError:
                    pass
            leaf["status"] = status_text
            self._update_ancestor_sbd_summaries(root_file)

    @Slot(str, object, str)
    def on_plan_dedup_updated(self, root_file, plan, status):
        row_items = self._row_items_by_root.get(root_file)
        if row_items is None:
            return
        stats = (plan.combinatory or {}).get(planner_keys.plan_stats, {})
        leaf = self._leaf_stats.get(root_file)
        if stats:
            total_msgs = stats.get(planner_keys.plan_stats_total_messages, 0)
            unique_msgs = stats.get(planner_keys.plan_stats_unique_messages, 0)
            source_bytes = stats.get(planner_keys.plan_stats_source_bytes, 0)
            dedup_bytes = stats.get(planner_keys.plan_stats_dedup_bytes, 0)
            saved_bytes = max(0, source_bytes - dedup_bytes)
            saved_pct = (
                (saved_bytes / source_bytes) * 100.0 if source_bytes > 0 else 0.0
            )
            removed = max(0, total_msgs - unique_msgs)
            row_items[1].setText(f"{len(plan.files)} / {len(plan.files)}")
            row_items[3].setText(f"{total_msgs:,}")
            row_items[4].setText(f"{unique_msgs:,} (-{removed:,})")
            row_items[5].setText(combinatory.format_bytes(dedup_bytes))
            row_items[6].setText(
                f"{combinatory.format_bytes(saved_bytes)} ({saved_pct:.1f}%)"
            )
            if leaf is not None:
                leaf["copies_done"] = len(plan.files)
                leaf["total_msgs"] = total_msgs
                leaf["unique_msgs"] = unique_msgs
                leaf["dedup_bytes"] = dedup_bytes
        row_items[7].setText(status)
        if leaf is not None:
            leaf["status"] = status
            self._update_ancestor_sbd_summaries(root_file)

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
