"""
M3U8 视频下载器 - 下载 m3u8 视频的 ts 片段和字幕文件
不进行合并操作，合并操作由 merge_ts.py 单独处理
支持多线程并发下载
"""

import json
import os
import re
import shutil
import sys
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urljoin


# 并发下载配置 - 根据 CPU 核心数动态计算
# I/O 密集型任务可使用较多线程，这里使用 CPU 核心数的 2 倍
# 最小 4 个线程，最大 16 个线程
_cpu_count = os.cpu_count() or 4
MAX_WORKERS = min(max(_cpu_count * 2, 4), 16)


class DownloadStats:
    """线程安全的下载统计类"""
    def __init__(self, total: int):
        self.total = total
        self.completed = 0
        self.success = 0
        self.skipped = 0
        self.failed = 0
        self.total_size = 0
        self.start_time = time.time()
        self._lock = threading.Lock()
    
    def add_success(self, size: int, skipped: bool = False):
        """添加成功下载"""
        with self._lock:
            self.completed += 1
            self.success += 1
            self.total_size += size
            if skipped:
                self.skipped += 1
    
    def add_failure(self):
        """添加下载失败"""
        with self._lock:
            self.completed += 1
            self.failed += 1
    
    def get_stats(self) -> dict:
        """获取当前统计数据"""
        with self._lock:
            elapsed = time.time() - self.start_time
            speed = self.total_size / elapsed if elapsed > 0 else 0
            return {
                'completed': self.completed,
                'total': self.total,
                'success': self.success,
                'skipped': self.skipped,
                'failed': self.failed,
                'total_size': self.total_size,
                'speed': speed
            }


def get_terminal_width() -> int:
    """获取终端宽度"""
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return 80


def ensure_dir(path: str):
    """确保目录存在"""
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def create_progress_bar(current: int, total: int, width: int = 30, 
                       prefix: str = "", suffix: str = "") -> str:
    """
    创建进度条字符串
    
    Args:
        current: 当前进度
        total: 总数
        width: 进度条宽度
        prefix: 前缀文字
        suffix: 后缀文字
    """
    if total == 0:
        percent = 100
    else:
        percent = (current / total) * 100
    
    filled = int(width * current / total) if total > 0 else width
    bar = "█" * filled + "░" * (width - filled)
    
    return f"{prefix}[{bar}] {current}/{total} ({percent:.1f}%){suffix}"


def print_progress(current: int, total: int, prefix: str = "", 
                  extra_info: str = "", newline: bool = False):
    """
    打印进度信息（覆盖当前行）
    
    Args:
        current: 当前进度
        total: 总数
        prefix: 前缀
        extra_info: 额外信息
        newline: 是否换行
    """
    bar = create_progress_bar(current, total, width=25, prefix=prefix)
    if extra_info:
        bar += f" {extra_info}"
    
    # 清除当前行并打印
    terminal_width = get_terminal_width()
    bar = bar[:terminal_width - 1]  # 确保不超过终端宽度
    
    if newline:
        print(f"\r{bar:<{terminal_width}}")
    else:
        print(f"\r{bar:<{terminal_width}}", end="", flush=True)


def download_file(url: str, filepath: str, show_error: bool = True) -> tuple[bool, int]:
    """
    下载文件到指定路径
    
    Args:
        url: 文件 URL
        filepath: 保存路径
        show_error: 是否显示错误信息
        
    Returns:
        tuple: (是否成功, 文件大小)
    """
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        size = 0
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                size += len(chunk)
        return True, size
    except Exception as e:
        if show_error:
            print(f"\n      ✗ 下载失败: {e}")
        return False, 0


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
        print(f"\n    ✗ 解析 m3u8 失败: {e}")
        return []


def download_single_ts(args: tuple) -> tuple[int, bool, int]:
    """
    下载单个 ts 片段（供线程池调用）
    
    Args:
        args: (index, url, ts_path) 元组
        
    Returns:
        tuple: (索引, 是否成功, 文件大小)
    """
    index, url, ts_path = args
    
    # 检查是否已存在
    if os.path.exists(ts_path):
        size = os.path.getsize(ts_path)
        return (index, True, size, True)  # True 表示是跳过的
    
    # 下载文件
    success, size = download_file(url, ts_path, show_error=False)
    return (index, success, size, False)


