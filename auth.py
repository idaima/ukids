"""
认证模块 - 短信验证码登录获取 Token
"""

import requests
import os
from config import BASE_URL, COMMON_HEADERS, TOKEN_FILE


def send_sms_code(mobile: str) -> bool:
    """
    发送短信验证码
    
    Args:
        mobile: 手机号码
        
    Returns:
        bool: 是否发送成功
    """
    url = f"{BASE_URL}/ucapp/sms"
    headers = COMMON_HEADERS.copy()
    headers["token"] = ""
    
    payload = {
        "mobile": mobile,
        "type": "1"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        result = response.json()
        
        if result.get("success"):
            print(f"✓ 验证码已发送到 {mobile}")
            return True
        else:
            error = result.get("error", {})
            print(f"✗ 发送验证码失败: {error.get('msg', '未知错误')}")
            return False
    except Exception as e:
        print(f"✗ 发送验证码异常: {e}")
        return False


def login_with_sms(mobile: str, verify_code: str) -> str | None:
    """
    使用短信验证码登录
    
    Args:
        mobile: 手机号码
        verify_code: 短信验证码
        
    Returns:
        str | None: 成功返回 token，失败返回 None
    """
    url = f"{BASE_URL}/ucapp/mobileLogin"
    headers = COMMON_HEADERS.copy()
    headers["token"] = ""
    headers["xchain"] = "13"
    
    payload = {
        "verifyCode": verify_code,
        "mobile": mobile
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        result = response.json()
        
        if result.get("success"):
            token_data = result.get("data", {}).get("token", {})
            token = token_data.get("token")
            
            if token:
                user = result.get("data", {}).get("user", {})
                print(f"✓ 登录成功! 欢迎 {user.get('nickname', '用户')}")
                print(f"  VIP状态: {'是' if user.get('vipReal',0) == 1 else '否'}")
                print(f"  VIP到期: {user.get('vipEndReal', '无')}")
                return token
            else:
                print("✗ 登录成功但未获取到 token")
                return None
        else:
            error = result.get("error", {})
            print(f"✗ 登录失败: {error.get('msg', '未知错误')}")
            return None
    except Exception as e:
        print(f"✗ 登录异常: {e}")
        return None


def save_token(token: str) -> None:
    """保存 token 到本地文件"""
    with open(TOKEN_FILE, "w") as f:
        f.write(token)
    print(f"✓ Token 已保存到 {TOKEN_FILE}")


def load_token() -> str | None:
    """从本地文件加载 token"""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            token = f.read().strip()
            if token:
                return token
    return None


def authenticate() -> str | None:
    """
    完整的认证流程
    
    Returns:
        str | None: 成功返回 token，失败返回 None
    """
    # 尝试加载已保存的 token
    existing_token = load_token()
    if existing_token:
        use_existing = input(f"发现已保存的 Token，是否使用? (y/n): ").strip().lower() or "y"
        if use_existing == 'y' and existing_token != "" :
            print("✓ 使用已保存的 Token")
            return existing_token
    
    # 输入手机号
    mobile = input("请输入手机号码: ").strip()
    if not mobile:
        print("✗ 手机号码不能为空")
        return None
    
    # 发送验证码
    if not send_sms_code(mobile):
        return None
    
    # 输入验证码
    verify_code = input("请输入短信验证码: ").strip()
    if not verify_code:
        print("✗ 验证码不能为空")
        return None
    
    # 登录
    token = login_with_sms(mobile, verify_code)
    
    if token:
        save_token(token)
    
    return token


if __name__ == "__main__":
    # 测试认证流程
    token = authenticate()
    if token:
        print(f"\n获取到的 Token: {token[:50]}...")
    else:
        print("\n认证失败")
