import os
import sys
import time
import urllib.request
import json

URL = "https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
os.makedirs(OUTPUT_DIR, exist_ok=True)
TARGET_FILE = os.path.join(OUTPUT_DIR, "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf")
PART_FILE = TARGET_FILE + ".part"
PROGRESS_FILE = os.path.join(OUTPUT_DIR, "download_progress.json")

def download():
    existing_bytes = os.path.getsize(PART_FILE) if os.path.exists(PART_FILE) else 0
    headers = {"User-Agent": "Mozilla/5.0"}
    if existing_bytes > 0:
        headers["Range"] = f"bytes={existing_bytes}-"

    req = urllib.request.Request(URL, headers=headers)
    
    print(f"Iniciando descarga de Meta-Llama-3.1-8B-Instruct-Q4_K_M...")
    if existing_bytes > 0:
        print(f"Reanudando desde {existing_bytes / (1024*1024):.2f} MB...")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_range = resp.headers.get("Content-Range")
            if content_range:
                total_bytes = int(content_range.split("/")[-1])
            else:
                total_bytes = existing_bytes + int(resp.headers.get("Content-Length", 0))

            start_time = time.time()
            downloaded = existing_bytes
            last_log = time.time()
            chunk_size = 1024 * 512 # 512 KB

            with open(PART_FILE, "ab" if existing_bytes > 0 else "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if now - last_log >= 3.0:
                        last_log = now
                        elapsed = now - start_time
                        speed = (downloaded - existing_bytes) / (elapsed if elapsed > 0 else 1)
                        pct = (downloaded / total_bytes) * 100 if total_bytes > 0 else 0
                        eta_sec = (total_bytes - downloaded) / speed if speed > 0 else 0
                        progress_info = {
                            "downloaded_mb": round(downloaded / (1024*1024), 2),
                            "total_mb": round(total_bytes / (1024*1024), 2),
                            "percent": round(pct, 1),
                            "speed_mbs": round(speed / (1024*1024), 2),
                            "eta_sec": int(eta_sec),
                            "status": "downloading"
                        }
                        with open(PROGRESS_FILE, "w", encoding="utf-8") as pf:
                            json.dump(progress_info, pf)
                        print(f"[{pct:.1f}%] {downloaded/(1024*1024):.1f}/{total_bytes/(1024*1024):.1f} MB | {speed/(1024*1024):.2f} MB/s | ETA: {int(eta_sec//60)}m {int(eta_sec%60)}s", flush=True)

        if os.path.exists(TARGET_FILE):
            os.remove(TARGET_FILE)
        os.rename(PART_FILE, TARGET_FILE)
        with open(PROGRESS_FILE, "w", encoding="utf-8") as pf:
            json.dump({"status": "completed", "percent": 100.0, "file": TARGET_FILE}, pf)
        print("¡Descarga completada con éxito!", flush=True)
    except Exception as e:
        print(f"Error en descarga: {e}", flush=True)
        with open(PROGRESS_FILE, "w", encoding="utf-8") as pf:
            json.dump({"status": "error", "error": str(e)}, pf)

if __name__ == "__main__":
    download()
