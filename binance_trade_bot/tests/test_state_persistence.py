import json
from pathlib import Path

from binance_trade_bot.state_persistence import StatePersistence


def test_save_and_load_state(tmp_path):
    path = tmp_path / "state.json"
    persistence = StatePersistence(path)
    data = {"config": {"a": 1}, "state": {"b": 2}}
    persistence.save(data)
    assert json.loads(path.read_text()) == data
    loaded = persistence.load()
    assert loaded == data
