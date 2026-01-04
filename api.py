"""
API 调用模块 - 获取动画视频数据
"""

import requests
import base64
from typing import Any
from config import BASE_URL, COMMON_HEADERS, LANG_MAP


class VideoAPI:
    """视频 API 客户端"""
    
    def __init__(self, token: str):
        self.token = token
        self.headers = COMMON_HEADERS.copy()
        self.headers["token"] = token
        # GET 请求使用不同的 Content-Type
        self.headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    
    def get_animation_list(self, filter_lang: int = 2) -> list[dict[str, Any]]:
        """
        获取动画列表
        
        Args:
            filter_lang: 语言过滤，0=中文, 2=英文，默认英文
            
        Returns:
            list: 动画列表
        """
        url = f"{BASE_URL}/coreapp/library/ip/list"
        params = {
            "applyAgeN": 0,
            "level": 0,
            "page.offset": 1,
            "vipType": 1,
            "filterLang": filter_lang,
            "page.limit": 0,
            "vip": 1,
            "subjectType": 0
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers)
            result = response.json()
            
            if result.get("success"):
                data = result.get("data", [])
                print(f"✓ 获取到 {len(data)} 个动画")
                return data
            else:
                error = result.get("error", {})
                print(f"✗ 获取动画列表失败: {error.get('msg', '未知错误')}")
                return []
        except Exception as e:
            print(f"✗ 获取动画列表异常: {e}")
            return []
    
    def get_age_types(self) -> list[dict[str, Any]]:
        """
        获取分龄动画类型数据
        
        Returns:
            list: 分龄类型列表，包含 type 和 name 字段
        """
        url = f"{BASE_URL}/coreapp/library/age/con"
        
        try:
            response = requests.get(url, headers=self.headers)
            result = response.json()
            
            if result.get("success"):
                data = result.get("data", [])
                print(f"✓ 获取到 {len(data)} 个分龄类型")
                return data
            else:
                error = result.get("error", {})
                print(f"✗ 获取分龄类型失败: {error.get('msg', '未知错误')}")
                return []
        except Exception as e:
            print(f"✗ 获取分龄类型异常: {e}")
            return []
    
    def get_age_animation_list(self, age_type: int, filter_lang: int = 0) -> list[dict[str, Any]]:
        """
        获取分龄动画列表
        
        Args:
            age_type: 分龄类型
            filter_lang: 语言过滤，0=中文, 2=英文
            
        Returns:
            list: 动画列表
        """
        url = f"{BASE_URL}/coreapp/library/rcmd/age/ip"
        params = {
            "age": age_type,
            "filterLang": filter_lang
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers)
            result = response.json()
            
            if result.get("success"):
                data = result.get("data", [])
                print(f"✓ 获取到 {len(data)} 个分龄动画")
                return data
            else:
                error = result.get("error", {})
                print(f"✗ 获取分龄动画列表失败: {error.get('msg', '未知错误')}")
                return []
        except Exception as e:
            print(f"✗ 获取分龄动画列表异常: {e}")
            return []
    
    def get_animation_detail(self, ip_id: int, filter_lang: int = 0) -> dict[str, Any] | None:
        """
        获取动画详情
        
        Args:
            ip_id: 动画 IP ID
            filter_lang: 语言过滤
            
        Returns:
            dict: 动画详情数据
        """
        url = f"{BASE_URL}/coreapp/player/video/ipArea"
        params = {
            "ipId": ip_id,
            "filterLang": filter_lang
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers)
            result = response.json()
            
            if result.get("success"):
                return result.get("data")
            else:
                error = result.get("error", {})
                print(f"  ✗ 获取动画详情失败 (ipId={ip_id}): {error.get('msg', '未知错误')}")
                return None
        except Exception as e:
            print(f"  ✗ 获取动画详情异常 (ipId={ip_id}): {e}")
            return None
    
    def get_episodes(self, season_id: int, filter_lang: int = 2) -> list[dict[str, Any]]:
        """
        获取剧集数据
        
        Args:
            season_id: 剧集 ID
            filter_lang: 语言过滤
            
        Returns:
            list: 剧集列表
        """
        url = f"{BASE_URL}/coreapp/video"
        params = {
            "id": season_id,
            "dramaId": 0,
            "limit": 0,
            "offset": 0,
            "vip": 1,
            "filterLang": filter_lang,
            "type": 0
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers)
            result = response.json()
            
            if result.get("success"):
                data = result.get("data", [])
                return data
            else:
                error = result.get("error", {})
                print(f"    ✗ 获取剧集失败 (seasonId={season_id}): {error.get('msg', '未知错误')}")
                return []
        except Exception as e:
            print(f"    ✗ 获取剧集异常 (seasonId={season_id}): {e}")
            return []
    
    def get_play_data(self, en_id: int) -> dict[str, Any] | None:
        """
        获取播放数据
        
        Args:
            en_id: 剧集 enId
            
        Returns:
            dict: 包含 playUrl 和 subtitleUrl 的数据
        """
        url = f"{BASE_URL}/coreapp/play/video/V9/online"
        params = {
            "sType": 0,
            "definition": "HD",
            "id": en_id,
            "type": 1,
            "lang": -1,
            "pure": 1
        }
        
        headers = self.headers.copy()
        headers["xchain"] = "IP_detail"
        headers["udid"] = "338ACD6838381BB372159B79C0C30DB7"
        
        try:
            response = requests.get(url, params=params, headers=headers)
            result = response.json()
            
            if result.get("success"):
                data = result.get("data", {})
                
                # 解码 playUrl (Base64)
                play_url_encoded = data.get("playUrl", "")
                play_url = ""
                if play_url_encoded:
                    try:
                        play_url = base64.b64decode(play_url_encoded).decode("utf-8")
                    except Exception as e:
                        print(f"      ✗ Base64 解码 playUrl 失败: {e}")
                        play_url = play_url_encoded
                
                # subtitleUrl 不需要解码
                subtitle_url = data.get("subtitleUrl", "")
                
                return {
                    "playUrl": play_url,
                    "subtitleUrl": subtitle_url
                }
            else:
                error = result.get("error", {})
                print(f"      ✗ 获取播放数据失败 (enId={en_id}): {error.get('msg', '未知错误')}")
                return None
        except Exception as e:
            print(f"      ✗ 获取播放数据异常 (enId={en_id}): {e}")
            return None


def get_lang_name(lang: int) -> str:
    """获取语言名称"""
    return LANG_MAP.get(lang, f"lang{lang}")


if __name__ == "__main__":
    # 测试 API
    from auth import load_token
    
    token = load_token()
    if not token:
        print("请先运行 auth.py 进行认证")
        exit(1)
    
    api = VideoAPI(token)
    
    # 测试获取动画列表
    animations = api.get_animation_list(filter_lang=2)
    if animations:
        print(f"\n前3个动画:")
        for anim in animations[:3]:
            print(f"  - {anim.get('name')} (ipId={anim.get('ipId')}, lang={anim.get('lang')})")
