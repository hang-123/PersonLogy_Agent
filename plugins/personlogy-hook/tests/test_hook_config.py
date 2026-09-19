from __future__ import annotations

import json
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PLUGIN_ROOT.parents[1]


def _windows_commands(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        hook["commandWindows"]
        for groups in payload["hooks"].values()
        for group in groups
        for hook in group["hooks"]
        if "commandWindows" in hook
    ]


def test_project_and_plugin_windows_hooks_use_runtime_selector() -> None:
    wrapper = PLUGIN_ROOT / "scripts" / "run_windows.ps1"
    assert wrapper.is_file()

    configs = [
        REPOSITORY_ROOT / ".codex" / "hooks.json",
        PLUGIN_ROOT / "hooks" / "hooks.json",
    ]
    for config in configs:
        commands = _windows_commands(config)
        assert commands
        assert all("run_windows.ps1" in command for command in commands)
        assert all("py -3" not in command for command in commands)
