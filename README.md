# ukids 视频资源下载器

一个用于下载 ukids 平台动画视频资源的 Python 工具，支持获取 m3u8 视频流、ts 片段下载、字幕下载，以及使用 ffmpeg 合并为 MP4 视频。

## 功能特性

- 📱 **短信验证码登录**：支持手机号 + 验证码认证
- 🎬 **两种动画模式**：
  - 全部动画：按语言分类（中文/英文）
  - 分龄动画：按年龄段分类（0-2岁、2-4岁、4-6岁、6-9岁、9岁+）
- 📥 **视频下载**：下载 m3u8 视频的 ts 片段和 srt 字幕
- 🎞️ **视频合并**：使用 ffmpeg 将 ts 片段合并为 MP4，可选嵌入字幕
- 💾 **断点续传**：支持跳过已下载的文件

## 环境要求

### 通用要求
- Python 3.10+
- ffmpeg（仅合并视频时需要）

### macOS / Linux
- 系统自带 Python 或通过包管理器安装
- ffmpeg: `brew install ffmpeg` (macOS) 或 `apt install ffmpeg` (Ubuntu)

### Windows
- Python: 从 [python.org](https://www.python.org/downloads/) 下载安装，**安装时勾选 "Add Python to PATH"**
- ffmpeg: 
  1. 从 [ffmpeg.org](https://ffmpeg.org/download.html) 下载 Windows 版本
  2. 解压到 `C:\ffmpeg`
  3. 将 `C:\ffmpeg\bin` 添加到系统环境变量 PATH

## 安装

### macOS / Linux

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
# 创建虚拟环境
python -m venv venv
.\venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

### Windows (CMD)

```cmd
:: 创建虚拟环境
python -m venv venv
venv\Scripts\activate.bat

:: 安装依赖
pip install -r requirements.txt
```

## 使用方法

### 1. 获取视频元数据

```bash
python main.py
```

按提示操作：
1. 输入手机号并获取验证码
2. 选择动画模式（全部动画/分龄动画）
3. 选择语言类型
4. 选择要处理的动画数量

生成的 JSON 文件保存在 `outputs/all/` 或 `outputs/age/` 目录。

### 2. 下载视频资源

```bash
python download.py
```

按提示选择要下载的 JSON 文件，将下载 ts 片段和字幕到对应目录。

### 3. 合并视频（可选）

```bash
python merge.py
```

需要安装 ffmpeg，将 ts 片段合并为 MP4 视频，可选嵌入字幕。

## 目录结构

```
ukids/
├── main.py          # 主程序，获取动画元数据
├── download.py      # 下载 ts 片段和字幕
├── merge.py         # 合并视频（需要 ffmpeg）
├── api.py           # API 接口封装
├── auth.py          # 认证模块
├── config.py        # 配置文件
├── requirements.txt # 依赖列表
├── docs/            # API 文档
└── outputs/         # 输出目录
    ├── all/         # 全部动画
    ├── age/         # 分龄动画
    └── failed/      # 失败记录
```

### 下载目录结构

```
outputs/all/
├── 动画名_季名_语言.json     # 元数据
└── 动画名_季名_语言/         # 下载目录
    ├── 001_Episode_Title/
    │   ├── ts/               # ts 片段
    │   ├── *_subtitle.srt    # 字幕
    │   └── meta.json         # 剧集信息
    └── mp4/                  # 合并后的视频
```

## 注意事项

- Token 有效期约 5 小时，过期后需重新登录
- 下载大量视频时建议分批处理
- 合并视频会重新编码，需要较长时间

## License

MIT
