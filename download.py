"""
M3U8 视频下载器 - 下载 m3u8 视频的 ts 片段和字幕文件
不进行合并操作，合并操作由 merge_ts.py 单独处理
"""

import json
import os
import re
import requests
from typing import Any
from urllib.parse import urljoin


def ensure_dir(path: str):
    """确保目录存在"""
    if not os.path.exists(path):
        os.makedirs(path)


def download_file(url: str, filepath: str, show_error: bool = True) -> bool:
    """
    下载文件到指定路径
    
    Args:
        url: 文件 URL
        filepath: 保存路径
        show_error: 是否显示错误信息
        
    Returns:
        bool: 是否成功
    """
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        if show_error:
            print(f"      ✗ 下载失败: {e}")
        return False


def parse_m3u8(m3u8_url: str) -> list[str]:
    """
    解析 m3u8 文件获取所有 ts 片段 URL
    
    Args:
        m3u8_url: m3u8 文件 URL
        
    Returns:
        list: ts 片段 URL 列表
    """
    try:
        response = requests.get(m3u8_url, timeout=30)
        response.raise_for_status()
        content = response.text
        
        ts_urls = []
        base_url = m3u8_url.rsplit('/', 1)[0] + '/'
        
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                if line.startswith('http'):
                    ts_urls.append(line)
                else:
                    ts_urls.append(urljoin(base_url, line))
        
        return ts_urls
    except Exception as e:
        print(f"    ✗ 解析 m3u8 失败: {e}")
        return []


def download_ts_segments(ts_urls: list[str], ts_dir: str, name_prefix: str = "segment") -> int:
    """
    下载所有 ts 片段到指定目录
    
    Args:
        ts_urls: ts 片段 URL 列表
        ts_dir: ts 文件保存目录
        name_prefix: ts 文件名前缀
        
    Returns:
        int: 成功下载的数量
    """
    ensure_dir(ts_dir)
    success_count = 0
    total = len(ts_urls)
    
    for i, url in enumerate(ts_urls):
        ts_path = os.path.join(ts_dir, f"{name_prefix}_{i:05d}.ts")
        
        # 检查是否已存在
        if os.path.exists(ts_path):
            success_count += 1
            continue
        
        if download_file(url, ts_path, show_error=False):
            success_count += 1
        
        # 进度显示
        if (i + 1) % 20 == 0 or i + 1 == total:
            print(f"      下载进度: {i + 1}/{total} (成功: {success_count})")
    
    return success_count


def download_subtitle(subtitle_url: str, save_path: str) -> bool:
    """下载字幕文件"""
    if not subtitle_url:
        return False
    return download_file(subtitle_url, save_path)


def sanitize_filename(name: str) -> str:
    """清理文件名中的特殊字符"""
    return re.sub(r'[\\/*?:"<>|]', '_', name)


def process_episode(episode: dict[str, Any], episode_dir: str, index: int) -> bool:
    """
    处理单个剧集：下载 ts 片段和字幕
    
    Args:
        episode: 剧集数据
        episode_dir: 剧集保存目录
        index: 剧集索引
        
    Returns:
        bool: 是否成功
    """
    play_url = episode.get("playUrl", "")
    subtitle_url = episode.get("subtitleUrl", "")
    title = episode.get("enTitle", f"Episode_{index}")
    sortby = episode.get("sortby", index)
    
    # 创建剧集目录
    safe_title = sanitize_filename(title)
    episode_name = f"{sortby:03d}_{safe_title}"
    episode_path = os.path.join(episode_dir, episode_name)
    
    # ts 片段目录
    ts_dir = os.path.join(episode_path, "ts")
    
    # 检查标记文件，判断是否已完成下载
    done_marker = os.path.join(episode_path, ".download_complete")
    if os.path.exists(done_marker):
        print(f"    ⏭ 已完成，跳过: {episode_name}")
        return True
    
    if not play_url:
        print(f"    ✗ 缺少播放地址: {title}")
        return False
    
    print(f"    ▶ 下载: {title}")
    
    ensure_dir(episode_path)
    
    # 解析 m3u8
    ts_urls = parse_m3u8(play_url)
    if not ts_urls:
        return False
    
    print(f"      发现 {len(ts_urls)} 个片段")
    
    # 下载 ts 片段
    success_count = download_ts_segments(ts_urls, ts_dir, name_prefix=episode_name)
    
    if success_count == 0:
        print(f"      ✗ 下载 ts 片段失败")
        return False
    
    if success_count < len(ts_urls):
        print(f"      ⚠ 部分片段下载失败: {success_count}/{len(ts_urls)}")
    
    # 下载字幕
    if subtitle_url:
        subtitle_path = os.path.join(episode_path, f"{episode_name}_subtitle.srt")
        if download_subtitle(subtitle_url, subtitle_path):
            print(f"      ✓ 字幕已下载")
        else:
            print(f"      ⚠ 字幕下载失败")
    
    # 保存元数据
    meta_path = os.path.join(episode_path, "meta.json")
    meta_data = {
        "title": title,
        "sortby": sortby,
        "play_url": play_url,
        "subtitle_url": subtitle_url,
        "ts_count": len(ts_urls),
        "ts_downloaded": success_count
    }
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta_data, f, ensure_ascii=False, indent=2)
    
    # 如果全部下载成功，创建完成标记
    if success_count == len(ts_urls):
        with open(done_marker, 'w') as f:
            f.write("done")
        print(f"      ✓ 下载完成: {episode_name}")
    
    return True


