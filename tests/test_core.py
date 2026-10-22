from __future__ import annotations

from types import SimpleNamespace

import cinnamon_fingerprint_manager.core as core
from cinnamon_fingerprint_manager.core import (
    FINGER_LABEL,
    FINGERS,
    Result,
    available_fingers,
    build_delete_command,
    build_enroll_command,
    build_list_command,
    build_verify_command,
    classify_result,
    current_user,
    device_title,
    finger_label,
    parse_list_output,
    summarize_output,
)

SAMPLE_LIST = """found 1 devices
Device at /net/reactivated/Fprint/Device/0
Using device /net/reactivated/Fprint/Device/0
Fingerprints for user kisoya on AuthenTec AES2660 (swipe):
 - #0: left-index-finger
 - #1: right-index-finger
"""

SAMPLE_NO_SCAN_TYPE = """found 1 devices
Using device /net/reactivated/Fprint/Device/0
Fingerprints for user someone on Generic Sensor:
 - #0: right-thumb
"""

SAMPLE_NO_DEVICE = """found 0 devices
No devices available
"""

SAMPLE_NO_FINGERS = """found 1 devices
Device at /net/reactivated/Fprint/Device/0
Using device /net/reactivated/Fprint/Device/0
User nobody has no fingers enrolled for AuthenTec AES2660.
"""

SAMPLE_MULTI_DEVICE = """found 2 devices
Device at /net/reactivated/Fprint/Device/0
Using device /net/reactivated/Fprint/Device/0
Fingerprints for user kisoya on Sensor A (swipe):
 - #0: right-thumb
Device at /net/reactivated/Fprint/Device/1
Using device /net/reactivated/Fprint/Device/1
Fingerprints for user kisoya on Sensor B (press):
 - #0: left-thumb
"""

SAMPLE_NO_FINGERS_FIRST_DEVICE = """found 2 devices
Device at /net/reactivated/Fprint/Device/0
Using device /net/reactivated/Fprint/Device/0
User kisoya has no fingers enrolled for Sensor A.
Device at /net/reactivated/Fprint/Device/1
Using device /net/reactivated/Fprint/Device/1
Fingerprints for user kisoya on Sensor B (press):
 - #0: left-thumb
"""


class TestParseListOutput:
    def test_parses_device_scan_type_and_fingers(self):
        parsed = parse_list_output(SAMPLE_LIST)
        assert parsed.found is True
        assert parsed.device == "AuthenTec AES2660"
        assert parsed.scan_type == "swipe"
        assert parsed.fingers == ["left-index-finger", "right-index-finger"]

    def test_device_without_scan_type(self):
        parsed = parse_list_output(SAMPLE_NO_SCAN_TYPE)
        assert parsed.device == "Generic Sensor"
        assert parsed.scan_type is None
        assert parsed.fingers == ["right-thumb"]

    def test_no_device(self):
        parsed = parse_list_output(SAMPLE_NO_DEVICE)
        assert parsed.found is False
        assert parsed.device is None
        assert parsed.fingers == []

    def test_device_with_no_enrolled_fingers(self):
        text = "Fingerprints for user someone on Sensor X (press):\n"
        parsed = parse_list_output(text)
        assert parsed.device == "Sensor X"
        assert parsed.fingers == []

    def test_device_with_no_fingers_uses_real_fprintd_output(self):
        parsed = parse_list_output(SAMPLE_NO_FINGERS)
        assert parsed.found is True
        assert parsed.device == "AuthenTec AES2660"
        assert parsed.scan_type is None
        assert parsed.fingers == []

    def test_multiple_devices_only_uses_the_first_section(self):
        parsed = parse_list_output(SAMPLE_MULTI_DEVICE)
        assert parsed.device == "Sensor A"
        assert parsed.scan_type == "swipe"
        assert parsed.fingers == ["right-thumb"]

    def test_first_device_without_fingers_is_not_replaced_by_second(self):
        parsed = parse_list_output(SAMPLE_NO_FINGERS_FIRST_DEVICE)
        assert parsed.found is True
        assert parsed.device == "Sensor A"
        assert parsed.scan_type is None
        assert parsed.fingers == []

    def test_ignores_unrelated_lines(self):
        text = SAMPLE_LIST + "\nWarning: something else\n - not a finger\n"
        assert parse_list_output(text).fingers == [
            "left-index-finger",
            "right-index-finger",
        ]


class TestSummarizeOutput:
    def test_returns_last_non_empty_line(self):
        assert summarize_output("first\n\n  last  \n") == "last"

    def test_returns_empty_string_for_blank_output(self):
        assert summarize_output("\n \n") == ""


