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
