"""API tests never read or overwrite the developer's saved robot configuration."""
import pytest


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("MISSION_DB_PATH", str(tmp_path / "missions.sqlite3"))
    monkeypatch.setenv("ROBOT_CONFIG_PATH", str(tmp_path / "robot-config.json"))
