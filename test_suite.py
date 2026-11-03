#!/usr/bin/env python3
"""
VidVault Automated End-to-End Test Suite
Tests all endpoints, format extraction, download pipelines, and security validations.
"""
import sys
import os
import unittest
import json

# Ensure stdout handles UTF-8 safely on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Setup import path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.join(BASE_DIR, "api")
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

from index import app, is_valid_youtube_url, sanitize_filename, format_duration, format_filesize


class VidVaultTestCase(unittest.TestCase):
    extracted_info = None

    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()
        cls.test_video_url = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"  # Big Buck Bunny

    def test_01_unit_helpers(self):
        """Test URL validation regex and helper utilities."""
        print("\n[TEST 1] Testing URL validation and helper functions...")
        self.assertTrue(is_valid_youtube_url("https://www.youtube.com/watch?v=aqz-KE-bpKQ"))
        self.assertTrue(is_valid_youtube_url("https://youtu.be/aqz-KE-bpKQ"))
        self.assertTrue(is_valid_youtube_url("https://www.youtube.com/shorts/dQw4w9WgXcQ"))
        self.assertTrue(is_valid_youtube_url("http://youtube.com/watch?v=aqz-KE-bpKQ"))

        # Invalid / SSRF attempts
        self.assertFalse(is_valid_youtube_url("https://google.com/watch?v=12345678901"))
        self.assertFalse(is_valid_youtube_url("http://localhost:5000/malicious"))
        self.assertFalse(is_valid_youtube_url("ftp://youtube.com/watch?v=12345678901"))
        self.assertFalse(is_valid_youtube_url("not_a_url"))
        self.assertFalse(is_valid_youtube_url(""))

        # Helpers
        self.assertEqual(sanitize_filename("Video? Title: With/Slash*"), "Video Title WithSlash")
        self.assertEqual(format_duration(65), "01:05")
        self.assertEqual(format_duration(3665), "1:01:05")
        self.assertIn("MB", format_filesize(25 * 1024 * 1024))
        print("  [PASS] URL validation and helpers passed.")

    def test_02_health_endpoint(self):
        """Test GET /api/health."""
        print("\n[TEST 2] Testing GET /api/health endpoint...")
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "VidVault YouTube Video Downloader")
        self.assertIn("ffmpeg_available", data)
        print(f"  [PASS] Health check response: {data}")

    def test_03_static_files(self):
        """Test static frontend asset delivery."""
        print("\n[TEST 3] Testing static files delivery...")
        res_home = self.client.get("/")
        self.assertEqual(res_home.status_code, 200)
        self.assertIn(b"VidVault", res_home.data)

        res_css = self.client.get("/css/style.css")
        self.assertEqual(res_css.status_code, 200)
        self.assertIn(b"--bg-main", res_css.data)

        res_js = self.client.get("/js/app.js")
        self.assertEqual(res_js.status_code, 200)
        self.assertIn(b"analyzeVideo", res_js.data)
        print("  [PASS] Static files (index.html, style.css, app.js) served successfully.")

    def test_04_video_info_invalid_urls(self):
        """Test POST /api/video-info with bad requests."""
        print("\n[TEST 4] Testing video-info error handling for bad inputs...")
        # Empty payload
        res = self.client.post("/api/video-info", json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

        # Non-youtube URL (SSRF block)
        res = self.client.post("/api/video-info", json={"url": "https://malicious-site.com/exploit"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Invalid URL format", res.get_json()["error"])
        print("  [PASS] Error handling verified for invalid inputs.")

    def test_05_video_info_valid_url(self):
        """Test POST /api/video-info with authentic YouTube URL."""
        print("\n[TEST 5] Testing POST /api/video-info extraction for sample video...")
        res = self.client.post("/api/video-info", json={"url": self.test_video_url})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertIn("title", data)
        self.assertIn("thumbnail", data)
        self.assertIn("video_formats", data)
        self.assertIn("audio_formats", data)
        self.assertTrue(len(data["video_formats"]) > 0 or len(data["audio_formats"]) > 0)

        print(f"  [PASS] Extracted Video Title: {data['title']}")
        print(f"  [PASS] Channel: {data['channel']}")
        print(f"  [PASS] Duration: {data['duration_formatted']}")
        print(f"  [PASS] Video formats discovered: {len(data['video_formats'])}")
        print(f"  [PASS] Audio formats discovered: {len(data['audio_formats'])}")

        VidVaultTestCase.extracted_info = data

    def test_06_video_download(self):
        """Test /api/download with real format."""
        print("\n[TEST 6] Testing media download via /api/download...")
        info = VidVaultTestCase.extracted_info
        if not info:
            res = self.client.post("/api/video-info", json={"url": self.test_video_url})
            info = res.get_json()

        audio_formats = info.get("audio_formats", [])
        video_formats = info.get("video_formats", [])

        # Choose the smallest available format for rapid testing
        chosen_format_id = None
        chosen_ext = "m4a"
        if audio_formats:
            # Pick a native audio format (e.g., format 139 or 140 or webm)
            native_audio = [f for f in audio_formats if not f["format_id"].startswith("mp3_converted_")]
            chosen = min(native_audio, key=lambda x: x.get("raw_abr") or 999) if native_audio else audio_formats[0]
            chosen_format_id = chosen["format_id"]
            chosen_ext = chosen["ext"]
        elif video_formats:
            chosen_format_id = video_formats[-1]["format_id"]
            chosen_ext = video_formats[-1]["ext"]

        print(f"  Testing download of format_id: {chosen_format_id} ({chosen_ext})...")
        res = self.client.get(f"/api/download?url={self.test_video_url}&format_id={chosen_format_id}&ext={chosen_ext}&title=TestDownload")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Content-Disposition", res.headers)
        self.assertIn("attachment", res.headers["Content-Disposition"])
        content_length = len(res.data)
        self.assertGreater(content_length, 10000)
        print(f"  [PASS] Download succeeded! Received {content_length} bytes with attachment header: {res.headers['Content-Disposition']}")


if __name__ == "__main__":
    unittest.main()
