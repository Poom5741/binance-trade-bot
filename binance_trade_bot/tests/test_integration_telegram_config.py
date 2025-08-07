import types
import sys
import asyncio

# Provide a lightweight stub for optional third-party dependencies so the
# configuration commands can be imported without the real packages installed.
sys.modules.setdefault("apprise", types.ModuleType("apprise"))

# Stub sqlalchemy for environments where it's not available
sa = types.ModuleType("sqlalchemy")
ext = types.ModuleType("sqlalchemy.ext")
declarative = types.ModuleType("sqlalchemy.ext.declarative")

def declarative_base():
    class Base:  # minimal stand-in
        pass
    return Base

declarative.declarative_base = declarative_base
ext.declarative = declarative
sa.ext = ext
sys.modules.setdefault("sqlalchemy", sa)
sys.modules.setdefault("sqlalchemy.ext", ext)
sys.modules.setdefault("sqlalchemy.ext.declarative", declarative)

from binance_trade_bot.telegram.configuration_commands import ConfigurationCommands


class DummyDB:
    def db_session(self):
        from contextlib import contextmanager
        @contextmanager
        def _cm():
            yield None
        return _cm()


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


def test_update_backup_interval_runtime():
    config = {"backup_interval": 10}

    class TestCommands(ConfigurationCommands):
        def send_message(self, *a, **k):
            pass

        def send_trade_notification(self, *a, **k):
            pass

        def send_alert(self, *a, **k):
            pass

        def start_bot(self):
            pass

        def stop_bot(self):
            pass

    cmds = TestCommands(config, DummyDB(), DummyLogger())
    user = types.SimpleNamespace(first_name="Tester", username="tester")
    result = asyncio.run(cmds._update_backup_interval(20, user))
    assert result["status"] == "success"
    assert config["backup_interval"] == 20
