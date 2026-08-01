import json
import time
import os
import threading
from flask import request

# ---------- 路径 ----------
BASE_DIR = "./static/api/keys"
KEYS_FILE = os.path.join(BASE_DIR, "VALID_API_KEYS.json")
DATA_FILE = os.path.join(BASE_DIR, "KEYS_DATA.json")
USAGE_FILE = os.path.join(BASE_DIR, "KEY_USAGE.json")
SECRET_FILE = os.path.join(BASE_DIR, "HMAC_SECRET")

# ---------- 全局状态 ----------
_state_lock = threading.Lock()

VALID_API_KEYS = {}
KEYS_DATA = {}
HMAC_SECRET = ""
KEY_USAGE = {}

_last_mtime = 0


# ---------- 加载函数 ----------
def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_all(force=False):
    """根据文件修改时间决定是否重载"""
    global VALID_API_KEYS, KEYS_DATA, HMAC_SECRET
    global KEY_USAGE, _last_mtime

    mtime = os.path.getmtime(KEYS_FILE)

    if not force and mtime == _last_mtime:
        return  # 文件没变，不重载

    with _state_lock:
        raw = _load_json(KEYS_FILE)["keys"]
        VALID_API_KEYS = {item["key"]: item for item in raw}
        KEYS_DATA = _load_json(DATA_FILE)
        HMAC_SECRET = open(SECRET_FILE, "r", encoding="utf-8").read().strip()

        if os.path.exists(USAGE_FILE):
            KEY_USAGE = _load_json(USAGE_FILE)
        else:
            KEY_USAGE = {}

        _last_mtime = mtime


# ---------- 使用记录 ----------
def record_usage(api_key: str):
    """记录调用信息"""
    now = int(time.time())
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    ua = request.headers.get("User-Agent", "")

    with _state_lock:
        info = KEY_USAGE.setdefault(api_key, {
            "last_used_at": now,
            "last_ip": ip,
            "request_count": 0,
            "last_user_agent": ua
        })

        info["last_used_at"] = now
        info["last_ip"] = ip
        info["request_count"] += 1
        info["last_user_agent"] = ua

        # 持久化
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(KEY_USAGE, f, indent=2, ensure_ascii=False)


# ---------- 首次加载 ----------
load_all(force=True)