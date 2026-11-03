"""Per-user API credentials outside life packs. No plaintext storage fallback.

Windows DPAPI protects the local payload; a life pack stores only a random
reference. The encrypted payload binds a key to its adapter and endpoint.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .i18n import t


class CredentialError(ValueError):
    pass


def supported():
    return os.name == "nt"


def scope(config):
    adapter = str(config.get("adapter") or "")
    default = "https://api.anthropic.com" if adapter == "anthropic" else "https://api.deepseek.com/v1"
    address = str(config.get("base_url") or default).strip().rstrip("/")
    try:
        parsed = urlsplit(address)
        if (adapter not in ("anthropic", "openai-compatible") or parsed.scheme != "https"
                or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError()
        host = parsed.hostname.lower()
        if ":" in host:
            host = "[" + host + "]"
        port = parsed.port
        origin = "https://" + host + (":" + str(port) if port and port != 443 else "")
        return [adapter, origin + parsed.path.rstrip("/")]
    except ValueError:
        raise CredentialError(t("本机保存的 API Key 需要有效的 HTTPS 接口地址。")) from None


def _path(reference):
    if not re.fullmatch(r"[a-f0-9]{32}", str(reference or "")):
        raise CredentialError(t("本机密钥引用无效，请重新填写 API Key。"))
    return Path.home() / ".seedbank" / "credentials" / (reference + ".dpapi")


def available(reference):
    try:
        return supported() and _path(reference).is_file()
    except (CredentialError, OSError):
        return False


def _crypt(data, *, decrypt=False):
    if not supported():
        raise CredentialError(t("此系统暂不支持本机密钥保存，请使用环境变量方式。"))
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    try:
        # UI forbidden, current user scope; never CRYPTPROTECT_LOCAL_MACHINE.
        if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
            raise CredentialError(t("无法使用本机密钥，请重新填写或改用环境变量方式。"))
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.memset(buffer, 0, ctypes.sizeof(buffer))
        if result.data:
            ctypes.memset(result.data, 0, result.size)
            kernel32.LocalFree(result.data)


def store(key, config):
    key = str(key or "").strip()
    if not key or len(key) > 8192 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise CredentialError(t("API Key 不能为空，也不能包含空格或换行。"))
    payload = json.dumps({"version": 1, "scope": scope(config), "key": key}).encode("utf-8")
    encrypted = _crypt(payload)
    reference = uuid.uuid4().hex
    target = _path(reference)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(encrypted)
    except OSError:
        raise CredentialError(t("无法保存本机密钥，请检查用户目录权限。")) from None
    return reference


def load(reference, config):
    expected = scope(config)
    try:
        payload = json.loads(_crypt(_path(reference).read_bytes(), decrypt=True))
    except (OSError, ValueError, UnicodeError):
        raise CredentialError(t("无法使用本机密钥，请重新填写或改用环境变量方式。")) from None
    if not isinstance(payload, dict) or payload.get("version") != 1 or payload.get("scope") != expected:
        raise CredentialError(t("接口地址或类型已改变，请重新填写 API Key。"))
    key = payload.get("key")
    if not isinstance(key, str) or not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise CredentialError(t("无法使用本机密钥，请重新填写或改用环境变量方式。"))
    return key
