"""
视频资源下载器 - 主程序
获取 ukids 平台动画视频的 m3u8 下载地址并保存到本地 JSON 文件
支持两种模式：全部动画 和 分龄动画
"""

import json
import os
import time
from datetime import datetime
from typing import Any

from auth import authenticate
from api import VideoAPI, get_lang_name
from config import LANG_MAP


# 输出目录
OUTPUT_DIR_ALL = "outputs/all"    # 全部动画输出目录
OUTPUT_DIR_AGE = "outputs/age"    # 分龄动画输出目录
FAILED_DIR = "outputs/failed"     # 失败记录目录


def ensure_dir(path: str):
    """确保目录存在"""
    if not os.path.exists(path):
        os.makedirs(path)


def sanitize_filename(name: str) -> str:
    """清理文件名中的特殊字符"""
    for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|', ' ']:
        name = name.replace(char, '_')
    return name.strip('_')


def save_to_json(data: list[dict[str, Any]], output_dir: str, animation_name: str, 
                 season_name: str, lang: int, age_name: str = None):
    """
    保存数据到 JSON 文件
    
    Args:
        data: 剧集数据列表
        output_dir: 输出目录
        animation_name: 动画名称
        season_name: 季名称
        lang: 语言类型
        age_name: 年龄范围（分龄动画时使用）
    """
    ensure_dir(output_dir)
    
    lang_name = get_lang_name(lang)
    safe_name = sanitize_filename(animation_name)
    safe_season = sanitize_filename(season_name)
    
    if age_name:
        safe_age = sanitize_filename(age_name)
        filename = f"{safe_name}_{safe_season}_{lang_name}_{safe_age}.json"
    else:
        filename = f"{safe_name}_{safe_season}_{lang_name}.json"
    
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"    ✓ 已保存到 {filepath} ({len(data)} 集)")


