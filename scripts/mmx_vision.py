#!/usr/bin/env python3
"""mmx_vision — MiniMax VLM 图片识别封装"""

import subprocess, json, os

MMX = "C:\\Users\\Administrator\\AppData\\Roaming\\npm\\mmx.cmd"

def describe(image_path: str, prompt: str = "Describe the image.") -> dict:
    if not os.path.exists(image_path):
        return {"content": "File not found: " + image_path, "status": "error"}
    cmd = [MMX, "vision", "describe", "--image", image_path,
           "--output", "json", "--quiet", "--non-interactive"]
    if prompt:
        cmd += ["--prompt", prompt]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            return {"content": data.get("content", result.stdout), "status": "success"}
        except:
            return {"content": result.stdout, "status": "partial"}
    else:
        return {"content": result.stderr[:500], "status": "error"}

def extract_text(image_path: str) -> dict:
    return describe(image_path, "Extract all text from this image.")

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "C:/Users/Administrator/Desktop/1.jpg"
    prompt = sys.argv[2] if len(sys.argv) > 2 else None
    result = describe(path, prompt)
    print(result["content"])