def process_json_file(json_path: str, downloads_base_dir: str) -> tuple[int, int]:
    """
    处理单个 JSON 文件，下载所有视频
    
    Args:
        json_path: JSON 文件路径
        downloads_base_dir: 下载目录基础路径
        
    Returns:
        tuple: (成功数, 失败数)
    """
    json_name = os.path.splitext(os.path.basename(json_path))[0]
    output_dir = os.path.join(downloads_base_dir, json_name)
    ensure_dir(output_dir)
    
    print(f"\n处理: {json_name}")
    print(f"  输出目录: {output_dir}")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            episodes = json.load(f)
    except Exception as e:
        print(f"  ✗ 读取 JSON 失败: {e}")
        return 0, 0
    
    print(f"  共 {len(episodes)} 集")
    
    success = 0
    fail = 0
    
    for i, episode in enumerate(episodes):
        if process_episode(episode, output_dir, i + 1):
            success += 1
        else:
            fail += 1
    
    return success, fail


def get_json_files(source_dir: str) -> list[str]:
    """获取目录下所有 JSON 文件"""
    if not os.path.exists(source_dir):
        return []
    return sorted([f for f in os.listdir(source_dir) if f.endswith('.json')])


def main():
    """主函数"""
    print("=" * 50)
    print("  M3U8 视频下载器 (仅下载 ts 和字幕)")
    print("=" * 50)
    print("提示: 下载完成后使用 merge_ts.py 进行合并")
    
    # 选择来源模式
    print("\n选择 JSON 文件来源:")
    print("  1. 全部动画 (output/ 目录)")
    print("  2. 分龄动画 (output_age/ 目录)")
    print("  3. 全部 (两个目录)")
    
    mode_choice = input("请输入选项 (1/2/3, 默认 1): ").strip() or "1"
    
    sources = []
    if mode_choice == "1":
        sources = [("outputs/all", "outputs/all")]
    elif mode_choice == "2":
        sources = [("outputs/age", "outputs/age")]
    else:
        sources = [("outputs/all", "outputs/all"), ("outputs/age", "outputs/age")]
    
    total_success = 0
    total_fail = 0
    
    for source_dir, downloads_dir in sources:
        json_files = get_json_files(source_dir)
        
        if not json_files:
            print(f"\n✗ {source_dir}/ 目录不存在或没有 JSON 文件")
            continue
        
        print(f"\n{'=' * 50}")
        print(f"  来源目录: {source_dir}/")
        print(f"  下载目录: {downloads_dir}/")
        print("=" * 50)
        
        print(f"\n找到 {len(json_files)} 个 JSON 文件:")
        for i, f in enumerate(json_files, 1):
            print(f"  {i}. {f}")
        
        print("\n选择要下载的文件:")
        print("  输入数字选择单个文件 (如: 1)")
        print("  输入 'all' 下载全部")
        print("  输入 'skip' 跳过此目录")
        choice = input("请输入选择: ").strip().lower()
        
        if choice == 'skip':
            print("跳过此目录")
            continue
        
        if choice == 'all':
            selected_files = json_files
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(json_files):
                    selected_files = [json_files[idx]]
                else:
                    print("✗ 无效选择，跳过")
                    continue
            except ValueError:
                print("✗ 无效输入，跳过")
                continue
        
        ensure_dir(downloads_dir)
        
        for json_file in selected_files:
            json_path = os.path.join(source_dir, json_file)
            success, fail = process_json_file(json_path, downloads_dir)
            total_success += success
            total_fail += fail
    
    print("\n" + "=" * 50)
    print(f"  下载完成!")
    print(f"  成功: {total_success} 个视频")
    print(f"  失败: {total_fail} 个视频")
    print("\n  提示: 使用 python merge_ts.py 合并视频")
    print("=" * 50)


if __name__ == "__main__":
    main()