def download_ts_segments(ts_urls: list[str], ts_dir: str, name_prefix: str = "segment",
                         progress_cb=None, cancel_cb=None) -> tuple[int, int, int]:
    """
    并发下载所有 ts 片段到指定目录
    
    Args:
        ts_urls: ts 片段 URL 列表
        ts_dir: ts 文件保存目录
        name_prefix: ts 文件名前缀
        
    Returns:
        tuple: (成功下载数量, 跳过数量, 总下载大小)
    """
    ensure_dir(ts_dir)
    total = len(ts_urls)
    
    if total == 0:
        return 0, 0, 0
    
    # 创建下载统计
    stats = DownloadStats(total)
    
    # 准备下载任务
    tasks = []
    for i, url in enumerate(ts_urls):
        ts_path = os.path.join(ts_dir, f"{name_prefix}_{i:05d}.ts")
        tasks.append((i, url, ts_path))
    
    # 进度显示函数
    def show_progress():
        s = stats.get_stats()
        speed_str = f"{format_size(int(s['speed']))}/s" if s['speed'] > 0 else "计算中..."
        extra = f"成功: {s['success']} | 跳过: {s['skipped']} | 大小: {format_size(s['total_size'])} | 速度: {speed_str}"
        print_progress(s['completed'], s['total'], prefix="      ", extra_info=extra)
        if progress_cb:
            progress_cb({
                "stage": "segments",
                "completed": s["completed"],
                "total": s["total"],
                "success": s["success"],
                "skipped": s["skipped"],
                "failed": s["failed"],
                "total_size": s["total_size"],
                "speed": s["speed"],
                "message": extra,
            })
    
    # 使用线程池并发下载
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        futures = {executor.submit(download_single_ts, task): task for task in tasks}
        
        # 处理完成的任务
        for future in as_completed(futures):
            if cancel_cb and cancel_cb():
                for pending in futures:
                    pending.cancel()
                break
            try:
                index, success, size, skipped = future.result()
                if success:
                    stats.add_success(size, skipped=skipped)
                else:
                    stats.add_failure()
            except Exception:
                stats.add_failure()
            
            # 更新进度显示
            show_progress()
    
    # 完成后换行
    print()
    
    s = stats.get_stats()
    return s['success'], s['skipped'], s['total_size']


def download_subtitle(subtitle_url: str, save_path: str) -> bool:
    """下载字幕文件"""
    if not subtitle_url:
        return False
    success, _ = download_file(subtitle_url, save_path, show_error=False)
    return success


def sanitize_filename(name: str) -> str:
    """清理文件名中的特殊字符"""
    return re.sub(r'[\\/*?:"<>|]', '_', name)