def save_failed_record(failed_list: list[dict], mode: str):
    """
    保存失败记录
    
    Args:
        failed_list: 失败的动画列表
        mode: 模式 ('all' 或 'age')
    """
    if not failed_list:
        return
    
    ensure_dir(FAILED_DIR)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"failed_{mode}_{timestamp}.json"
    filepath = os.path.join(FAILED_DIR, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(failed_list, f, ensure_ascii=False, indent=2)
    
    print(f"\n⚠ 失败记录已保存到: {filepath}")


def process_animation(api: VideoAPI, animation: dict[str, Any], output_dir: str, 
                      age_name: str = None) -> tuple[bool, dict | None]:
    """
    处理单个动画，获取所有剧集的播放数据
    
    Args:
        api: VideoAPI 实例
        animation: 动画信息
        output_dir: 输出目录
        age_name: 年龄范围名称（分龄动画时使用）
        
    Returns:
        tuple: (是否成功, 失败信息)
    """
    ip_id = animation.get("ipId")
    name = animation.get("name", "未知动画")
    lang = animation.get("lang", 2)
    
    print(f"\n处理动画: {name} (ipId={ip_id}, lang={get_lang_name(lang)})")
    
    # 获取动画详情
    detail = api.get_animation_detail(ip_id, filter_lang=lang)
    if not detail:
        return False, {"ipId": ip_id, "name": name, "error": "获取动画详情失败"}
    
    seasons = detail.get("seasons", [])
    if not seasons:
        print(f"  ✗ 没有找到剧集季")
        return False, {"ipId": ip_id, "name": name, "error": "没有剧集季"}
    
    print(f"  发现 {len(seasons)} 个季")
    
    success_seasons = 0
    failed_episodes = []
    
    for season in seasons:
        season_id = season.get("id")
        season_name = season.get("name", "未知季")
        season_lang = season.get("lang", lang)
        
        print(f"  处理: {season_name.strip()} (id={season_id})")
        
        # 获取剧集列表
        episodes = api.get_episodes(season_id, filter_lang=season_lang)
        if not episodes:
            continue
        
        print(f"    发现 {len(episodes)} 集")
        
        season_episodes = []
        
        for i, episode in enumerate(episodes):
            en_id = episode.get("enId")
            en_title = episode.get("enTitle", f"第{i+1}集")
            
            # 获取播放数据
            play_data = api.get_play_data(en_id)
            
            if play_data:
                episode["playUrl"] = play_data.get("playUrl", "")
                episode["subtitleUrl"] = play_data.get("subtitleUrl", "")
            else:
                episode["playUrl"] = ""
                episode["subtitleUrl"] = ""
                failed_episodes.append({
                    "enId": en_id, 
                    "title": en_title,
                    "season": season_name
                })
            
            season_episodes.append(episode)
            
            if (i + 1) % 10 == 0:
                print(f"      已处理 {i + 1}/{len(episodes)} 集...")
            
            time.sleep(0.1)
        
        if season_episodes:
            save_to_json(season_episodes, output_dir, name, season_name, season_lang, age_name)
            success_seasons += 1
    
    if success_seasons > 0:
        print(f"  ✓ 成功保存 {success_seasons} 个季")
        if failed_episodes:
            return True, {"ipId": ip_id, "name": name, "partial": True, "failed_episodes": failed_episodes}
        return True, None
    else:
        print(f"  ✗ 没有获取到任何剧集数据")
        return False, {"ipId": ip_id, "name": name, "error": "没有获取到剧集数据"}


def run_all_animations_mode(api: VideoAPI):
    """全部动画模式"""
    print("\n" + "=" * 50)
    print("  [模式] 获取全部动画")
    print("=" * 50)
    
    # 选择语言
    print("\n选择要获取的语言类型:")
    print("  1. 英文 (lang=2)")
    print("  2. 中文 (lang=0)")
    print("  3. 全部")
    
    choice = input("请输入选项 (1/2/3, 默认 1): ").strip() or "1"
    
    if choice == "1":
        lang_filters = [2]
    elif choice == "2":
        lang_filters = [0]
    else:
        lang_filters = [0, 2]
    
    # 选择处理数量
    limit_input = input("请输入要处理的动画数量 (输入 0 表示全部, 默认 3): ").strip() or "3"
    try:
        limit = int(limit_input)
    except ValueError:
        limit = 3
    
    success_count = 0
    fail_count = 0
    failed_list = []
    
    for filter_lang in lang_filters:
        print(f"\n{'=' * 50}")
        print(f"  获取 {get_lang_name(filter_lang)} 动画列表")
        print("=" * 50)
        
        animations = api.get_animation_list(filter_lang=filter_lang)
        if not animations:
            print("没有获取到动画列表")
            continue
        
        if limit > 0:
            animations = animations[:limit]
        
        print(f"\n将处理 {len(animations)} 个动画\n")
        
        for i, animation in enumerate(animations):
            print(f"\n[{i+1}/{len(animations)}]", end="")
            success, failed_info = process_animation(api, animation, OUTPUT_DIR_ALL)
            if success:
                success_count += 1
            else:
                fail_count += 1
            if failed_info:
                failed_list.append(failed_info)
            
            time.sleep(0.5)
    
    # 保存失败记录
    save_failed_record(failed_list, "all")
    
    print("\n" + "=" * 50)
    print(f"  处理完成!")
    print(f"  成功: {success_count} 个动画")
    print(f"  失败: {fail_count} 个动画")
    print(f"  输出目录: {os.path.abspath(OUTPUT_DIR_ALL)}")
    print("=" * 50)


def run_age_animations_mode(api: VideoAPI):
    """分龄动画模式"""
    print("\n" + "=" * 50)
    print("  [模式] 获取分龄动画")
    print("=" * 50)
    
    # 获取分龄类型
    age_types = api.get_age_types()
    if not age_types:
        print("获取分龄类型失败")
        return
    
    # 显示分龄类型选项
    print("\n可选的分龄类型:")
    age_map = {}
    for age in age_types:
        age_type = age.get("type")
        age_name = age.get("name")
        age_map[age_type] = age_name
        print(f"  {age_type}. {age_name}")
    
    # 用户选择分龄类型
    type_input = input("\n请输入分龄类型编号: ").strip()
    try:
        selected_type = int(type_input)
        if selected_type not in age_map:
            print("✗ 无效的分龄类型")
            return
    except ValueError:
        print("✗ 请输入有效的数字")
        return
    
    selected_age_name = age_map[selected_type]
    print(f"\n已选择: {selected_age_name}")
    
    # 选择语言
    print("\n选择要获取的语言类型:")
    print("  1. 英文 (lang=2)")
    print("  2. 中文 (lang=0)")
    print("  3. 全部")
    
    choice = input("请输入选项 (1/2/3, 默认 1): ").strip() or "1"
    
    if choice == "1":
        lang_filters = [2]
    elif choice == "2":
        lang_filters = [0]
    else:
        lang_filters = [0, 2]
    
    # 选择处理数量
    limit_input = input("请输入要处理的动画数量 (输入 0 表示全部, 默认 3): ").strip() or "3"
    try:
        limit = int(limit_input)
    except ValueError:
        limit = 3
    
    success_count = 0
    fail_count = 0
    failed_list = []
    
    for filter_lang in lang_filters:
        print(f"\n{'=' * 50}")
        print(f"  获取 {selected_age_name} - {get_lang_name(filter_lang)} 动画列表")
        print("=" * 50)
        
        animations = api.get_age_animation_list(selected_type, filter_lang=filter_lang)
        if not animations:
            print("没有获取到分龄动画列表")
            continue
        
        if limit > 0:
            animations = animations[:limit]
        
        print(f"\n将处理 {len(animations)} 个动画\n")
        
        for i, animation in enumerate(animations):
            print(f"\n[{i+1}/{len(animations)}]", end="")
            success, failed_info = process_animation(
                api, animation, OUTPUT_DIR_AGE, age_name=selected_age_name
            )
            if success:
                success_count += 1
            else:
                fail_count += 1
            if failed_info:
                failed_info["age_type"] = selected_age_name
                failed_list.append(failed_info)
            
            time.sleep(0.5)
    
    # 保存失败记录
    save_failed_record(failed_list, "age")
    
    print("\n" + "=" * 50)
    print(f"  处理完成!")
    print(f"  分龄类型: {selected_age_name}")
    print(f"  成功: {success_count} 个动画")
    print(f"  失败: {fail_count} 个动画")
    print(f"  输出目录: {os.path.abspath(OUTPUT_DIR_AGE)}")
    print("=" * 50)


def main():
    """主函数"""
    print("=" * 50)
    print("  ukids 视频资源下载器")
    print("=" * 50)
    
    # 认证获取 token
    token = authenticate()
    if not token:
        print("\n认证失败，程序退出")
        return
    
    print("\n" + "-" * 50)
    
    # 创建 API 客户端
    api = VideoAPI(token)
    
    # 选择模式
    print("\n选择获取动画的模式:")
    print("  1. 全部动画 (按语言分类)")
    print("  2. 分龄动画 (按年龄段分类)")
    
    mode_choice = input("请输入选项 (1/2, 默认 1): ").strip() or "1"
    
    if mode_choice == "2":
        run_age_animations_mode(api)
    else:
        run_all_animations_mode(api)


if __name__ == "__main__":
    main()
