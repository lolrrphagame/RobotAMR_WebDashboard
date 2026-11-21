"""API tests never read or overwrite the developer's saved robot configuration."""
import pytest


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_MODE','local')
    monkeypatch.setenv('ALLOWED_HOSTS','localhost,127.0.0.1,testserver')
    monkeypatch.setenv('ALLOWED_ORIGINS','http://127.0.0.1:5173,http://localhost:5173')
    monkeypatch.delenv('OPERATOR_PASSWORD_HASH',raising=False)
    monkeypatch.delenv('ACCOUNT_STORE_PATH',raising=False)
    monkeypatch.setenv("MISSION_DB_PATH", str(tmp_path / "missions.sqlite3"))
    monkeypatch.setenv("ROBOT_CONFIG_PATH", str(tmp_path / "robot-config.json"))
