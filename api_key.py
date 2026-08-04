from flask import request, abort, jsonify
import hmac
import hashlib
import time
import json

from key_manager import (
    load_all,
    record_usage,
    check_device_binding,
    unbind_device,
    get_valid_keys,
    get_keys_data,
    get_hmac_secret,
)
# 每次请求前刷新（几乎零开销）
load_all()

# ---------- 工具函数 ----------
def is_public_request():
    # 公网域名
    if request.host.endswith(".top"):
        return True
    # Nginx 明确告诉我是 https
    if request.headers.get("X-Forwarded-Proto") == "https":
        return True
    return False

def _get_device_fingerprint():
    """统一获取客户端传来的设备指纹"""
    # 优先从 header 取（公网 Bearer 方式）
    fp = request.headers.get("device_fingerprint")
    if fp:
        return fp
    # 再从 query params 取（内网 HMAC 方式）
    fp = request.args.get("device_fingerprint")
    if fp:
        return fp
    return None

def _ensure_key_enabled(api_key: str):
    key_info = get_valid_keys().get(api_key)
    if not key_info:
        abort(401, description="Invalid api_key")
    if key_info["status"] != "enable":
        abort(401, description=f"API key {key_info['status']}")

def _do_device_check(api_key: str):
    """统一设备指纹校验入口"""
    key_info = get_valid_keys().get(api_key)
    if not key_info:
        abort(401, description="Invalid api_key")

    role = key_info.get("role")
    if role == "super_admin":
        return

    device_fp = _get_device_fingerprint()
    if not device_fp:
        abort(400, description="Missing device_fingerprint")
    try:
        check_device_binding(api_key, device_fp)
    except RuntimeError:
        abort(403, description="API key already bound to another device")

def check_public_auth():
    # 公网 HTTPS：仅校验 api_key，不防重放
    api_key = request.args.get("api_key") or request.headers.get("Authorization")
    if isinstance(api_key, str) and api_key.startswith("Bearer "):
        api_key = api_key.replace("Bearer ", "")

    if not api_key:
        abort(401, description="Missing api_key")

    _ensure_key_enabled(api_key)

    _do_device_check(api_key)

    record_usage(api_key)

def check_internal_auth():
    api_key = request.args.get("api_key")
    ts = request.args.get("ts", type=int)
    sign = request.args.get("sign")

    if not api_key or ts is None or not sign:
        abort(400, description="Missing parameters")

    _ensure_key_enabled(api_key)

    if abs(time.time() - ts) > 300:
        abort(401, description="Request expired")

    msg = f"{api_key}{ts}"
    expected = hmac.new(
        get_hmac_secret().encode(),
        msg.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, sign):
        abort(401, description="Invalid signature")

    _do_device_check(api_key)

    record_usage(api_key)

# ---------- 接口 ----------
def get_keys():
    load_all()

    if is_public_request():
        check_public_auth()
    else:
        check_internal_auth()

    return jsonify(get_keys_data())

# ---------- 管理员解绑接口（可选） ----------
# def unbind_key():
#     """
#     GET /admin/unbind-key
#     Body: {"api_key": "sk-123456"}
#     Header: Authorization: Bearer <admin_secret>
#     """
#     api_key = request.args.get("api_key")
#     if not api_key:
#         abort(400, description="Missing api_key")
#
#     if unbind_device(api_key):
#         return jsonify({"msg": "unbound", "api_key": api_key})
#
#     return jsonify({"error": "key not found"}), 404


# ---------- 管理员解绑接口（可选） ----------
def unbind_key():
    """
    GET /admin/unbind-key
    Header: Authorization: Bearer <admin_secret>
    无参数：显示输入表单
    带 ?api_key=xxx：执行解绑
    """
    api_key = request.args.get("api_key")

    # 没有传api_key，展示输入页面
    if not api_key:
        html = """
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>设备解绑管理</title>
            <style>
            *{margin:0;padding:0;box-sizing:border-box;font-family:system-ui, -apple-system, sans-serif;}
            body{background-color:#f5f7fa;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}
            .card{background:#ffffff;width:100%;max-width:520px;padding:36px;border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,0.08);}
            .title{font-size:22px;color:#222;margin-bottom:24px;font-weight:600;}
            .label{display:block;color:#444;margin-bottom:8px;font-size:15px;}
            .input{width:100%;padding:14px 16px;border:1px solid #dde1e8;border-radius:10px;font-size:15px;transition:0.2s;outline:none;}
            .input:focus{border-color:#4080ff;box-shadow:0 0 0 3px rgba(64,128,255,0.15);}
            .btn{width:100%;margin-top:20px;padding:14px;background:#4080ff;color:white;border:none;border-radius:10px;font-size:16px;cursor:pointer;transition:0.2s;}
            .btn:hover{background:#2c70ee;}
            </style>
            </head>
            <body>
            <div class="card">
                <h2 class="title">解绑 API Key</h2>
                <form method="get">
                    <label class="label">API_KEY</label>
                    <input class="input" type="text" name="api_key" placeholder="请输入 sk-xxxx 密钥">
                    <button class="btn" type="submit">确认解绑</button>
                </form>
            </div>
            </body>
            </html>
        """
        return html

    # 传了 api_key，执行解绑逻辑
    if unbind_device(api_key):
        result_html = f"""
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>操作成功</title>
            <style>
            *{{margin:0;padding:0;box-sizing:border-box;font-family:system-ui, -apple-system, sans-serif;}}
            body{{background-color:#f5f7fa;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}}
            .card{{background:#ffffff;width:100%;max-width:520px;padding:36px;border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,0.08);text-align:center;}}
            .success-title{{font-size:24px;color:#00b42a;margin-bottom:16px;font-weight:600;}}
            .text{{font-size:15px;color:#444;margin:12px 0;word-break:break-all;}}
            .back{{display:inline-block;margin-top:24px;padding:12px 26px;background:#4080ff;color:#fff;border-radius:10px;text-decoration:none;transition:0.2s;}}
            .back:hover{{background:#2c70ee;}}
            </style>
            </head>
            <body>
            <div class="card">
                <h2 class="success-title">✅ 解绑成功</h2>
                <p class="text">API Key：{api_key}</p>
                <a class="back" href="/admin/unbind-key">返回页面</a>
            </div>
            </body>
            </html>
        """
        return result_html
    else:
        result_html = f"""
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>操作失败</title>
            <style>
            *{{margin:0;padding:0;box-sizing:border-box;font-family:system-ui, -apple-system, sans-serif;}}
            body{{background-color:#f5f7fa;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}}
            .card{{background:#ffffff;width:100%;max-width:520px;padding:36px;border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,0.08);text-align:center;}}
            .error-title{{font-size:24px;color:#f53f3f;margin-bottom:16px;font-weight:600;}}
            .text{{font-size:15px;color:#444;margin:12px 0;word-break:break-all;}}
            .back{{display:inline-block;margin-top:24px;padding:12px 26px;background:#4080ff;color:#fff;border-radius:10px;text-decoration:none;transition:0.2s;}}
            .back:hover{{background:#2c70ee;}}
            </style>
            </head>
            <body>
            <div class="card">
                <h2 class="error-title">❌ Key未使用过或不存在，解绑失败</h2>
                <p class="text">API Key：{api_key}</p>
                <a class="back" href="/admin/unbind-key">返回页面</a>
            </div>
            </body>
            </html>
        """
        return result_html

