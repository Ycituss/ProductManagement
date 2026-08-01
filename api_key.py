from flask import request, abort, jsonify
import hmac
import hashlib
import time
import json

from key_manager import (
    load_all,
    record_usage,
    VALID_API_KEYS,
    KEYS_DATA,
    HMAC_SECRET,
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

def _ensure_key_enabled(api_key: str):
    key_info = VALID_API_KEYS.get(api_key)
    if not key_info:
        abort(401, description="Invalid api_key")
    if key_info["status"] != "enable":
        abort(401, description=f"API key {key_info['status']}")

def check_public_auth():
    # 公网 HTTPS：仅校验 api_key，不防重放
    api_key = request.args.get("api_key") or request.headers.get("Authorization")
    if isinstance(api_key, str) and api_key.startswith("Bearer "):
        api_key = api_key.replace("Bearer ", "")

    if not api_key:
        abort(401, description="Missing api_key")

    _ensure_key_enabled(api_key)
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
        HMAC_SECRET.encode(),
        msg.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, sign):
        abort(401, description="Invalid signature")

    record_usage(api_key)

# ---------- 接口 ----------
def get_keys():
    load_all()

    if is_public_request():
        check_public_auth()
    else:
        check_internal_auth()

    return jsonify(KEYS_DATA)
