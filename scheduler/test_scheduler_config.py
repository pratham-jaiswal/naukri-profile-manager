import ast
import json
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

try:
    import fcntl  # noqa: F401
except ImportError:
    fcntl_stub = types.ModuleType("fcntl")
    fcntl_stub.LOCK_EX = 1
    fcntl_stub.LOCK_NB = 2
    fcntl_stub.LOCK_UN = 3
    fcntl_stub.flock = lambda *_args: None
    sys.modules["fcntl"] = fcntl_stub

from scheduler import scheduler


def valid_config():
    return {
        "updates_per_day": 3,
        "windows": [
            {"start": "08:00", "end": "09:00", "action": "headline"},
            {"start": "10:00", "end": "11:00", "action": "resume"},
            {"start": "12:00", "end": "13:00", "action": "random"},
        ],
        "random_action_options": ["headline", "resume", "both"],
    }


@contextmanager
def no_lock(_path, blocking=True):
    yield


class SchedulerConfigTests(unittest.TestCase):
    def test_accepts_configuration_without_timezone(self):
        cfg = valid_config()

        validated = scheduler.validate_config(cfg)

        self.assertEqual(validated, cfg)
        self.assertNotIn("timezone", validated)

    def test_legacy_timezone_is_ignored_without_rewriting_file_on_read(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.json"
            legacy_config = valid_config()
            legacy_config["timezone"] = "Asia/Kolkata"
            config_path.write_text(json.dumps(legacy_config))
            original_contents = config_path.read_text()

            with patch.object(scheduler, "CONFIG", config_path):
                cfg = scheduler.read_config()

            self.assertNotIn("timezone", cfg)
            self.assertEqual(config_path.read_text(), original_contents)

    def test_invalid_config_json_has_clear_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.json"
            config_path.write_text('{"updates_per_day":')

            with patch.object(scheduler, "CONFIG", config_path):
                with self.assertRaisesRegex(ValueError, "must contain valid JSON"):
                    scheduler.read_config()

    def test_rejects_non_integer_update_count(self):
        cfg = valid_config()
        cfg["updates_per_day"] = 2.5

        with self.assertRaisesRegex(ValueError, "must be an integer"):
            scheduler.validate_config(cfg)

    def test_rejects_invalid_time_formats_and_ranges(self):
        for value in ("9:00", "25:00", "09:60", "nine"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "Invalid time"):
                    scheduler.minutes(value)

    def test_rejects_invalid_actions_and_overlapping_windows(self):
        invalid_action = valid_config()
        invalid_action["windows"][2]["action"] = "invalid"
        with self.assertRaisesRegex(ValueError, "Invalid action"):
            scheduler.validate_config(invalid_action)

        overlapping = valid_config()
        overlapping["windows"][2]["start"] = "10:30"
        with self.assertRaisesRegex(ValueError, "must not overlap"):
            scheduler.validate_config(overlapping)

    def test_rejects_malformed_window_json(self):
        for serialized in ('[{"start":', '{"start":"09:00"}'):
            with self.subTest(serialized=serialized):
                with self.assertRaisesRegex(ValueError, "valid JSON array"):
                    scheduler.parse_windows_json(serialized)

    def test_config_updates_preserve_legacy_migration_and_reject_invalid_input(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            config_path = directory / "config.json"
            original = valid_config()
            original["timezone"] = "Asia/Kolkata"
            config_path.write_text(json.dumps(original))

            with (
                patch.object(scheduler, "CONFIG", config_path),
                patch.object(scheduler, "SDIR", directory),
            ):
                saved = scheduler.update_config({
                    "updates_per_day": 2,
                    "windows": original["windows"][:2],
                })
                self.assertEqual(saved["updates_per_day"], 2)
                persisted = json.loads(config_path.read_text())
                self.assertNotIn("timezone", persisted)
                self.assertEqual(persisted["windows"], original["windows"][:2])

                unchanged = config_path.read_text()
                invalid_windows = original["windows"][:]
                invalid_windows[0] = dict(invalid_windows[0], start="9:00")
                for changes in (
                    {"updates_per_day": 3, "windows": invalid_windows},
                    {"timezone": "Asia/Kolkata"},
                ):
                    with self.subTest(changes=changes):
                        with self.assertRaises(ValueError):
                            scheduler.update_config(changes)
                        self.assertEqual(config_path.read_text(), unchanged)

    def test_cron_replaces_only_managed_block_and_preserves_generator(self):
        generator_job = (
            "5 0 * * * cd /home/ubuntu/naukri-resume-action && "
            "/usr/bin/python3 scheduler/scheduler.py generate "
            ">> scheduler/cron.log 2>&1"
        )
        existing_cron = "\n".join((
            "# custom crontab comment",
            generator_job,
            "17 4 * * * /usr/local/bin/keep-before",
            scheduler.BEGIN,
            "CRON_TZ=Asia/Kolkata",
            "5 0 * * * /old/scheduler.py generate",
            "30 9 * * * /old/scheduler.py run 1",
            scheduler.END,
            "CRON_TZ=Asia/Kolkata",
            "20 5 * * * /usr/local/bin/keep-after",
        )) + "\n"
        responses = [
            types.SimpleNamespace(returncode=0, stdout=existing_cron, stderr=""),
            types.SimpleNamespace(returncode=0, stdout="", stderr=""),
        ]
        runs = [
            {"id": 1, "time": "09:30"},
            {"id": 2, "time": "13:30"},
            {"id": 3, "time": "18:30"},
        ]

        with patch.object(scheduler.subprocess, "run", side_effect=responses) as run:
            scheduler.install_generated_jobs(runs)

        installed = run.call_args_list[1].kwargs["input"]
        start_index = installed.splitlines().index(scheduler.BEGIN)
        end_index = installed.splitlines().index(scheduler.END)
        block = "\n".join(installed.splitlines()[start_index : end_index + 1])

        self.assertEqual(block.count(scheduler.BEGIN), 1)
        self.assertEqual(block.count(scheduler.END), 1)
        self.assertNotIn("CRON_TZ", block)
        self.assertNotIn("/old/scheduler.py", installed)
        self.assertEqual(installed.count(generator_job), 1)
        self.assertIn("17 4 * * * /usr/local/bin/keep-before", installed)
        self.assertIn("20 5 * * * /usr/local/bin/keep-after", installed)
        self.assertNotIn("CRON_TZ=Asia/Kolkata", installed)
        self.assertEqual(run.call_args_list[0].args[0], ["crontab", "-l"])
        self.assertEqual(run.call_args_list[1].args[0], ["crontab", "-"])

    def test_cron_block_contains_no_timezone_setting_without_legacy_block(self):
        response = types.SimpleNamespace(
            returncode=0,
            stdout="* * * * * /usr/local/bin/keep\n",
            stderr="",
        )
        with (
            patch.object(scheduler.subprocess, "run", side_effect=[response, response]) as run,
            redirect_stdout(StringIO()),
        ):
            output = scheduler.install_generated_jobs(
                [{"id": 1, "time": "09:30"}], dry_run=True
            )

        self.assertEqual(run.call_count, 1)
        block = output.split(scheduler.BEGIN, 1)[1].split(scheduler.END, 1)[0]
        self.assertNotIn("CRON_TZ", block)
        self.assertIn("30 9 * * *", block)

    def test_malformed_generated_blocks_abort_before_crontab_write(self):
        malformed_crontabs = (
            f"custom-before\n{scheduler.BEGIN}\ncustom-inside\n",
            f"custom-before\n{scheduler.END}\ncustom-after\n",
            f"{scheduler.BEGIN}\n{scheduler.END}\n"
            f"{scheduler.BEGIN}\n{scheduler.END}\n",
        )
        expected_errors = (
            "no matching end",
            "no matching start",
            "Multiple generated cron blocks",
        )

        for content, expected_error in zip(malformed_crontabs, expected_errors):
            with self.subTest(expected_error=expected_error):
                response = types.SimpleNamespace(
                    returncode=0, stdout=content, stderr=""
                )
                with patch.object(
                    scheduler.subprocess, "run", return_value=response
                ) as run:
                    with self.assertRaisesRegex(ValueError, expected_error):
                        scheduler.install_generated_jobs(
                            [{"id": 1, "time": "09:30"}]
                        )
                self.assertEqual(run.call_count, 1)

    def test_local_now_uses_host_timezone(self):
        before = datetime.now().astimezone()
        actual = scheduler.local_now()
        after = datetime.now().astimezone()

        self.assertIsNotNone(actual.tzinfo)
        self.assertIn(actual.utcoffset(), {before.utcoffset(), after.utcoffset()})
        self.assertIn(actual.tzname(), {before.tzname(), after.tzname()})

    def test_generate_uses_local_date_and_does_not_store_timezone(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            state_path = directory / "today.json"
            local_date = datetime(2026, 1, 1, 1, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
            runs = [{"id": 1, "time": "09:30", "action": "headline"}]

            with (
                patch.object(scheduler, "STATE", state_path),
                patch.object(scheduler, "STATE_LOCK", directory / ".state.lock"),
                patch.object(scheduler, "read_config", return_value=valid_config()),
                patch.object(scheduler, "local_now", return_value=local_date),
                patch.object(scheduler, "locked", no_lock),
                patch.object(scheduler, "create_runs", return_value=runs),
                patch.object(scheduler, "install_generated_jobs") as install,
                patch.object(scheduler, "notify"),
                redirect_stdout(StringIO()),
            ):
                scheduler.generate()

            state = json.loads(state_path.read_text())
            self.assertEqual(state["date"], "2026-01-01")
            self.assertNotIn("timezone", state)
            install.assert_called_once_with(runs)

    def test_force_regeneration_remains_blocked_after_first_window_begins(self):
        local_now = datetime(
            2026, 1, 1, 8, 30, tzinfo=scheduler.local_now().tzinfo
        )
        with (
            patch.object(scheduler, "read_config", return_value=valid_config()),
            patch.object(scheduler, "local_now", return_value=local_now),
            patch.object(scheduler, "locked", no_lock),
        ):
            with self.assertRaisesRegex(
                ValueError, "after the first update window has begun"
            ):
                scheduler.generate(force=True)

    def test_dry_run_preserves_saved_state_and_uses_local_date(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "today.json"
            local_date = datetime(2026, 1, 1, 1, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
            runs = [{"id": 1, "time": "00:15", "action": "headline"}]
            state = {
                "date": local_date.date().isoformat(),
                "timezone": "Asia/Kolkata",
                "runs": runs,
            }
            state_path.write_text(json.dumps(state))
            original_contents = state_path.read_text()

            with (
                patch.object(scheduler, "STATE", state_path),
                patch.object(scheduler, "read_config", return_value=valid_config()),
                patch.object(scheduler, "local_now", return_value=local_date),
                patch.object(scheduler, "install_generated_jobs") as install,
                redirect_stdout(StringIO()),
            ):
                scheduler.generate(dry_run=True)

            self.assertEqual(state_path.read_text(), original_contents)
            install.assert_called_once_with(runs, dry_run=True)

    def test_run_refuses_schedule_after_local_date_rollover(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "today.json"
            state_path.write_text(json.dumps({
                "date": "2025-12-31",
                "timezone": "Asia/Kolkata",
                "runs": [{"id": 1, "status": "pending", "action": "headline"}],
            }))
            local_now = datetime(
                2026, 1, 1, 0, 5, tzinfo=timezone(timedelta(hours=5, minutes=30))
            )

            with (
                patch.object(scheduler, "STATE", state_path),
                patch.object(scheduler, "SDIR", Path(temporary_directory)),
                patch.object(scheduler, "read_config", return_value=valid_config()),
                patch.object(scheduler, "local_now", return_value=local_now),
                patch.object(scheduler, "locked", no_lock),
                patch.object(scheduler.subprocess, "run") as run,
                redirect_stdout(StringIO()),
            ):
                scheduler._run_update(1)

            run.assert_not_called()

    def test_bot_does_not_register_timezone_command(self):
        bot_source = Path(__file__).resolve().parent.parent / "bot" / "bot.py"
        tree = ast.parse(bot_source.read_text(encoding="utf-8"))
        command_names = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Attribute):
                    continue
                if decorator.func.attr != "command":
                    continue
                for keyword in decorator.keywords:
                    if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                        command_names.append(keyword.value.value)

        self.assertNotIn("schedule_timezone", command_names)
        self.assertIn("schedule_config", command_names)
        self.assertIn("schedule_show", command_names)
        self.assertIn("schedule_regenerate", command_names)

        regenerate = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "schedule_regenerate_command"
        )
        self.assertIn(
            scheduler.NO_ERROR_NOTIFICATION,
            [
                node.value
                for node in ast.walk(regenerate)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            ],
        )

    def test_command_triggered_regeneration_failure_is_not_webhook_notified(self):
        with (
            patch.object(
                scheduler,
                "generate",
                side_effect=RuntimeError("regeneration is not allowed now"),
            ),
            patch.object(scheduler, "notify") as notify,
            redirect_stderr(StringIO()),
        ):
            exit_code = scheduler.run_cli([
                "generate",
                "--force",
                scheduler.NO_ERROR_NOTIFICATION,
            ])

        self.assertEqual(exit_code, 1)
        notify.assert_not_called()

    def test_cron_triggered_failure_still_sends_webhook_alert(self):
        with (
            patch.object(
                scheduler,
                "run_update",
                side_effect=RuntimeError("scheduled run failed"),
            ),
            patch.object(scheduler, "notify") as notify,
            redirect_stderr(StringIO()),
        ):
            exit_code = scheduler.run_cli(["run", "1"])

        self.assertEqual(exit_code, 1)
        notify.assert_called_once()
        self.assertIn("Naukri scheduler error", notify.call_args.args[0])
        self.assertIn("scheduled run failed", notify.call_args.args[0])


if __name__ == "__main__":
    unittest.main()