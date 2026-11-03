#!/usr/bin/env python3
"""
VidVault Local Development Runner
Runs the Flask application locally for testing and development.
"""
import os
import sys

# Ensure api directory is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.join(current_dir, "api")
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from index import app, FFMPEG_AVAILABLE, FFMPEG_PATH

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print(" 🚀 VidVault - Professional YouTube Video Downloader")
    print(f" 🌐 Running at: http://127.0.0.1:{port}")
    print(f" ⚙️  FFmpeg Available: {FFMPEG_AVAILABLE} ({FFMPEG_PATH or 'Not Found'})")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=True)
