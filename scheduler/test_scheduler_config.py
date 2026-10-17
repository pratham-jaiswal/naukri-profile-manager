import json
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager, redirect_stdout
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
        "timezone": "UTC",
        "updates_per_day": 3,
        "windows": [
            {"start": "08:00", "end": "09:00", "action": "headline"},
            {"start": "10:00", "end": "11:00", "action": "resume"},
            {"start": "12:00", "end": "13:00", "action": "random"},
        ],
        "random_action_options": ["headline", "resume", "both"],
    }


class SchedulerConfigTests(unittest.TestCase):
    def test_accepts_valid_configuration(self):
        cfg = valid_config()

        self.assertIs(scheduler.validate_config(cfg), cfg)

    def test_rejects_invalid_timezone(self):
        cfg = valid_config()
        cfg["timezone"] = "Not/A_Timezone"

        with self.assertRaisesRegex(ValueError, "Unknown timezone"):
            scheduler.validate_config(cfg)

    def test_rejects_non_integer_update_count(self):
        cfg = valid_config()
        cfg["updates_per_day"] = 2.5

        with self.assertRaisesRegex(ValueError, "must be an integer"):
            scheduler.validate_config(cfg)

    def test_rejects_invalid_time_formats(self):
        for value in ("9:00", "25:00", "09:60", "nine"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "Invalid time"):
                    scheduler.minutes(value)

    def test_rejects_malformed_window_json(self):
        with self.assertRaisesRegex(ValueError, "valid JSON array"):
            scheduler.parse_windows_json('[{"start":')

        with self.assertRaisesRegex(ValueError, "valid JSON array"):
            scheduler.parse_windows_json('{"start":"09:00"}')

    def test_rejects_invalid_or_overlapping_windows(self):
        cfg = valid_config()
        cfg["windows"][2]["start"] = "10:30"

        with self.assertRaisesRegex(ValueError, "must not overlap"):
            scheduler.validate_config(cfg)

    def test_rejects_window_count_larger_than_windows(self):
        cfg = valid_config()
        cfg["updates_per_day"] = 4

        with self.assertRaisesRegex(ValueError, "between 2 and the window count"):
            scheduler.validate_config(cfg)

    def test_saves_only_valid_config_updates(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            config_path = directory / "config.json"
            original = valid_config()
            config_path.write_text(json.dumps(original))

            with (
                patch.object(scheduler, "CONFIG", config_path),
                patch.object(scheduler, "SDIR", directory),
            ):
                saved = scheduler.update_config({
                    "timezone": "Europe/London",
                    "updates_per_day": 2,
                    "windows": original["windows"][:2],
                })
                self.assertEqual(saved["timezone"], "Europe/London")
                self.assertEqual(saved["updates_per_day"], 2)
                persisted = json.loads(config_path.read_text())
                self.assertEqual(persisted["timezone"], "Europe/London")
                self.assertEqual(persisted["updates_per_day"], 2)
                self.assertEqual(persisted["windows"], original["windows"][:2])

                unchanged = config_path.read_text()
                invalid_windows = original["windows"][:]
                invalid_windows[0] = dict(invalid_windows[0], start="9:00")
                for changes in (
                    {"timezone": "Not/A_Timezone"},
                    {"updates_per_day": 3, "windows": invalid_windows},
                ):
                    with self.subTest(changes=changes):
                        with self.assertRaises(ValueError):
                            scheduler.update_config(changes)
                        self.assertEqual(config_path.read_text(), unchanged)

    def test_cron_restores_previous_timezone_after_generated_block(self):
        existing_cron = (
            "17 4 * * * /usr/local/bin/keep-me\n"
            "CRON_TZ=America/Los_Angeles\n"
            f"{scheduler.BEGIN}\n"
            "5 0 * * * /old/scheduler.py generate\n"
            "30 9 * * * /old/scheduler.py run 1\n"
            f"{scheduler.END}\n"
            "CRON_TZ=America/New_York\n"
            "20 5 * * * /usr/local/bin/keep-after-block\n"
        )
        responses = [
            types.SimpleNamespace(returncode=0, stdout=existing_cron, stderr=""),
            types.SimpleNamespace(returncode=0, stdout="", stderr=""),
        ]
        runs = [{"id": 1, "time": "09:30"}]

        with patch.object(scheduler.subprocess, "run", side_effect=responses) as run:
            scheduler.install_generated_jobs(runs, "Europe/London")

        installed_cron = run.call_args_list[1].kwargs["input"]
        self.assertIn("17 4 * * * /usr/local/bin/keep-me", installed_cron)
        self.assertIn("20 5 * * * /usr/local/bin/keep-after-block", installed_cron)
        self.assertIn("CRON_TZ=Europe/London", installed_cron)
        self.assertIn("30 9 * * *", installed_cron)
        self.assertNotIn("scheduler.py generate", installed_cron)
        lines = installed_cron.splitlines()
        end_index = lines.index(scheduler.END)
        self.assertEqual(lines[end_index + 1], "CRON_TZ=America/New_York")
        self.assertEqual(lines.count(scheduler.BEGIN), 1)
        self.assertEqual(lines.count(scheduler.END), 1)
        self.assertIn("CRON_TZ=America/Los_Angeles", installed_cron)

    def test_cron_restores_system_timezone_when_none_was_set(self):
        response = types.SimpleNamespace(returncode=0, stdout="17 4 * * * keep\n", stderr="")
        runs = [{"id": 1, "time": "09:30"}]

        with (
            patch.object(scheduler.subprocess, "run", side_effect=[response, response]) as run,
            patch.object(scheduler, "system_timezone", return_value="Etc/UTC"),
        ):
            scheduler.install_generated_jobs(runs, "Europe/London")

        installed_cron = run.call_args_list[1].kwargs["input"]
        self.assertTrue(installed_cron.endswith(f"{scheduler.END}\nCRON_TZ=Etc/UTC\n"))

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
                            [{"id": 1, "time": "09:30"}], "UTC"
                        )
                self.assertEqual(run.call_count, 1)

    def test_cron_preview_handles_midnight_and_dst_timezone_without_writing(self):
        response = types.SimpleNamespace(returncode=0, stdout="", stderr="")
        runs = [
            {"id": 1, "time": "00:15"},
            {"id": 2, "time": "23:45"},
        ]
        with (
            patch.object(scheduler.subprocess, "run", return_value=response) as run,
            patch.object(scheduler, "system_timezone", return_value="Etc/UTC"),
            redirect_stdout(StringIO()),
        ):
            preview = scheduler.install_generated_jobs(
                runs, "America/New_York", dry_run=True
            )

        self.assertEqual(run.call_count, 1)
        self.assertIn("CRON_TZ=America/New_York", preview)
        self.assertIn("15 0 * * *", preview)
        self.assertIn("45 23 * * *", preview)
        self.assertIn(f"{scheduler.END}\nCRON_TZ=Etc/UTC", preview)
        self.assertNotIn("scheduler.py generate", preview)

        eastern = scheduler.ZoneInfo("America/New_York")
        before_spring = scheduler.datetime.fromisoformat(
            "2026-03-08T06:59:00+00:00"
        ).astimezone(eastern)
        after_spring = scheduler.datetime.fromisoformat(
            "2026-03-08T07:00:00+00:00"
        ).astimezone(eastern)
        first_fall = scheduler.datetime.fromisoformat(
            "2026-11-01T05:30:00+00:00"
        ).astimezone(eastern)
        second_fall = scheduler.datetime.fromisoformat(
            "2026-11-01T06:30:00+00:00"
        ).astimezone(eastern)
        self.assertEqual((before_spring.hour, before_spring.minute), (1, 59))
        self.assertEqual((after_spring.hour, after_spring.minute), (3, 0))
        self.assertEqual((first_fall.hour, first_fall.fold), (1, 0))
        self.assertEqual((second_fall.hour, second_fall.fold), (1, 1))

    def test_keeps_saved_timezone_when_reinstalling_today(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "today.json"
            runs = [{"id": 1, "time": "09:30", "action": "headline"}]
            state_path.write_text(json.dumps({
                "date": scheduler.datetime.now(
                    scheduler.ZoneInfo("Europe/London")
                ).date().isoformat(),
                "timezone": "UTC",
                "runs": runs,
            }))

            @contextmanager
            def no_lock(_path):
                yield

            config = valid_config()
            config["timezone"] = "Europe/London"
            with (
                patch.object(scheduler, "STATE", state_path),
                patch.object(scheduler, "STATE_LOCK", state_path.with_suffix(".lock")),
                patch.object(scheduler, "read_config", return_value=config),
                patch.object(scheduler, "locked", no_lock),
                patch.object(scheduler, "install_generated_jobs") as install,
                patch.object(scheduler, "notify"),
                redirect_stdout(StringIO()),
            ):
                scheduler.generate()

            install.assert_called_once_with(runs, "UTC")

    def test_generate_dry_run_does_not_modify_saved_state(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "today.json"
            runs = [{"id": 1, "time": "00:15", "action": "headline"}]
            state = {
                "date": scheduler.datetime.now(
                    scheduler.ZoneInfo("Europe/London")
                ).date().isoformat(),
                "timezone": "UTC",
                "runs": runs,
            }
            state_path.write_text(json.dumps(state))
            original_contents = state_path.read_text()
            config = valid_config()
            config["timezone"] = "Europe/London"

            with (
                patch.object(scheduler, "STATE", state_path),
                patch.object(scheduler, "read_config", return_value=config),
                patch.object(scheduler, "install_generated_jobs") as install,
                redirect_stdout(StringIO()),
            ):
                scheduler.generate(dry_run=True)

            self.assertEqual(state_path.read_text(), original_contents)
            install.assert_called_once_with(runs, "UTC", dry_run=True)


if __name__ == "__main__":
    unittest.main()