def process_episode(episode: dict[str, Any], episode_dir: str, index: int,
                   episode_num: int, total_episodes: int,
                   progress_cb=None, cancel_cb=None) -> tuple[bool, int]:
    """
    处理单个剧集：下载 ts 片段和字幕
    
    Args:
        episode: 剧集数据
        episode_dir: 剧集保存目录
        index: 剧集索引
        episode_num: 当前剧集编号（用于显示）
        total_episodes: 总剧集数
        
    Returns:
        tuple: (是否成功, 下载大小)
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
        print(f"  [{episode_num}/{total_episodes}] ⏭ 已完成，跳过: {title}")
        if progress_cb:
            progress_cb({
                "stage": "episode_skipped",
                "episode": title,
                "episode_num": episode_num,
                "total_episodes": total_episodes,
                "message": f"已完成，跳过: {title}",
            })
        return True, 0
    
    if not play_url:
        print(f"  [{episode_num}/{total_episodes}] ✗ 缺少播放地址: {title}")
        if progress_cb:
            progress_cb({
                "stage": "episode_failed",
                "episode": title,
                "episode_num": episode_num,
                "total_episodes": total_episodes,
                "message": f"缺少播放地址: {title}",
            })
        return False, 0
    
    print(f"\n  [{episode_num}/{total_episodes}] ▶ {title}")
    if progress_cb:
        progress_cb({
            "stage": "episode_start",
            "episode": title,
            "episode_num": episode_num,
            "total_episodes": total_episodes,
            "message": f"开始下载: {title}",
        })
    if cancel_cb and cancel_cb():
        return False, 0
    
    ensure_dir(episode_path)
    
    # 解析 m3u8
    ts_urls = parse_m3u8(play_url)
    if not ts_urls:
        return False, 0
    
    print(f"    📦 共 {len(ts_urls)} 个片段")
    
    # 下载 ts 片段
    success_count, skipped_count, total_size = download_ts_segments(
        ts_urls, ts_dir, name_prefix=episode_name,
        progress_cb=progress_cb, cancel_cb=cancel_cb
    )
    
    if success_count == 0:
        print(f"    ✗ 下载 ts 片段失败")
        return False, 0
    
    # 显示下载统计
    new_downloads = success_count - skipped_count
    print(f"    📊 统计: 成功 {success_count}/{len(ts_urls)} | "
          f"新下载 {new_downloads} | 跳过 {skipped_count} | "
          f"大小 {format_size(total_size)}")
    
    if success_count < len(ts_urls):
        failed = len(ts_urls) - success_count
        print(f"    ⚠ {failed} 个片段下载失败")
    
    # 下载字幕
    if subtitle_url:
        subtitle_path = os.path.join(episode_path, f"{episode_name}_subtitle.srt")
        if download_subtitle(subtitle_url, subtitle_path):
            print(f"    📝 字幕已下载")
        else:
            print(f"    ⚠ 字幕下载失败")
    
    # 保存元数据
    meta_path = os.path.join(episode_path, "meta.json")
    meta_data = {
        "title": title,
        "sortby": sortby,
        "play_url": play_url,
        "subtitle_url": subtitle_url,
        "ts_count": len(ts_urls),
        "ts_downloaded": success_count,
        "total_size": total_size
    }
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta_data, f, ensure_ascii=False, indent=2)
    
    # 如果全部下载成功，创建完成标记
    if success_count == len(ts_urls):
        with open(done_marker, 'w') as f:
            f.write("done")
        print(f"    ✓ 下载完成")
    if progress_cb:
        progress_cb({
            "stage": "episode_done",
            "episode": title,
            "episode_num": episode_num,
            "total_episodes": total_episodes,
            "success_count": success_count,
            "ts_count": len(ts_urls),
            "total_size": total_size,
            "message": f"下载完成: {title}",
        })
    
    return True, total_size


def process_json_file(json_path: str, downloads_base_dir: str, 
                     file_num: int = 1, total_files: int = 1,
                     progress_cb=None, cancel_cb=None) -> tuple[int, int, int]:
    """
    处理单个 JSON 文件，下载所有视频
    
    Args:
        json_path: JSON 文件路径
        downloads_base_dir: 下载目录基础路径
        file_num: 当前文件编号
        total_files: 总文件数
        
    Returns:
        tuple: (成功数, 失败数, 总下载大小)
    """
    json_name = os.path.splitext(os.path.basename(json_path))[0]
    output_dir = os.path.join(downloads_base_dir, json_name)
    ensure_dir(output_dir)
    
    print(f"\n{'=' * 60}")
    print(f"📁 [{file_num}/{total_files}] {json_name}")
    print(f"   输出目录: {output_dir}")
    print("=" * 60)
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            episodes = json.load(f)
    except Exception as e:
        print(f"  ✗ 读取 JSON 失败: {e}")
        return 0, 0, 0
    
    total_episodes = len(episodes)
    print(f"  📺 共 {total_episodes} 集待处理")
    if progress_cb:
        progress_cb({
            "stage": "json_start",
            "json_name": json_name,
            "file_num": file_num,
            "total_files": total_files,
            "total_episodes": total_episodes,
            "message": f"开始处理 JSON: {json_name}",
        })
    
    success = 0
    fail = 0
    total_size = 0
    
    for i, episode in enumerate(episodes):
        if cancel_cb and cancel_cb():
            print("\n  ⚠ 已请求取消，停止处理后续剧集")
            break
        ep_success, ep_size = process_episode(
            episode, output_dir, i + 1, 
            episode_num=i + 1, total_episodes=total_episodes,
            progress_cb=progress_cb, cancel_cb=cancel_cb
        )
        if ep_success:
            success += 1
        else:
            fail += 1
        total_size += ep_size
        if progress_cb:
            progress_cb({
                "stage": "json_progress",
                "json_name": json_name,
                "done": i + 1,
                "total": total_episodes,
                "success": success,
                "failed": fail,
                "total_size": total_size,
                "message": f"{json_name}: 已处理 {i + 1}/{total_episodes}",
            })
    
    # 文件处理完成统计
    print(f"\n  {'─' * 50}")
    print(f"  📊 {json_name} 下载统计:")
    print(f"     ✓ 成功: {success} 集")
    if fail > 0:
        print(f"     ✗ 失败: {fail} 集")
    print(f"     💾 总大小: {format_size(total_size)}")
    
    return success, fail, total_size


def get_json_files(source_dir: str) -> list[str]:
    """获取目录下所有 JSON 文件"""
    if not os.path.exists(source_dir):
        return []
    return sorted([f for f in os.listdir(source_dir) if f.endswith('.json')])


def main():
    """主函数"""
    print("=" * 60)
    print("  📥 M3U8 视频下载器 (仅下载 ts 和字幕)")
    print("=" * 60)
    print(f"  🚀 并发线程数: {MAX_WORKERS} (CPU核心数: {_cpu_count})")
    print("  💡 提示: 下载完成后使用 merge_ts.py 进行合并")
    
    # 选择来源模式
    print("\n选择 JSON 文件来源:")
    print("  1. 全部动画 (outputs/all 目录)")
    print("  2. 分龄动画 (outputs/age 目录)")
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
    total_size = 0
    start_time = time.time()
    
    for source_dir, downloads_dir in sources:
        json_files = get_json_files(source_dir)
        
        if not json_files:
            print(f"\n✗ {source_dir}/ 目录不存在或没有 JSON 文件")
            continue
        
        print(f"\n{'=' * 60}")
        print(f"  📂 来源目录: {source_dir}/")
        print(f"  💾 下载目录: {downloads_dir}/")
        print("=" * 60)
        
        print(f"\n找到 {len(json_files)} 个 JSON 文件:")
        for i, f in enumerate(json_files, 1):
            print(f"  {i}. {f}")
        
        print("\n选择要下载的文件:")
        print("  输入数字选择单个文件 (如: 1)")
        print("  输入多个数字用空格分隔 (如: 1 3 5)")
        print("  输入 'all' 下载全部")
        print("  输入 'skip' 跳过此目录")
        choice = input("请输入选择: ").strip().lower()
        
        if choice == 'skip':
            print("跳过此目录")
            continue
        
        if choice == 'all':
            selected_files = json_files
        else:
            # 支持多选
            selected_files = []
            parts = choice.split()
            for part in parts:
                try:
                    idx = int(part) - 1
                    if 0 <= idx < len(json_files):
                        if json_files[idx] not in selected_files:
                            selected_files.append(json_files[idx])
                    else:
                        print(f"  ⚠ 序号 {part} 超出范围，已忽略")
                except ValueError:
                    print(f"  ⚠ 无效输入 '{part}'，已忽略")
            
            if not selected_files:
                print("✗ 没有选择有效文件，跳过")
                continue
        
        ensure_dir(downloads_dir)
        
        print(f"\n📋 将下载 {len(selected_files)} 个文件")
        
        for file_idx, json_file in enumerate(selected_files, 1):
            json_path = os.path.join(source_dir, json_file)
            success, fail, size = process_json_file(
                json_path, downloads_dir, 
                file_num=file_idx, total_files=len(selected_files)
            )
            total_success += success
            total_fail += fail
            total_size += size
    
    # 计算总用时
    elapsed = time.time() - start_time
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    seconds = int(elapsed % 60)
    
    if hours > 0:
        time_str = f"{hours}小时 {minutes}分 {seconds}秒"
    elif minutes > 0:
        time_str = f"{minutes}分 {seconds}秒"
    else:
        time_str = f"{seconds}秒"
    
    # 最终统计
    print("\n" + "=" * 60)
    print("  🎉 下载任务完成!")
    print("=" * 60)
    print(f"  ✓ 成功: {total_success} 个视频")
    if total_fail > 0:
        print(f"  ✗ 失败: {total_fail} 个视频")
    print(f"  💾 总大小: {format_size(total_size)}")
    print(f"  ⏱ 总用时: {time_str}")
    print("\n  💡 提示: 使用 python merge_ts.py 合并视频")
    print("=" * 60)


if __name__ == "__main__":
    main()
