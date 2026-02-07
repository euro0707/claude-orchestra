"""Test 5.3: path_utils module - Windows/Git Bash path normalization."""
import pytest
from pathlib import Path

import path_utils


class TestNormalizePath:
    def test_msys2_c_drive(self):
        assert path_utils.normalize_path("/c/Users/skyeu") == "C:\\Users\\skyeu"

    def test_msys2_d_drive(self):
        assert path_utils.normalize_path("/d/projects") == "D:\\projects"

    def test_msys2_uppercase_drive(self):
        assert path_utils.normalize_path("/C/Users/skyeu") == "C:\\Users\\skyeu"

    def test_windows_path_unchanged(self):
        assert path_utils.normalize_path("C:\\Users\\skyeu") == "C:\\Users\\skyeu"

    def test_empty_string(self):
        assert path_utils.normalize_path("") == ""

    def test_none_like_empty(self):
        # normalize_path checks `if not path_str`
        assert path_utils.normalize_path("") == ""

    def test_drive_root_only(self):
        assert path_utils.normalize_path("/c") == "C:"

    def test_unix_absolute_non_drive(self):
        # /usr/bin should not match (not a single letter drive)
        assert path_utils.normalize_path("/usr/bin") == "/usr/bin"

    def test_relative_path_unchanged(self):
        assert path_utils.normalize_path("src/main.py") == "src/main.py"

    def test_forward_slashes_in_msys(self):
        result = path_utils.normalize_path("/c/Users/skyeu/project/src")
        assert "\\" in result
        assert "/" not in result


class TestToWindowsPath:
    def test_msys2_path_to_windows(self):
        result = path_utils.to_windows_path("/c/Users/skyeu")
        assert isinstance(result, Path)

    def test_path_object_passthrough(self):
        p = Path("C:/Users/skyeu")
        result = path_utils.to_windows_path(p)
        assert isinstance(result, Path)

    def test_string_normalized(self):
        result = path_utils.to_windows_path("/d/projects/foo")
        assert str(result).startswith("D:")


class TestToPosixString:
    def test_windows_path_to_posix(self):
        result = path_utils.to_posix_string("C:\\Users\\skyeu")
        assert "\\" not in result
        assert "/" in result

    def test_already_posix(self):
        result = path_utils.to_posix_string("C:/Users/skyeu")
        assert "/" in result
