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
import sys
from unittest import mock

from thunderbirddedup import cmd

from tests import base


class TestCmd(base.AsyncioTestCase):

    async def test_async_main_subcommands_and_log_config(self):
        with base.KeepLocalDirClean() as cwd:
            # 1. dedup subcommand returning None -> returns 0
            with mock.patch.object(
                sys,
                "argv",
                ["tb-dedup", "dedup", "-l", cwd.temp_dir.name],
            ), mock.patch(
                "thunderbirddedup.cmd.dedup.asyncDedup",
                new=mock.AsyncMock(return_value=None),
            ) as mock_dedup:
                ret = await cmd.asyncMain()
                self.assertEqual(ret, 0)
                mock_dedup.assert_awaited_once()

            # 2. do subcommand with --log-config returning explicit code
            with mock.patch.object(
                sys,
                "argv",
                [
                    "tb-dedup",
                    "--log-config",
                    "dummy.ini",
                    "do",
                    "-l",
                    cwd.temp_dir.name,
                    "-y",
                ],
            ), mock.patch(
                "thunderbirddedup.cmd.logging.config.fileConfig",
            ) as mock_file_config, mock.patch(
                "thunderbirddedup.cmd.combinatory.asyncCombinatory",
                new=mock.AsyncMock(return_value=42),
            ) as mock_comb:
                ret = await cmd.asyncMain()
                self.assertEqual(ret, 42)
                mock_file_config.assert_called_once_with("dummy.ini")
                mock_comb.assert_awaited_once()

            # 3. Exception raised by handler -> returns -1
            with mock.patch.object(
                sys,
                "argv",
                ["tb-dedup", "planner", "-l", cwd.temp_dir.name],
            ), mock.patch(
                "thunderbirddedup.cmd.planner_plan.asyncPlanner",
                new=mock.AsyncMock(side_effect=RuntimeError("boom")),
            ):
                ret = await cmd.asyncMain()
                self.assertEqual(ret, -1)

            # 4. gui subcommand dispatches to asyncGui
            fake_gui = mock.MagicMock()
            fake_gui.asyncGui = mock.AsyncMock(return_value=0)
            with mock.patch.object(
                sys,
                "argv",
                ["tb-dedup", "gui"],
            ), mock.patch.dict(
                sys.modules,
                {"thunderbirddedup.gui": fake_gui},
            ):
                ret = await cmd.asyncMain()
                self.assertEqual(ret, 0)
                fake_gui.asyncGui.assert_awaited_once()

    def test_main_tui_and_gui(self):
        with mock.patch.object(
            sys,
            "argv",
            ["tb-dedup", "preplanner", "-l", "/tmp"],
        ), mock.patch(
            "thunderbirddedup.cmd.asyncio.run",
        ) as mock_run:
            cmd.main()
            mock_run.assert_called_once()

        with mock.patch.object(
            sys,
            "argv",
            ["tb-dedup", "gui"],
        ), mock.patch(
            "thunderbirddedup.cmd.asyncio.run",
        ) as mock_run:
            cmd.main()
            mock_run.assert_called_once()
