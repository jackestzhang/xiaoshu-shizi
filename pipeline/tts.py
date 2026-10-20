"""语音合成：百度公开 TTS 接口（无需 key），按内容哈希缓存。

命名不用 L03_c01.mp3 这类"文件名即身份"的方式，而是：

    key = sha1(text | voice | speed)[:12]
    file = app/assets/audio/<key>.mp3

文字一变，key 就变，旧音频自然失效——不需要任何"清理缓存"的逻辑，
也不会出现换字之后还读旧音的情况。
"""
from __future__ import annotations

import hashlib
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "app" / "assets" / "audio"
AUDIO.mkdir(parents=True, exist_ok=True)

ENDPOINT = "https://fanyi.baidu.com/gettts?lan=zh&spd=3&source=web&text="


def key_for(text: str, voice: str = "baidu-zh", speed: int = 3) -> str:
    raw = f"{text}|{voice}|{speed}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]


def rel_path(text: str) -> str:
    return f"assets/audio/{key_for(text)}.mp3"


def synth(text: str, timeout: int = 20, retries: int = 3) -> Path:
    """返回音频路径；已存在则直接复用（内容哈希，复用是安全的）。"""
    key = key_for(text)
    path = AUDIO / f"{key}.mp3"
    if path.exists() and path.stat().st_size > 800:
        return path

    url = ENDPOINT + urllib.parse.quote(text)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if len(data) < 800 or not (data[:3] == b"ID3" or data[0] == 0xFF):
                raise ValueError(f"返回内容不像 MP3（{len(data)} 字节）")
            path.write_bytes(data)
            return path
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"合成失败：{text}（{last}）")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    args = ap.parse_args()
    p = synth(args.text)
    print(p, p.stat().st_size, "bytes")
