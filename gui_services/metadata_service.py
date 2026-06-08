"""GUI 元数据采集服务。"""

from __future__ import annotations

import time
from typing import Any, Callable

from api import VideoAPI, get_lang_name
from main import OUTPUT_DIR_AGE, OUTPUT_DIR_ALL, save_failed_record, save_to_json

ProgressCallback = Callable[..., None]
CancelCallback = Callable[[], bool]


def collect_metadata(
    token: str,
    animations: list[dict[str, Any]],
    mode: str = "all",
    age_name: str | None = None,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
) -> dict[str, Any]:
    """采集选中动画的剧集播放元数据并保存 JSON。"""
    api = VideoAPI(token)
    output_dir = OUTPUT_DIR_AGE if mode == "age" else OUTPUT_DIR_ALL
    total = len(animations)
    success_count = 0
    fail_count = 0
    failed_list: list[dict[str, Any]] = []

    if progress_cb:
        progress_cb(total=total, done=0, success=0, failed=0, progress=0.0, message="开始采集元数据")

    for index, animation in enumerate(animations, 1):
        if cancel_cb and cancel_cb():
            if progress_cb:
                progress_cb(status="cancelled", message="元数据采集已取消")
            break

        name = animation.get("name", "未知动画")
        if progress_cb:
            progress_cb(
                current=name,
                done=index - 1,
                total=total,
                progress=round(((index - 1) / total) * 100, 2) if total else 0,
                message=f"正在处理动画 {index}/{total}: {name}",
                log=f"开始处理: {name}",
            )

        ok, failed_info = collect_one_animation(api, animation, output_dir, age_name, progress_cb, cancel_cb)
        if ok:
            success_count += 1
        else:
            fail_count += 1
        if failed_info:
            if age_name:
                failed_info["age_type"] = age_name
            failed_list.append(failed_info)

        if progress_cb:
            progress_cb(
                done=index,
                total=total,
                success=success_count,
                failed=fail_count,
                progress=round((index / total) * 100, 2) if total else 100,
                message=f"已完成 {index}/{total}",
            )
        time.sleep(0.2)

    save_failed_record(failed_list, mode)
    return {
        "mode": mode,
        "age_name": age_name,
        "output_dir": output_dir,
        "success": success_count,
        "failed": fail_count,
        "failed_items": failed_list,
    }


def collect_one_animation(
    api: VideoAPI,
    animation: dict[str, Any],
    output_dir: str,
    age_name: str | None = None,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    ip_id = animation.get("ipId")
    name = animation.get("name", "未知动画")
    lang = animation.get("lang", 2)

    if progress_cb:
        progress_cb(current=name, message=f"获取动画详情: {name}")

    detail = api.get_animation_detail(ip_id, filter_lang=lang)
    if not detail:
        return False, {"ipId": ip_id, "name": name, "error": "获取动画详情失败"}

    seasons = detail.get("seasons", [])
    if not seasons:
        return False, {"ipId": ip_id, "name": name, "error": "没有剧集季"}

    success_seasons = 0
    failed_episodes: list[dict[str, Any]] = []

    for season_index, season in enumerate(seasons, 1):
        if cancel_cb and cancel_cb():
            return False, {"ipId": ip_id, "name": name, "error": "cancelled"}

        season_id = season.get("id")
        season_name = season.get("name", "未知季")
        season_lang = season.get("lang", lang)

        if progress_cb:
            progress_cb(
                current=f"{name} / {season_name}",
                message=f"获取剧集列表: {season_name} ({season_index}/{len(seasons)})",
                log=f"{name}: 处理季 {season_name} lang={get_lang_name(season_lang)}",
            )

        episodes = api.get_episodes(season_id, filter_lang=season_lang)
        if not episodes:
            continue

        season_episodes: list[dict[str, Any]] = []
        for episode_index, episode in enumerate(episodes, 1):
            if cancel_cb and cancel_cb():
                return False, {"ipId": ip_id, "name": name, "error": "cancelled"}

            en_id = episode.get("enId")
            en_title = episode.get("enTitle", f"第{episode_index}集")
            if progress_cb:
                progress_cb(
                    current=f"{name} / {season_name} / {en_title}",
                    message=f"获取播放数据 {episode_index}/{len(episodes)}",
                )

            play_data = api.get_play_data(en_id)
            if play_data:
                episode["playUrl"] = play_data.get("playUrl", "")
                episode["subtitleUrl"] = play_data.get("subtitleUrl", "")
            else:
                episode["playUrl"] = ""
                episode["subtitleUrl"] = ""
                failed_episodes.append({"enId": en_id, "title": en_title, "season": season_name})

            season_episodes.append(episode)
            time.sleep(0.1)

        if season_episodes:
            save_to_json(season_episodes, output_dir, name, season_name, season_lang, age_name)
            success_seasons += 1
            if progress_cb:
                progress_cb(log=f"已保存: {name} / {season_name} ({len(season_episodes)} 集)")

    if success_seasons > 0:
        if failed_episodes:
            return True, {"ipId": ip_id, "name": name, "partial": True, "failed_episodes": failed_episodes}
        return True, None
    return False, {"ipId": ip_id, "name": name, "error": "没有获取到剧集数据"}
