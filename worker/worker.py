import json
import os
import subprocess
import sys
import tempfile
import requests
import base64

def must_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing env: {name}")
    return v

def sniff_head(path: str, n: int = 64) -> bytes:
    with open(path, "rb") as f:
        return f.read(n)

def looks_like_mp4(head: bytes) -> bool:
    # MP4 常見：前面 4 bytes size，之後會有 b'ftyp' 出現
    return b"ftyp" in head[:32]

def looks_like_mp3(head: bytes) -> bool:
    # MP3 常見：ID3 header 或 frame sync 0xFFEx
    if head.startswith(b"ID3"):
        return True
    return len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0

def download(url: str, out_path: str, kind: str):
    with requests.get(url, stream=True, timeout=300) as r:
        # 先把最重要資訊印出，方便你對照係咪用錯 URL / 過期 / 404
        ct = r.headers.get("Content-Type", "")
        cl = r.headers.get("Content-Length", "")
        print(f"[download:{kind}] status={r.status_code} ct={ct} cl={cl}", file=sys.stderr)
        r.raise_for_status()

        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    size = os.path.getsize(out_path)
    head = sniff_head(out_path, 64)
    print(f"[download:{kind}] saved_bytes={size} head={head[:64]!r}", file=sys.stderr)

    if size < 1024:
        raise RuntimeError(f"{kind} too small ({size} bytes). Usually 404/403 HTML/XML was saved. head={head!r}")

    # 粗略驗證：避免把 XML/HTML/JSON 當 mp4/mp3
    if kind == "video" and not looks_like_mp4(head):
        raise RuntimeError(f"video not mp4-like. head={head!r} (likely wrong/expired URL or object not found)")
    if kind == "audio" and not (looks_like_mp3(head) or b"ftyp" in head[:32]):
        # 有啲音訊可能係 m4a/aac in mp4 container，允許 ftyp
        raise RuntimeError(f"audio not mp3/m4a-like. head={head!r} (likely wrong/expired URL or object not found)")

def put_upload(put_url: str, file_path: str, content_type: str = "video/mp4"):
    size = os.path.getsize(file_path)
    print(f"[upload] bytes={size} ct={content_type}", file=sys.stderr)
    with open(file_path, "rb") as f:
        r = requests.put(put_url, data=f, headers={"Content-Type": content_type}, timeout=1800)
        print(f"[upload] status={r.status_code}", file=sys.stderr)
        r.raise_for_status()

def run_ffmpeg(video_path: str, audio_path: str, out_path: str, duration_sec: int):
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-stream_loop", "-1", "-i", video_path,
        "-stream_loop", "-1", "-i", audio_path,
        "-t", str(duration_sec),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        out_path,
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + p.stdout)

def main():
    payload_b64 = must_env("PAYLOAD_B64")
    payload = json.loads(base64.b64decode(payload_b64).decode("utf-8"))

    params = payload["params"]
    duration = int(params["durationSec"])
    video_url = params["video"]["url"]
    audio_url = params["audio"]["url"]
    put_url = params["output"]["upload"]["putUrl"]

    # 把三條 URL 印出，直接驗證上游有冇「錯位」(例如 video_url 其實等於 put_url)
    print(f"[urls] video_url={video_url}", file=sys.stderr)
    print(f"[urls] audio_url={audio_url}", file=sys.stderr)
    print(f"[urls] put_url={put_url}", file=sys.stderr)

    with tempfile.TemporaryDirectory() as d:
        video_path = os.path.join(d, "in.mp4")
        audio_path = os.path.join(d, "in.mp3")
        out_path = os.path.join(d, "final.mp4")

        download(video_url, video_path, "video")
        download(audio_url, audio_path, "audio")
        run_ffmpeg(video_path, audio_path, out_path, duration)
        put_upload(put_url, out_path)

    print(json.dumps({"ok": True}, ensure_ascii=False))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
