"""GUI 文件扫描与安全路径工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from merge import get_episode_dirs, get_season_dirs

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = (PROJECT_ROOT / "outputs").resolve()
ALL_DIR = (OUTPUT_ROOT / "all").resolve()
AGE_DIR = (OUTPUT_ROOT / "age").resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def to_project_relative(path: str | Path) -> str:
    p = Path(path).resolve()
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


def safe_output_path(path: str | Path, must_exist: bool = True) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    resolved = p.resolve()
    if not _is_relative_to(resolved, OUTPUT_ROOT):
        raise ValueError(f"非法路径，不在 outputs 目录下: {path}")
    if must_exist and not resolved.exists():
        raise FileNotFoundError(str(path))
    return resolved


def source_dirs(source: str = "both") -> list[tuple[str, Path]]:
    if source == "all":
        return [("all", ALL_DIR)]
    if source == "age":
        return [("age", AGE_DIR)]
    return [("all", ALL_DIR), ("age", AGE_DIR)]


def count_json_episodes(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


def scan_json_files(source: str = "both") -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source_name, directory in source_dirs(source):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            items.append(
                {
                    "name": path.name,
                    "path": to_project_relative(path),
                    "source": source_name,
                    "episodes": count_json_episodes(path),
                    "size": path.stat().st_size,
                    "modified": path.stat().st_mtime,
                }
            )
    return items


def scan_season_dirs(source: str = "both") -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source_name, directory in source_dirs(source):
        if not directory.exists():
            continue
        for season_dir_str in get_season_dirs(str(directory)):
            season_dir = Path(season_dir_str).resolve()
            episode_dirs = get_episode_dirs(str(season_dir))
            mp4_dir = season_dir / "mp4"
            mp4_nosub_dir = season_dir / "mp4_nosub"
            mp4_count = len(list(mp4_dir.glob("*.mp4"))) if mp4_dir.exists() else 0
            mp4_nosub_count = len(list(mp4_nosub_dir.glob("*.mp4"))) if mp4_nosub_dir.exists() else 0
            items.append(
                {
                    "name": season_dir.name,
                    "path": to_project_relative(season_dir),
                    "source": source_name,
                    "episodes": len(episode_dirs),
                    "mp4_count": mp4_count,
                    "mp4_nosub_count": mp4_nosub_count,
                }
            )
    return items
