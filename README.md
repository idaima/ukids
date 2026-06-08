# ukids 视频资源下载器

一个用于下载 ukids 平台动画视频资源的本地工具，支持短信验证码登录、动画元数据采集、m3u8/ts 片段下载、字幕下载，以及使用 ffmpeg 合并为 MP4。

项目同时提供：

- **Web GUI**：推荐使用，浏览器内完成登录、采集、下载、合并和任务管理。
- **命令行脚本**：保留原有 `main.py` / `download.py` / `merge.py` 流程。

## 功能特性

- 📱 **登录认证**
  - 手机号 + 短信验证码登录
  - 支持手动粘贴 Token
  - 支持退出登录
- 🖥️ **本地 Web GUI**
  - 独立登录页 + MD3 风格控制台主页
  - 左侧导航切换：概览 / 资源 / 下载 / 合并 / 任务
  - 异常提示、Toast、确认弹窗、操作 loading 状态
- 🎬 **资源采集**
  - 全部动画：按语言分类
  - 分龄动画：按年龄段分类
  - 动画列表分页显示，默认每页 30 条
  - 支持搜索、跨页选择、批量采集
- 📥 **视频下载**
  - 扫描 `outputs/all` 或 `outputs/age` 下的 JSON
  - JSON 列表分页显示，默认每页 30 条
  - 支持跨页选择、选本页、清除已选
  - 并发下载 m3u8 的 ts 片段和字幕
- 🎞️ **视频合并**
  - 检查 ffmpeg 可用性
  - 扫描已下载季目录
  - 支持嵌入字幕 / 不嵌入字幕输出
- ⚙️ **任务管理**
  - 后台执行采集、下载、合并任务
  - 实时查看进度和日志
  - 支持取消任务、清空日志
  - 支持删除单个任务、清空所有任务
  - 任务状态持久化到 `outputs/.gui/tasks.json`
- 💾 **断点续传**
  - 已下载片段会跳过
  - 已合并 MP4 会跳过

## 环境要求

- Python 3.10+
- ffmpeg（仅合并视频时需要）

### macOS / Linux

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg
```

### Windows

1. 从 [python.org](https://www.python.org/downloads/) 安装 Python，并勾选 **Add Python to PATH**。
2. 从 [ffmpeg.org](https://ffmpeg.org/download.html) 下载 Windows 版本。
3. 解压到 `C:\ffmpeg`。
4. 将 `C:\ffmpeg\bin` 添加到系统环境变量 PATH。

## 安装

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Windows CMD

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

## 推荐使用：Web GUI

### 启动

```bash
source .venv/bin/activate  # Windows 使用对应 activate 命令
python gui_server.py
```

然后访问：

```text
http://127.0.0.1:8000
```

> GUI 服务默认只监听 `127.0.0.1:8000`，适合作为本机工具使用。

### GUI 操作流程

1. **登录**
   - 使用手机号发送短信验证码登录；或
   - 手动粘贴已有 Token。

2. **资源采集**
   - 进入左侧导航 `资源`。
   - 选择模式：`全部动画` / `分龄动画`。
   - 选择语言和年龄段。
   - 点击 `加载` 获取动画列表。
   - 动画列表默认每页 30 条，可搜索、翻页、跨页选择。
   - 点击 `采集`，生成 JSON 到：
     - `outputs/all/`
     - `outputs/age/`

3. **下载资源**
   - 进入左侧导航 `下载`。
   - 选择来源：
     - `全部动画`：对应 `outputs/all`
     - `分龄动画`：对应 `outputs/age`
   - 点击 `刷新` 扫描 JSON。
   - JSON 列表默认每页 30 条，可翻页、选本页、清除已选。
   - 点击 `下载` 下载 ts 片段和字幕。

4. **合并 MP4**
   - 进入左侧导航 `合并`。
   - 点击 `重新检测` 检查 ffmpeg。
   - 选择目录来源和是否嵌入字幕。
   - 点击 `刷新` 扫描可合并目录。
   - 选择目录后点击 `合并`。

5. **任务管理**
   - 进入左侧导航 `任务`。
   - 查看当前任务进度、统计和日志。
   - 支持：
     - 取消任务
     - 清空日志
     - 删除指定任务
     - 清空所有任务

## 命令行使用方法

### 1. 获取视频元数据

```bash
python main.py
```

按提示操作：

1. 输入手机号并获取验证码。
2. 选择动画模式：全部动画 / 分龄动画。
3. 选择语言类型。
4. 选择要处理的动画。

生成的 JSON 文件保存在 `outputs/all/` 或 `outputs/age/` 目录。

### 2. 下载视频资源

```bash
python download.py
```

按提示选择要下载的 JSON 文件，将下载 ts 片段和字幕到对应目录。

### 3. 合并视频

```bash
python merge.py
```

需要安装 ffmpeg。可选择是否嵌入字幕。

## 目录结构

```text
ukids/
├── gui_server.py             # Web GUI 后端入口
├── gui_services/             # GUI 服务层
│   ├── task_manager.py       # 任务管理和持久化
│   ├── metadata_service.py   # 元数据采集服务
│   └── file_service.py       # 文件扫描和路径校验
├── web/                      # Web GUI 前端
│   ├── index.html
│   ├── app.js
│   └── style.css
├── main.py                   # CLI：获取动画元数据
├── download.py               # CLI/服务复用：下载 ts 和字幕
├── merge.py                  # CLI/服务复用：合并 MP4
├── api.py                    # API 接口封装
├── auth.py                   # 认证模块
├── config.py                 # 配置文件
├── docs/                     # API 文档
├── requirements.txt          # Python 依赖
└── outputs/                  # 输出目录
    ├── all/                  # 全部动画 JSON 和下载目录
    ├── age/                  # 分龄动画 JSON 和下载目录
    ├── failed/               # 失败记录
    └── .gui/                 # GUI 任务持久化数据
```

## 输出目录说明

### 元数据 JSON

```text
outputs/all/动画名_季名_语言.json
outputs/age/动画名_季名_语言_年龄段.json
```

### 下载目录

```text
outputs/all/
├── 动画名_季名_语言.json
└── 动画名_季名_语言/
    ├── 001_Episode_Title/
    │   ├── ts/
    │   │   ├── 001_Episode_Title_00000.ts
    │   │   └── 001_Episode_Title_00001.ts
    │   ├── 001_Episode_Title_subtitle.srt
    │   ├── meta.json
    │   └── .download_complete
    ├── mp4/                  # 嵌入字幕 MP4
    └── mp4_nosub/            # 不嵌入字幕 MP4
```

### GUI 任务持久化

```text
outputs/.gui/tasks.json
```

服务重启后会恢复历史任务记录。如果重启前任务仍在运行，会标记为已中断/取消。

## 常见问题

### Token 过期怎么办？

Token 有效期约 5 小时。过期后在 GUI 登录页重新登录即可。

### ffmpeg 显示不可用怎么办？

请确认 ffmpeg 已安装，并且 `ffmpeg` 命令已加入 PATH：

```bash
ffmpeg -version
```

### 下载大量视频很慢怎么办？

下载大量视频建议分批选择 JSON 或动画。下载脚本已支持并发和跳过已完成文件。

### GUI 数据会不会提交到 git？

不会。`outputs/`、`token.txt`、`.venv/` 等运行数据已在 `.gitignore` 中忽略。

## 注意事项

- 请仅下载你有权限访问的内容。
- 下载大量视频会占用较多磁盘空间。
- 合并视频需要重新编码，耗时较长且占用 CPU。
- GUI 后端默认限制在本地访问，不建议直接暴露到公网。

## License

MIT
