"""
TS 视频合并工具 - 将下载的 ts 片段合并为 MP4 视频
使用 ffmpeg 进行合并，可选嵌入字幕
"""

import json
import os
import subprocess
from pathlib import Path


def check_ffmpeg() -> bool:
    """检查 ffmpeg 是否可用"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True)
        return result.returncode == 0
    except Exception:
        return False


def get_episode_dirs(base_dir: str) -> list[str]:
    """
    获取所有剧集目录（包含 ts 子目录的目录）
    
    Args:
        base_dir: 基础目录
        
    Returns:
        list: 剧集目录路径列表
    """
    episode_dirs = []
    
    if not os.path.exists(base_dir):
        return []
    
    for item in sorted(os.listdir(base_dir)):
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path):
            ts_dir = os.path.join(item_path, "ts")
            if os.path.isdir(ts_dir):
                episode_dirs.append(item_path)
    
    return episode_dirs


def get_ts_files(ts_dir: str) -> list[str]:
    """获取 ts 目录下所有 ts 文件，按顺序排列"""
    if not os.path.exists(ts_dir):
        return []
    
    ts_files = []
    for f in sorted(os.listdir(ts_dir)):
        if f.endswith('.ts'):
            ts_files.append(os.path.join(ts_dir, f))
    
    return ts_files


def merge_ts_to_mp4(episode_dir: str, output_dir: str, embed_subtitle: bool = True) -> bool:
    """
    合并单个剧集的 ts 文件为 MP4
    
    Args:
        episode_dir: 剧集目录
        output_dir: 输出 MP4 目录
        embed_subtitle: 是否嵌入字幕
        
    Returns:
        bool: 是否成功
    """
    episode_name = os.path.basename(episode_dir)
    ts_dir = os.path.join(episode_dir, "ts")
    subtitle_path = os.path.join(episode_dir, f"{episode_name}_subtitle.srt")
    output_path = os.path.join(output_dir, f"{episode_name}.mp4")
    
    # 检查是否已存在
    if os.path.exists(output_path):
        print(f"  ⏭ 已存在，跳过: {episode_name}.mp4")
        return True
    
    # 获取 ts 文件
    ts_files = get_ts_files(ts_dir)
    if not ts_files:
        print(f"  ✗ 没有找到 ts 文件: {episode_name}")
        return False
    
    print(f"  ▶ 合并: {episode_name} ({len(ts_files)} 个片段)")
    
    try:
        # 步骤1：将所有 ts 文件二进制拼接
        combined_ts = os.path.join(episode_dir, "combined.ts")
        print(f"    拼接 ts 文件...")
        
        with open(combined_ts, 'wb') as outfile:
            for ts_file in ts_files:
                with open(ts_file, 'rb') as infile:
                    outfile.write(infile.read())
        
        # 检查是否有字幕
        has_subtitle = embed_subtitle and os.path.exists(subtitle_path)
        
        if has_subtitle:
            # 步骤2：编码视频
            temp_video = os.path.join(episode_dir, "temp_video.mp4")
            print(f"    编码视频...")
            
            cmd1 = [
                'ffmpeg', '-y',
                '-i', combined_ts,
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '18',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-movflags', '+faststart',
                temp_video
            ]
            
            result1 = subprocess.run(cmd1, capture_output=True, text=True)
            if result1.returncode != 0:
                print(f"    ✗ 编码失败: {result1.stderr[:200]}")
                return False
            
            # 步骤3：嵌入字幕
            print(f"    嵌入字幕...")
            
            cmd2 = [
                'ffmpeg', '-y',
                '-i', temp_video,
                '-i', subtitle_path,
                '-c:v', 'copy',
                '-c:a', 'copy',
                '-c:s', 'mov_text',
                '-metadata:s:s:0', 'language=eng',
                '-disposition:s:0', 'default',
                output_path
            ]
            
            result2 = subprocess.run(cmd2, capture_output=True, text=True)
            
            # 清理临时文件
            if os.path.exists(temp_video):
                os.remove(temp_video)
            
            if result2.returncode != 0:
                print(f"    ✗ 嵌入字幕失败: {result2.stderr[:200]}")
                return False
        else:
            # 无字幕：直接编码输出
            print(f"    编码视频...")
            
            cmd = [
                'ffmpeg', '-y',
                '-i', combined_ts,
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '18',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-movflags', '+faststart',
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"    ✗ 编码失败: {result.stderr[:200]}")
                return False
        
        # 清理合并的 ts
        if os.path.exists(combined_ts):
            os.remove(combined_ts)
        
        file_size = os.path.getsize(output_path) / (1024 * 1024)
        print(f"    ✓ 完成: {episode_name}.mp4 ({file_size:.1f} MB)")
        return True
        
    except Exception as e:
        print(f"    ✗ 合并失败: {e}")
        return False


def process_season_dir(season_dir: str, embed_subtitle: bool = True) -> tuple[int, int]:
    """
    处理一个季目录下的所有剧集
    
    Args:
        season_dir: 季目录路径
        embed_subtitle: 是否嵌入字幕
        
    Returns:
        tuple: (成功数, 失败数)
    """
    season_name = os.path.basename(season_dir)
    
    # MP4 输出到同级目录，根据是否嵌入字幕区分
    if embed_subtitle:
        mp4_dir = os.path.join(season_dir, "mp4")
    else:
        mp4_dir = os.path.join(season_dir, "mp4_nosub")
    os.makedirs(mp4_dir, exist_ok=True)
    
    print(f"\n处理: {season_name}")
    subtitle_status = "嵌入字幕" if embed_subtitle else "不嵌入字幕"
    print(f"  输出目录: {mp4_dir} ({subtitle_status})")
    
    episode_dirs = get_episode_dirs(season_dir)
    if not episode_dirs:
        print(f"  ✗ 没有找到剧集目录")
        return 0, 0
    
    print(f"  发现 {len(episode_dirs)} 个剧集")
    
    success = 0
    fail = 0
    
    for episode_dir in episode_dirs:
        if merge_ts_to_mp4(episode_dir, mp4_dir, embed_subtitle):
            success += 1
        else:
            fail += 1
    
    return success, fail


def get_season_dirs(downloads_dir: str) -> list[str]:
    """获取下载目录下所有季目录"""
    if not os.path.exists(downloads_dir):
        return []
    
    season_dirs = []
    for item in sorted(os.listdir(downloads_dir)):
        item_path = os.path.join(downloads_dir, item)
        if os.path.isdir(item_path):
            # 检查是否包含剧集目录
            for sub_item in os.listdir(item_path):
                sub_path = os.path.join(item_path, sub_item)
                if os.path.isdir(sub_path) and os.path.isdir(os.path.join(sub_path, "ts")):
                    season_dirs.append(item_path)
                    break
    
    return season_dirs


def main():
    """主函数"""
    print("=" * 50)
    print("  TS 视频合并工具")
    print("=" * 50)
    
    # 检查 ffmpeg
    if not check_ffmpeg():
        print("✗ 需要安装 ffmpeg")
        return
    
    print("✓ ffmpeg 已就绪")
    
    # 选择下载目录
    print("\n选择要合并的下载目录:")
    print("  1. 全部动画 (outputs/all/ 目录)")
    print("  2. 分龄动画 (outputs/age/ 目录)")
    print("  3. 全部")
    
    mode_choice = input("请输入选项 (1/2/3, 默认 1): ").strip() or "1"
    
    downloads_dirs = []
    if mode_choice == "1":
        downloads_dirs = ["outputs/all"]
    elif mode_choice == "2":
        downloads_dirs = ["outputs/age"]
    else:
        downloads_dirs = ["outputs/all", "outputs/age"]
    
    # 是否嵌入字幕
    subtitle_choice = input("\n是否嵌入字幕? (y/n, 默认 y): ").strip().lower() or "y"
    embed_subtitle = subtitle_choice == 'y'
    
    total_success = 0
    total_fail = 0
    
    for downloads_dir in downloads_dirs:
        season_dirs = get_season_dirs(downloads_dir)
        
        if not season_dirs:
            print(f"\n✗ {downloads_dir}/ 目录不存在或没有下载的视频")
            continue
        
        print(f"\n{'=' * 50}")
        print(f"  下载目录: {downloads_dir}/")
        print("=" * 50)
        
        print(f"\n找到 {len(season_dirs)} 个季目录:")
        for i, d in enumerate(season_dirs, 1):
            print(f"  {i}. {os.path.basename(d)}")
        
        print("\n选择要合并的目录:")
        print("  输入数字选择单个 (如: 1)")
        print("  输入 'all' 合并全部")
        print("  输入 'skip' 跳过")
        choice = input("请输入选择: ").strip().lower()
        
        if choice == 'skip':
            continue
        
        if choice == 'all':
            selected_dirs = season_dirs
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(season_dirs):
                    selected_dirs = [season_dirs[idx]]
                else:
                    print("✗ 无效选择，跳过")
                    continue
            except ValueError:
                print("✗ 无效输入，跳过")
                continue
        
        for season_dir in selected_dirs:
            success, fail = process_season_dir(season_dir, embed_subtitle)
            total_success += success
            total_fail += fail
    
    print("\n" + "=" * 50)
    print(f"  合并完成!")
    print(f"  成功: {total_success} 个视频")
    print(f"  失败: {total_fail} 个视频")
    print("=" * 50)


if __name__ == "__main__":
    main()
