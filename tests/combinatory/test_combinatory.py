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
import json as std_json
import os
import os.path
from unittest import mock

from thunderbirddedup import (
    combinatory,
    mbox,
)
from thunderbirddedup.planner import (
    keys as planner_keys,
    plan as planner_plan,
    walk as planner_walk,
)

from tests import base


class TestCombinatory(base.AsyncioTestCase):

    def test_format_bytes(self):
        self.assertEqual(combinatory.format_bytes(500), "500.00 B")
        self.assertEqual(combinatory.format_bytes(2048), "2.00 KB")
        self.assertEqual(combinatory.format_bytes(5 * 1024 * 1024), "5.00 MB")
        self.assertEqual(
            combinatory.format_bytes(3 * 1024 * 1024 * 1024),
            "3.00 GB",
        )
        self.assertEqual(
            combinatory.format_bytes(2 * 1024 * 1024 * 1024 * 1024),
            "2.00 TB",
        )

    def test_get_reconstructed_mbox_path(self):
        # Standard reconstructed root does not end with Inbox.sbd
        path1 = combinatory.get_reconstructed_mbox_path(
            "/tmp/run/reconstructed",
            "Inbox.sbd/",
            "Inbox.sbd/Activities.sbd/Scouts",
        )
        self.assertEqual(
            path1,
            "/tmp/run/reconstructed/Inbox.sbd/Activities.sbd/Scouts",
        )

        # Target directory already ending in Inbox.sbd should not duplicate Inbox.sbd
        path2 = combinatory.get_reconstructed_mbox_path(
            "/home/user/Mail/Local Folders/Inbox.sbd",
            "Inbox.sbd/",
            "Inbox.sbd/Activities.sbd/Scouts",
        )
        self.assertEqual(
            path2,
            "/home/user/Mail/Local Folders/Inbox.sbd/Activities.sbd/Scouts",
        )

    def test_get_plan_output_directory(self):
        out_dir = combinatory.get_plan_output_directory(
            "Inbox.sbd/",
            "/tmp/work",
            "Inbox.sbd/Activities.sbd/Scouts",
        )
        self.assertEqual(out_dir, "/tmp/work/Inbox_Activities_Scouts_Dedup")

    async def test_run_dedup_success_and_failure(self):
        with base.KeepLocalDirClean() as cwd:
            plan = planner_walk.PreplannerFileManager("Inbox.sbd/Activities")
            plan.combinatory = {
                planner_keys.plan_location: {},
            }

            async def ok_task():
                out_file = os.path.join(cwd.temp_dir.name, "dedup.mbox")
                with open(out_file, "wb") as f:
                    f.write(b"test")
                return out_file

            res_dir, res_plan, res_file = await combinatory.runDedup(
                cwd.temp_dir.name,
                plan,
                ok_task(),
                counter_update=lambda: None,
            )
            self.assertIsNotNone(res_file)
            self.assertIn(planner_keys.plan_stats, res_plan.combinatory)

            async def fail_task():
                raise RuntimeError("dedup failure")

            res_dir2, res_plan2, res_file2 = await combinatory.runDedup(
                cwd.temp_dir.name,
                plan,
                fail_task(),
            )
            self.assertIsNone(res_file2)

    async def test_move_dedup_mbox_none(self):
        plan = mock.MagicMock()
        await combinatory.move_dedup_mbox(
            "/tmp/reconstructed",
            "Inbox.sbd/",
            plan,
            None,
        )

    def test_confirm_move_prompt_responses(self):
        options = base.GenericOptions(
            location="/mail/Inbox.sbd",
            yes=False,
        )
        plan = mock.MagicMock()
        plan.combinatory = {
            planner_keys.plan_stats: {
                planner_keys.plan_stats_source_files: 2,
                planner_keys.plan_stats_source_bytes: 0,
                planner_keys.plan_stats_dedup_bytes: 0,
                planner_keys.plan_stats_total_messages: 2,
                planner_keys.plan_stats_unique_messages: 1,
            },
        }
        worker_results = [("/tmp/work", plan, "/tmp/work/dedup.mbox")]

        with mock.patch("builtins.input", return_value="yes"):
            self.assertTrue(
                combinatory.confirm_move(
                    options,
                    "/tmp/work",
                    "/tmp/reconstructed",
                    worker_results,
                )
            )

        with mock.patch("builtins.input", return_value="n"):
            self.assertFalse(
                combinatory.confirm_move(
                    options,
                    "/tmp/work",
                    "/tmp/reconstructed",
                    worker_results,
                )
            )

        with mock.patch("builtins.input", side_effect=EOFError):
            self.assertFalse(
                combinatory.confirm_move(
                    options,
                    "/tmp/work",
                    "/tmp/reconstructed",
                    worker_results,
                )
            )

    async def test_async_combinatory_end_to_end_recursive_tree(self):
        with base.KeepLocalDirClean() as cwd:
            mail_root = os.path.join(cwd.temp_dir.name, "Mail", "Inbox.sbd")
            storage_dir = os.path.join(cwd.temp_dir.name, "storage")
            reconstructed_dir = os.path.join(cwd.temp_dir.name, "reconstructed")
            os.makedirs(storage_dir, exist_ok=True)

            # Top-level Activities folder and recursive copy under Kids.sbd/Inbox.sbd
            top_activities = os.path.join(mail_root, "Activities")
            rec_activities = os.path.join(
                mail_root,
                "Activities.sbd",
                "Scouts.sbd",
                "Kids.sbd",
                "Inbox.sbd",
                "Activities",
            )
            scouts_mbox = os.path.join(mail_root, "Activities.sbd", "Scouts")
            os.makedirs(os.path.dirname(rec_activities), exist_ok=True)

            dt1 = "Mon Jan 01 00:00:00 2024"
            dt2 = "Tue Jan 02 00:00:00 2024"

            # Message 1 is in both top_activities (expunged) and rec_activities (starred)
            msg1_copy1 = (
                f"From - {dt1}\n"
                "X-Mozilla-Status: 0008\n"
                "X-Mozilla-Status2: 00000000\n"
                "Subject: Shared Message\n"
                "\n"
                "Shared body\n"
            )
            msg1_copy2 = (
                f"From - {dt1}\n"
                "X-Mozilla-Status: 0005\n"
                "X-Mozilla-Status2: 00000000\n"
                "Subject: Shared Message\n"
                "\n"
                "Shared body\n"
            )
            # Message 2 only exists in the deep recursive folder
            msg2_unique = (
                f"From - {dt2}\n"
                "X-Mozilla-Status: 0001\n"
                "X-Mozilla-Status2: 00000000\n"
                "Subject: Deep Unique Message\n"
                "\n"
                "Unique body in recursive copy\n"
            )

            with open(top_activities, "wt") as f:
                f.write(msg1_copy1)
            with open(rec_activities, "wt") as f:
                f.write(msg1_copy2 + "\n" + msg2_unique)
            with open(scouts_mbox, "wt") as f:
                f.write(msg1_copy2)

            options = base.GenericOptions(
                location=mail_root,
                storage_location=storage_dir,
                output_location=reconstructed_dir,
                folder_pattern="Inbox.sbd/",
                limit_pattern=None,
                msg_hash_source="parsed",
                yes=True,
            )

            await combinatory.asyncCombinatory(options)

            # Verify reconstructed folder hierarchy exists without recursive loop
            recon_activities = os.path.join(
                reconstructed_dir,
                "Inbox.sbd",
                "Activities",
            )
            recon_scouts = os.path.join(
                reconstructed_dir,
                "Inbox.sbd",
                "Activities.sbd",
                "Scouts",
            )
            self.assertTrue(os.path.isfile(recon_activities))
            self.assertTrue(os.path.isfile(recon_scouts))
            self.assertFalse(
                os.path.exists(
                    os.path.join(
                        reconstructed_dir,
                        "Inbox.sbd",
                        "Activities.sbd",
                        "Scouts.sbd",
                        "Kids.sbd",
                    )
                )
            )

            # Verify reconstructed Activities has both unique messages and merged status
            box = mbox.Mailbox(None, recon_activities)
            msgs = list(box.buildSummary())
            self.assertEqual(len(msgs), 2)
            statuses = {
                m.headers["Subject"][0].strip(): m.getMozillaStatus()
                for m in msgs
            }
            self.assertEqual(statuses[b"Subject: Shared Message"], 0x0005)
            self.assertEqual(statuses[b"Subject: Deep Unique Message"], 0x0001)

            # Verify combinatory_operation.json was written with final_mbox and stats
            op_json_path = os.path.join(
                storage_dir,
                "combinatory_operation.json",
            )
            self.assertTrue(os.path.isfile(op_json_path))
            with open(op_json_path, "rt") as f:
                op_data = std_json.load(f)
            act_plan = op_data["preplanner"]["planning"]["Inbox.sbd/Activities"]["combinatory"]
            self.assertEqual(
                act_plan["location"]["final_mbox"],
                recon_activities,
            )
            self.assertEqual(act_plan["stats"]["total_messages"], 3)
            self.assertEqual(act_plan["stats"]["unique_messages"], 2)

    async def test_combinatory_edge_cases(self):
        with base.KeepLocalDirClean() as cwd:
            options = base.GenericOptions(
                location=cwd.temp_dir.name,
                storage_location=None,
                output_location=None,
                folder_pattern="Inbox.sbd/",
                limit_pattern=None,
                msg_hash_source="parsed",
                yes=False,
            )

            # 1. Empty mboxfiles -> no plans
            await combinatory.combinatory(options, [])

            # Create a valid mbox file for remaining edge cases
            mbox_path = os.path.join(
                cwd.temp_dir.name,
                "Inbox.sbd",
                "Activities",
            )
            os.makedirs(os.path.dirname(mbox_path), exist_ok=True)
            with open(mbox_path, "wt") as f:
                f.write(
                    "From - Mon Jan 01 00:00:00 2024\n"
                    "Subject: Edge Case\n\nBody\n"
                )
            folder = mbox.MailboxFolder(cwd.temp_dir.name)
            mboxfiles = await folder.getMboxFiles()

            # 2. GenerationError during planner_plan.generate
            with mock.patch(
                "thunderbirddedup.combinatory.planner_plan.generate",
                side_effect=planner_plan.GenerationError("gen error"),
            ):
                await combinatory.combinatory(options, mboxfiles)

            # 3. resource.setrlimit failure when raising limit
            with mock.patch(
                "thunderbirddedup.combinatory.resource.getrlimit",
                return_value=(1, 1),
            ), mock.patch(
                "thunderbirddedup.combinatory.resource.setrlimit",
                side_effect=OSError("setrlimit denied"),
            ):
                await combinatory.combinatory(options, mboxfiles)

            # 4. User declines confirmation prompt -> move skipped, operation JSON written
            with mock.patch("builtins.input", return_value="n"):
                await combinatory.combinatory(options, mboxfiles)
