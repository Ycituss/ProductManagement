import json
import time
import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
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
_last_reload_ts = 0.0   # 新增：防抖时间戳
RELOAD_DEBOUNCE = 0.5   # 0.5秒内不重复重载


# ---------- 加载函数 ----------
def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_all(force=False):
    """
    接口入口调用，自动热加载
    修复并发重复加载 + 文件变更检测竞态
    """
    global VALID_API_KEYS, KEYS_DATA, HMAC_SECRET
    global KEY_USAGE, _last_mtime, _last_reload_ts

    now = time.time()
    # 快速防抖：短时间强制跳过
    if not force and (now - _last_reload_ts) < RELOAD_DEBOUNCE:
        return

    try:
        # 先尝试获取文件mtime（失败直接退出）
        current_mtime = os.path.getmtime(KEYS_FILE)
    except FileNotFoundError:
        return
    except Exception:
        return

    # 无需重载，直接返回
    if not force and current_mtime == _last_mtime:
        return

    # ===== 只有确认需要重载，才进入锁 =====
    with _state_lock:
        # 【双重检查】防止进入锁前其他请求已经完成加载
        try:
            current_mtime = os.path.getmtime(KEYS_FILE)
        except Exception:
            return
        if not force and current_mtime == _last_mtime:
            return

        try:
            # 加载全部资源
            keys_json = _load_json(KEYS_FILE)
            raw = keys_json["keys"]
            VALID_API_KEYS = {item["key"]: item for item in raw}
            KEYS_DATA = _load_json(DATA_FILE)
            HMAC_SECRET = open(SECRET_FILE, "r", encoding="utf-8").read().strip()

            if os.path.exists(USAGE_FILE):
                KEY_USAGE = _load_json(USAGE_FILE)
            else:
                KEY_USAGE = {}

            _last_mtime = current_mtime
            _last_reload_ts = time.time()
            print("[HotReload] 配置文件已重新加载", flush=True)
        except Exception as e:
            # 加载失败，保持旧数据，不覆盖空值！重要！
            print(f"[HotReload Failed] {e}", flush=True)


# ---------- 使用记录 ----------
def record_usage(api_key: str):
    """记录调用信息"""
    now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S UTC+8")
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


# ---------- 设备绑定 ----------
def check_device_binding(api_key: str, device_fp: str):
    """
    一 key 一设备绑定校验
    - 首次使用 → 自动绑定
    - 后续使用 → 必须一致
    - 不一致 → 抛 RuntimeError，由调用方 abort
    """
    with _state_lock:
        info = KEY_USAGE.setdefault(api_key, {})
        bound_fp = info.get("bound_fp")

        if not bound_fp:
            # 首次使用，自动绑定
            info["bound_fp"] = device_fp
            info["bound_at"] = now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S UTC+8")
            info["bind_count"] = info.get("bind_count", 0) + 1

            # 同时补上基础使用记录
            info.setdefault("last_used_at", now)
            info.setdefault("last_ip", request.headers.get("X-Forwarded-For", request.remote_addr))
            info.setdefault("request_count", 0)
            info.setdefault("last_user_agent", request.headers.get("User-Agent", ""))

            _persist_usage()
        elif bound_fp != device_fp:
            # 设备不一致，拒绝
            raise RuntimeError("device_mismatch")

def unbind_device(api_key: str):
    """管理员解绑设备"""
    with _state_lock:
        if api_key in KEY_USAGE:
            KEY_USAGE[api_key].pop("bound_fp", None)
            KEY_USAGE[api_key].pop("bound_at", None)
            _persist_usage()
            return True
        return False

def _persist_usage():
    """持久化 KEY_USAGE.json（调用方需已持有 _state_lock）"""
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(KEY_USAGE, f, indent=2, ensure_ascii=False)


# ---------- 数据接口 ----------
def get_valid_keys():
    with _state_lock:
        return VALID_API_KEYS

def get_keys_data():
    with _state_lock:
        return KEYS_DATA

def get_hmac_secret():
    with _state_lock:
        return HMAC_SECRET


# ---------- 首次加载 ----------
load_all(force=True)