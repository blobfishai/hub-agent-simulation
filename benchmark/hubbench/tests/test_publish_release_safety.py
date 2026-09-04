"""Release CLI rejects unsafe targets before creating files or starting jobs."""

import os
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "publish_release.sh"


def test_publisher_shell_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


@pytest.mark.parametrize(("version", "override", "message"), [
    ("../../somewhere", {}, "version must be N.N.N"),
    ("1.4.0", {"HUBBENCH_FROZEN_RELEASE": "/unexpected/snapshot"}, "original or qualified cache directory"),
    ("1.4.0", {"HUBBENCH_GATE_JOB": "../old-job"}, "simple directory names"),
    ("1.4.0", {"HUBBENCH_ROUNDTRIP_JOB": "../old-job"}, "simple directory names"),
    ("1.4.0", {"HUBBENCH_GATE_CONCURRENCY": "0"}, "at least 1"),
    ("1.4.0", {"HUBBENCH_ROUNDTRIP_CONCURRENCY": "0"}, "positive integer"),
])
def test_invalid_publish_parameters_fail_before_any_action(version: str, override: dict, message: str):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("HUBBENCH_")}
    result = subprocess.run(
        ["bash", str(SCRIPT), version, "--from-step", "3", "--to-step", "3"],
        env={**environment, **override}, capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert message in result.stderr
    assert "HubBench publish" not in result.stdout
