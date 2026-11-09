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
import subprocess
import sys
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (  # noqa: E402
    QModelIndex,
    Qt,
)
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QMessageBox,
)

from thunderbirddedup import gui  # noqa: E402
from thunderbirddedup.gui import (  # noqa: E402
    app,
    runner,
)

from tests import base  # noqa: E402


class TestGui(base.AsyncioTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.qapp = QApplication.instance() or QApplication([])

    async def test_gui_workflow_end_to_end(self):
        with base.KeepLocalDirClean() as cwd:
            mail_root = os.path.join(cwd.temp_dir.name, "Inbox.sbd")
            storage_dir = os.path.join(cwd.temp_dir.name, "storage")
            recon_dir = os.path.join(cwd.temp_dir.name, "reconstructed")
            os.makedirs(storage_dir, exist_ok=True)

            act_top = os.path.join(mail_root, "Activities")
            scouts_mbox = os.path.join(mail_root, "Activities.sbd", "Scouts")
            os.makedirs(os.path.dirname(scouts_mbox), exist_ok=True)

            msg = (
                "From - Mon Jan 01 00:00:00 2024\n"
                "X-Mozilla-Status: 0001\n"
                "Subject: GUI Test\n\nBody\n"
            )
            with open(act_top, "wt") as f:
                f.write(msg)
            with open(scouts_mbox, "wt") as f:
                f.write(msg)

            init_opts = runner.TbDedupOptions(location=mail_root)
            win = await gui.asyncGui(init_opts)
            self.assertEqual(win.txt_path.text(), mail_root)
            self.assertTrue(win.btn_search.isEnabled())

            # Configure storage and output paths via dialog helpers
            with mock.patch(
                "thunderbirddedup.gui.app.QFileDialog.getExistingDirectory",
                return_value=mail_root,
            ):
                win.select_path()
            with mock.patch(
                "thunderbirddedup.gui.app.QFileDialog.getExistingDirectory",
                return_value=storage_dir,
            ):
                win.select_storage_path()
            with mock.patch(
                "thunderbirddedup.gui.app.QFileDialog.getExistingDirectory",
                return_value="",
            ):
                win.select_output_path()

            # Step 1: Scan & Preplan
            win.do_search()
            await asyncio.sleep(0.05)
            # Wait for pending tasks
            for task in asyncio.all_tasks():
                if task is not asyncio.current_task():
                    await task

            self.assertEqual(len(win.get_checked_root_files()), 2)
            self.assertTrue(win.btn_dedup.isEnabled())

            # Test Select All / Deselect All and tree selection details
            win.deselect_all_folders()
            self.assertEqual(len(win.get_checked_root_files()), 0)
            self.assertFalse(win.btn_dedup.isEnabled())
            self.assertEqual(
                win._row_items_by_root["Inbox.sbd/Activities"][7].text(),
                "Skipped",
            )
            self.assertEqual(win._dir_rows_by_key["Inbox.sbd"][7].text(), "Skipped")

            win.select_all_folders()
            self.assertEqual(len(win.get_checked_root_files()), 2)
            self.assertTrue(win.btn_dedup.isEnabled())
            self.assertEqual(
                win._row_items_by_root["Inbox.sbd/Activities"][7].text(),
                "Pending",
            )
            self.assertIn("Pending", win._dir_rows_by_key["Inbox.sbd"][7].text())

            # Select directory node vs leaf folder node in QTreeView
            win.on_folder_selected(QModelIndex(), QModelIndex())
            inbox_index = win.tree_model.index(0, 0)
            win.on_folder_selected(inbox_index, QModelIndex())
            act_item = win._row_items_by_root["Inbox.sbd/Activities"][0]
            win.on_folder_selected(act_item.index(), QModelIndex())
            self.assertEqual(len(win.files_model.stringList()), 1)

            # Toggle single item check state
            act_item.setCheckState(Qt.Unchecked)
            self.assertEqual(len(win.get_checked_root_files()), 1)
            self.assertEqual(
                win._row_items_by_root["Inbox.sbd/Activities"][7].text(),
                "Skipped",
            )
            self.assertEqual(
                win._dir_rows_by_key["Inbox.sbd"][7].text(),
                "Pending (1/2 folders)",
            )
            act_item.setCheckState(Qt.Checked)
            self.assertEqual(
                win._row_items_by_root["Inbox.sbd/Activities"][7].text(),
                "Pending",
            )

            # Step 2: Deduplicate Checked Folders
            win.do_deduplicate()
            for task in asyncio.all_tasks():
                if task is not asyncio.current_task():
                    await task

            # Inspect .sbd directory node after deduplication to verify rolled-up stats
            win.on_folder_selected(inbox_index, QModelIndex())
            self.assertTrue(
                any(
                    "Space Saved:" in line
                    for line in win.files_model.stringList()
                )
            )
            sbd_row = win._dir_rows_by_key["Inbox.sbd"]
            self.assertIn("Deduplicated", sbd_row[7].text())

            self.assertTrue(win.btn_move.isEnabled())
            self.assertTrue(win.txt_output_path.text().endswith("reconstructed"))
            win.txt_output_path.setText(recon_dir)

            # Step 3a: Cancel move confirmation dialog
            with mock.patch(
                "thunderbirddedup.gui.app.QMessageBox.question",
                return_value=QMessageBox.No,
            ):
                win.do_move()

            # Step 3b: Confirm move dialog
            with mock.patch(
                "thunderbirddedup.gui.app.QMessageBox.question",
                return_value=QMessageBox.Yes,
            ):
                win.do_move()
                for task in asyncio.all_tasks():
                    if task is not asyncio.current_task():
                        await task

            self.assertIn("Moved", sbd_row[7].text())
            self.assertTrue(
                os.path.isfile(
                    os.path.join(recon_dir, "Inbox.sbd", "Activities")
                )
            )
            win.close()

    async def test_cancellation_and_batch_progress(self):
        with base.KeepLocalDirClean() as cwd:
            mail_root = os.path.join(cwd.temp_dir.name, "Inbox.sbd")
            storage_dir = os.path.join(cwd.temp_dir.name, "storage")
            os.makedirs(mail_root, exist_ok=True)
            os.makedirs(storage_dir, exist_ok=True)

            big_mbox = os.path.join(mail_root, "BigFolder")
            with open(big_mbox, "wt") as f:
                for idx in range(260):
                    f.write(
                        f"From - Mon Jan 01 00:00:00 2024\n"
                        f"Message-ID: <msg-{idx}@example.com>\n"
                        f"X-Mozilla-Status: 0001\n"
                        f"Subject: Msg {idx}\n\n"
                        f"Body {idx}\n\n"
                    )

            win = app.MainWindow(
                initial_options=runner.TbDedupOptions(location=mail_root)
            )
            win.txt_storage_path.setText(storage_dir)

            # Run full scan + deduplicate on 260 unique messages (triggers >=250 callbacks)
            win.do_search()
            for task in asyncio.all_tasks():
                if task is not asyncio.current_task():
                    await task

            win.do_deduplicate()
            for task in asyncio.all_tasks():
                if task is not asyncio.current_task():
                    await task

            self.assertEqual(win.progress_write.value(), 260)

            # Test cancelling an in-flight scan task via do_cancel()
            async def slow_get_files():
                await asyncio.sleep(10)
                return []

            with mock.patch(
                "thunderbirddedup.gui.runner.mbox.MailboxFolder.getMboxFiles",
                side_effect=slow_get_files,
            ):
                win.do_search()
                await asyncio.sleep(0)
                self.assertTrue(win.btn_cancel.isEnabled())
                win.do_cancel()
                for task in asyncio.all_tasks():
                    if task is not asyncio.current_task():
                        with self.assertRaises(asyncio.CancelledError):
                            await task
                self.assertIn("Cancelled", win.progress_overall.format())

            # Test cancelling an in-flight deduplicate_selected task
            async def slow_run_dedup(*args, **kwargs):
                await asyncio.sleep(10)

            with mock.patch(
                "thunderbirddedup.gui.runner.combinatory.runDedup",
                side_effect=slow_run_dedup,
            ):
                win.do_deduplicate()
                await asyncio.sleep(0.02)
                win.do_cancel()
                for task in asyncio.all_tasks():
                    if task is not asyncio.current_task():
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

            # Test cancelling an in-flight move_results task via closeEvent
            async def slow_move(*args, **kwargs):
                await asyncio.sleep(10)

            with mock.patch(
                "thunderbirddedup.gui.app.QMessageBox.question",
                return_value=QMessageBox.Yes,
            ), mock.patch(
                "thunderbirddedup.gui.runner.combinatory.move_dedup_mbox",
                side_effect=slow_move,
            ):
                win.do_move()
                await asyncio.sleep(0)
                win.close()
                for task in asyncio.all_tasks():
                    if task is not asyncio.current_task():
                        with self.assertRaises(asyncio.CancelledError):
                            await task

    async def test_runner_and_main_edge_cases(self):
        r = runner.TbDedupRunner()
        opts = runner.TbDedupOptions(location="/nonexistent")
        # deduplicate_selected when preplanner is None
        res = await r.deduplicate_selected(opts, ["Inbox.sbd/Activities"])
        self.assertEqual(res, [])

        # Progress update with total == 0
        win = app.MainWindow()
        win.on_progress_updated(0, 0)
        win.do_deduplicate()
        win.close()

        # Test gui.main() and gui.run_gui() entry points
        with mock.patch("thunderbirddedup.gui.QtAsyncio.run") as mock_qtrun:
            ret = gui.main()
            self.assertEqual(ret, 0)
            mock_qtrun.assert_called_once_with(
                keep_running=True, handle_sigint=True
            )

        with mock.patch(
            "thunderbirddedup.cmd.asyncMain",
            new=mock.MagicMock(return_value="coro"),
        ), mock.patch("thunderbirddedup.gui.QtAsyncio.run") as mock_qtrun:
            ret = gui.run_gui()
            self.assertEqual(ret, 0)
            mock_qtrun.assert_called_once_with(
                "coro", keep_running=True, handle_sigint=True
            )

    def test_qtasyncio_execution_no_reentrancy_crash(self):
        code = (
            "import asyncio, os, tempfile\n"
            "from PySide6.QtWidgets import QApplication\n"
            "from PySide6 import QtAsyncio\n"
            "from thunderbirddedup import gui\n"
            "from thunderbirddedup.gui import runner\n"
            "os.environ['QT_QPA_PLATFORM'] = 'offscreen'\n"
            "app = QApplication([])\n"
            "async def main():\n"
            "    with tempfile.TemporaryDirectory() as tmpdir:\n"
            "        mail_root = os.path.join(tmpdir, 'Inbox.sbd')\n"
            "        os.makedirs(mail_root, exist_ok=True)\n"
            "        for i in range(3):\n"
            "            folder = os.path.join(mail_root, f'Folder{i}')\n"
            "            with open(folder, 'wt') as f:\n"
            "                f.write('From - Mon Jan 01 00:00:00 2024\\nX-Mozilla-Status: 0001\\nSubject: Hi\\n\\nBody\\n')\n"
            "        opts = runner.TbDedupOptions(location=mail_root)\n"
            "        win = await gui.asyncGui(opts)\n"
            "        await win.runner.scan_and_preplan(opts)\n"
            "        win.do_deduplicate()\n"
            "        while win._active_task is not None and not win._active_task.done():\n"
            "            await asyncio.sleep(0.01)\n"
            "        assert len(win.runner.worker_results) == 3\n"
            "        app.quit()\n"
            "QtAsyncio.run(main(), keep_running=True)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, f"Error: {result.stderr}")

    async def test_button_states_and_cancel_lifecycle(self):
        with base.KeepLocalDirClean() as cwd:
            mail_root = os.path.join(cwd.temp_dir.name, "mail")
            os.makedirs(mail_root, exist_ok=True)
            opts = runner.TbDedupOptions(location=mail_root)
            win = await gui.asyncGui(opts)

            # Initially idle with valid path: search enabled, cancel disabled, move disabled
            self.assertFalse(win.is_running())
            self.assertTrue(win.btn_search.isEnabled())
            self.assertFalse(win.btn_dedup.isEnabled())
            self.assertFalse(win.btn_move.isEnabled())
            self.assertFalse(win.btn_cancel.isEnabled())

            # Start an in-flight operation: cancel MUST be enabled, all action buttons disabled
            async def dummy_slow_coro():
                await asyncio.sleep(0.5)

            task = win._schedule_coro(dummy_slow_coro())
            self.assertTrue(win.is_running())
            self.assertTrue(win.btn_cancel.isEnabled())
            self.assertFalse(win.btn_search.isEnabled())
            self.assertFalse(win.btn_dedup.isEnabled())
            self.assertFalse(win.btn_move.isEnabled())

            # Cancel the running operation
            win.do_cancel()
            await asyncio.sleep(0.02)
            for t in asyncio.all_tasks():
                if t is not asyncio.current_task():
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass

            # Once stopped: cancel disabled, search re-enabled
            self.assertFalse(win.is_running())
            self.assertFalse(win.btn_cancel.isEnabled())
            self.assertTrue(win.btn_search.isEnabled())
            win.close()

    async def test_disk_data_discovery_and_recovery(self):
        with base.KeepLocalDirClean() as cwd:
            mail_root = os.path.join(cwd.temp_dir.name, "Inbox.sbd")
            storage_dir = os.path.join(cwd.temp_dir.name, "storage")
            os.makedirs(mail_root, exist_ok=True)
            os.makedirs(storage_dir, exist_ok=True)

            f1 = os.path.join(mail_root, "Folder1")
            with open(f1, "wt") as f:
                f.write("From - Mon Jan 01 00:00:00 2024\nX-Mozilla-Status: 0001\nSubject: Hi\n\nBody\n")

            opts = runner.TbDedupOptions(
                location=mail_root,
                storage_location=storage_dir,
            )
            win = await gui.asyncGui(opts)
            win.txt_storage_path.setText(storage_dir)

            # Create synthetic completed plan on disk
            plan_dir = os.path.join(storage_dir, "Inbox_Folder1_Dedup")
            os.makedirs(plan_dir, exist_ok=True)
            mbox_path = os.path.join(plan_dir, "output_deduplicated.mbox")
            with open(mbox_path, "wt") as f:
                f.write("Deduplicated data\n")
            plan_json_path = os.path.join(plan_dir, "plan_output.json")
            from thunderbirddedup.planner import keys as p_keys
            from thunderbirddedup.utils import json as util_json
            fake_plan_data = {
                "files": [f1],
                "combinatory": {
                    p_keys.plan_location: {
                        p_keys.plan_source: "Inbox.sbd/Folder1",
                        p_keys.plan_output: plan_dir,
                        p_keys.plan_mbox: mbox_path,
                    },
                    p_keys.plan_stats: {
                        p_keys.plan_stats_source_files: 1,
                        p_keys.plan_stats_source_bytes: 100,
                        p_keys.plan_stats_dedup_bytes: 50,
                        p_keys.plan_stats_total_messages: 1,
                        p_keys.plan_stats_unique_messages: 1,
                    },
                },
            }
            util_json.dump_to_file(plan_json_path, fake_plan_data)

            # Scan and verify sync with disk data
            win.do_search()
            await asyncio.sleep(0.05)
            for t in asyncio.all_tasks():
                if t is not asyncio.current_task():
                    await t

            # Verify Folder1 was recovered from disk data as Deduplicated
            row = win._row_items_by_root.get("Inbox.sbd/Folder1")
            self.assertIsNotNone(row)
            self.assertEqual(row[7].text(), "Deduplicated")
            self.assertTrue(win.btn_move.isEnabled())

            # Test storage_path_changed slot
            win.storage_path_changed()
            self.assertTrue(win.btn_move.isEnabled())
            win.close()

    async def test_plan_failure_captured_and_logged(self):
        with base.KeepLocalDirClean() as cwd:
            mail_root = os.path.join(cwd.temp_dir.name, "Inbox.sbd")
            os.makedirs(mail_root, exist_ok=True)
            f1 = os.path.join(mail_root, "BadFolder")
            with open(f1, "wt") as f:
                f.write("From - Mon Jan 01 00:00:00 2024\nX-Mozilla-Status: 0001\nSubject: Hi\n\nBody\n")

            opts = runner.TbDedupOptions(location=mail_root)
            win = await gui.asyncGui(opts)
            win.do_search()
            await asyncio.sleep(0.05)
            for t in asyncio.all_tasks():
                if t is not asyncio.current_task():
                    await t

            # Simulate an unhandled exception during deduplication of BadFolder
            with mock.patch(
                "thunderbirddedup.gui.runner.combinatory.runDedup",
                side_effect=RuntimeError("Simulated disk error"),
            ):
                win.do_deduplicate()
                await asyncio.sleep(0.05)
                for t in asyncio.all_tasks():
                    if t is not asyncio.current_task():
                        await t

            row = win._row_items_by_root.get("Inbox.sbd/BadFolder")
            self.assertIsNotNone(row)
            self.assertTrue(row[7].text().startswith("Failed"))
            self.assertIn("Simulated disk error", row[7].toolTip())
            self.assertIn("FAILED: Inbox.sbd/BadFolder", win.txt_logs.toPlainText())
            win.close()

    async def test_gui_cleanup_workflow(self):
        with base.KeepLocalDirClean() as cwd:
            mail_root = os.path.join(cwd.temp_dir.name, "Inbox.sbd")
            storage_dir = os.path.join(cwd.temp_dir.name, "storage")
            os.makedirs(mail_root, exist_ok=True)
            os.makedirs(storage_dir, exist_ok=True)

            opts = runner.TbDedupOptions(
                location=mail_root,
                storage_location=storage_dir,
            )
            win = await gui.asyncGui(opts)
            win.txt_storage_path.setText(storage_dir)

            # 1. Cleanup button should be enabled when idle
            self.assertTrue(win.btn_cleanup.isEnabled())

            # 2. Prevent cleanup on source directory
            win.txt_storage_path.setText(mail_root)
            with mock.patch("thunderbirddedup.gui.app.QMessageBox.critical") as mock_crit:
                win.do_cleanup(mail_root)
                mock_crit.assert_called_once()

            # 3. Clean up directory with no files
            win.txt_storage_path.setText(storage_dir)
            with mock.patch("thunderbirddedup.gui.app.QMessageBox.information") as mock_info:
                win.do_cleanup(storage_dir)
                mock_info.assert_called_once()

            # 4. Clean up symlinks only
            # Create a mock symlink in storage_dir
            plan_dir = os.path.join(storage_dir, "Folder_Dedup")
            os.makedirs(plan_dir, exist_ok=True)
            dummy_src = os.path.join(cwd.temp_dir.name, "dummy.mbox")
            with open(dummy_src, "wt") as f:
                f.write("content\n")
            link = os.path.join(plan_dir, "000001.mbox")
            os.symlink(dummy_src, link)

            # Mock QMessageBox to simulate clicking "Remove Symlinks Only (Safe)"
            class FakeMsgBox:
                def __init__(self, parent=None):
                    self.buttons = []
                    self.clicked = None

                def setWindowTitle(self, title):
                    pass

                def setIcon(self, icon):
                    pass

                def setText(self, text):
                    pass

                def setDefaultButton(self, btn):
                    pass

                def addButton(self, btn_or_label, role=None):
                    self.buttons.append(btn_or_label)
                    return btn_or_label

                def exec(self):
                    # Click first button: "Remove Symlinks Only (Safe)"
                    self.clicked = self.buttons[0]

                def clickedButton(self):
                    return self.clicked

            with mock.patch(
                "thunderbirddedup.gui.app.QMessageBox", side_effect=FakeMsgBox
            ), mock.patch(
                "thunderbirddedup.gui.app.QMessageBox.information"
            ):
                win.do_cleanup(storage_dir)
                self.assertFalse(os.path.exists(link))
                self.assertTrue(os.path.exists(dummy_src))

            win.close()
