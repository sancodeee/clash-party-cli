from pathlib import Path

import pytest
import yaml


@pytest.fixture
def clash_party_data_dir(tmp_path: Path) -> Path:
    """Create a minimal valid Clash Party data directory."""
    data_dir = tmp_path / "mihomo-party"
    data_dir.mkdir()

    documents = {
        "config.yaml": {"app": {"language": "en"}},
        "mihomo.yaml": {"mixed-port": 7890, "mode": "rule"},
        "profile.yaml": {"current": "default", "items": []},
    }
    for name, content in documents.items():
        (data_dir / name).write_text(
            yaml.safe_dump(content, sort_keys=False),
            encoding="utf-8",
        )

    for name in ("profiles", "override", "rules", "work", "logs"):
        (data_dir / name).mkdir()

    return data_dir
