"""
配置文件 - 通用请求头和 API 配置
"""

# API 基础 URL
BASE_URL = "https://fastapi.ukids.cn"

# 通用请求头
COMMON_HEADERS = {
    "Cache-Control": "public, max-age=3600",
    "Content-Type": "application/json; charset=UTF-8",
    "format": "JSON",
    "channel": "anp6",
    "ver": "5.0.3",
    "verCode": "503",
    "xfrom": "1",
    "hos": "Android16",
    "mode": "parents",
    "Host": "fastapi.ukids.cn",
    "User-Agent": "okhttp/3.12.8"
}

# 语言类型映射
LANG_MAP = {
    0: "中文",
    1: "全部",
    2: "英文"
}

# Token 文件路径
TOKEN_FILE = "token.txt"