class TestLabels:
    def test_device_title_with_swipe_scan_type(self):
        assert device_title("AuthenTec AES2660", "swipe") == "AuthenTec AES2660（スワイプ式）"

    def test_device_title_with_press_scan_type(self):
        assert device_title("Sensor X", "press") == "Sensor X（押し当て式）"

    def test_device_title_with_unknown_scan_type(self):
        assert device_title("Sensor X", "optical") == "Sensor X（optical）"

    def test_device_title_without_scan_type(self):
        assert device_title("Generic Sensor") == "Generic Sensor"

    def test_finger_label_known(self):
        assert finger_label("right-index-finger") == "右手の人差し指"

    def test_finger_label_unknown_falls_back(self):
        assert finger_label("some-future-finger") == "some-future-finger"

    def test_finger_ids_are_unique(self):
        ids = [finger for finger, _ in FINGERS]
        assert len(ids) == len(set(ids))
        assert set(ids) == set(FINGER_LABEL)


class TestAvailableFingers:
    def test_excludes_enrolled_fingers(self):
        candidates = available_fingers(["right-index-finger"])
        ids = [finger for finger, _ in candidates]
        assert "right-index-finger" not in ids
        assert "left-index-finger" in ids
        assert len(candidates) == len(FINGERS) - 1

    def test_all_enrolled(self):
        assert available_fingers([finger for finger, _ in FINGERS]) == []


class TestCommands:
    def test_list_command(self):
        assert build_list_command("alice") == ["fprintd-list", "alice"]

    def test_list_command_uses_current_user(self, monkeypatch):
        monkeypatch.setattr(core, "current_user", lambda: "bob")
        assert build_list_command() == ["fprintd-list", "bob"]

    def test_enroll_command(self):
        assert build_enroll_command("left-thumb", "alice") == [
            "fprintd-enroll",
            "-f",
            "left-thumb",
            "alice",
        ]

    def test_enroll_command_uses_current_user(self, monkeypatch):
        monkeypatch.setattr(core, "current_user", lambda: "bob")
        assert build_enroll_command("left-thumb") == [
            "fprintd-enroll",
            "-f",
            "left-thumb",
            "bob",
        ]

    def test_verify_command(self):
        assert build_verify_command("left-thumb", "alice") == [
            "fprintd-verify",
            "-f",
            "left-thumb",
            "alice",
        ]

    def test_verify_command_uses_current_user(self, monkeypatch):
        monkeypatch.setattr(core, "current_user", lambda: "bob")
        assert build_verify_command("left-thumb") == [
            "fprintd-verify",
            "-f",
            "left-thumb",
            "bob",
        ]

    def test_delete_command(self):
        assert build_delete_command("left-thumb", "alice") == [
            "fprintd-delete",
            "alice",
            "-f",
            "left-thumb",
        ]

    def test_current_user_uses_password_database(self, monkeypatch):
        monkeypatch.setattr(core.pwd, "getpwuid", lambda uid: SimpleNamespace(pw_name="carol"))
        monkeypatch.setattr(core.os, "geteuid", lambda: 1000)
        assert current_user() == "carol"

    def test_current_user_falls_back_to_environment(self, monkeypatch):
        def missing_user(uid):
            raise KeyError(uid)

        monkeypatch.setattr(core.pwd, "getpwuid", missing_user)
        monkeypatch.setenv("USER", "dave")
        assert current_user() == "dave"


class TestClassifyResult:
    def test_authorization_denied(self):
        result = classify_result(["Not Authorized: foo"], 1)
        assert result.kind == "denied"

    def test_enroll_completed(self):
        result = classify_result(["Enroll result: enroll-completed"], 0)
        assert result == Result("enrolled", "登録が完了しました。")

    def test_verify_match(self):
        result = classify_result(["Verify result: verify-match (done)"], 0)
        assert result.kind == "verified"

    def test_verify_no_match_is_not_treated_as_match(self):
        result = classify_result(["Verify result: verify-no-match"], 0)
        assert result.kind == "no-match"

    def test_retry_scan(self):
        result = classify_result(["Verify result: verify-retry-scan"], 0)
        assert result.kind == "retry"

    def test_data_full(self):
        result = classify_result(["Enroll result: enroll-data-full"], 1)
        assert result.kind == "data-full"

    def test_duplicate(self):
        result = classify_result(["Enroll result: enroll-duplicate"], 1)
        assert result.kind == "duplicate"

    def test_disconnected(self):
        result = classify_result(["Verify result: verify-disconnected"], 1)
        assert result.kind == "disconnected"

    def test_device_already_in_use(self):
        result = classify_result(
            ["failed to claim device: net.reactivated.Fprint.Error.AlreadyInUse"], 1
        )
        assert result.kind == "busy"

    def test_enroll_failed(self):
        result = classify_result(["Enroll result: enroll-failed"], 1)
        assert result.kind == "enroll-failed"

    def test_delete_success(self):
        assert classify_result([], 0, "delete") == Result("deleted", "削除しました。")

    def test_generic_success(self):
        assert classify_result([], 0) == Result("ok", "完了しました。")

    def test_failure_includes_returncode(self):
        result = classify_result(["boom"], 2)
        assert result.kind == "error"
        assert "2" in result.message
