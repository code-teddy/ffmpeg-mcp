import json
import os
import subprocess
import sys
import tempfile
import requests
import base64

def must_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env: {name}")
    return v


def download(url: str, out_path: str):
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def put_upload(put_url: str, file_path: str, content_type: str = "video/mp4"):
    with open(file_path, "rb") as f:
        r = requests.put(put_url, data=f, headers={"Content-Type": content_type}, timeout=1800)
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

    with tempfile.TemporaryDirectory() as d:
        video_path = os.path.join(d, "in.mp4")
        audio_path = os.path.join(d, "in.mp3")
        out_path = os.path.join(d, "final.mp4")

        download(video_url, video_path)
        download(audio_url, audio_path)
        run_ffmpeg(video_path, audio_path, out_path, duration)
        put_upload(put_url, out_path)

    print(json.dumps({"ok": True}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
