import os
import re
import sys
import shutil
import tempfile
import logging
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_file, after_this_request
import yt_dlp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("vidvault")

# Determine base paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

app = Flask(
    __name__,
    static_folder=PUBLIC_DIR if os.path.exists(PUBLIC_DIR) else None,
    static_url_path=""
)


class VercelPathFixMiddleware:
    """
    WSGI Middleware for Vercel Serverless Functions.
    Vercel rewrites /api/* to /api/index.py, setting PATH_INFO = /api/index.py.
    This middleware restores PATH_INFO from HTTP_X_MATCHED_PATH or HTTP_X_FORWARDED_URI.
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path_info = environ.get("PATH_INFO", "")
        if path_info in ("/api/index.py", "/api/index", "/index.py", "/api") or path_info.endswith("/index.py"):
            matched = (
                environ.get("HTTP_X_MATCHED_PATH")
                or environ.get("HTTP_X_FORWARDED_URI")
                or environ.get("HTTP_X_NOW_ROUTE_MATCHES")
                or environ.get("RAW_URI")
                or environ.get("REQUEST_URI")
            )
            if matched:
                clean_path = matched.split("?")[0]
                if clean_path and not clean_path.endswith("/index.py"):
                    environ["PATH_INFO"] = clean_path
        return self.wsgi_app(environ, start_response)


app.wsgi_app = VercelPathFixMiddleware(app.wsgi_app)

# Configuration & Platform Limits (Respecting Vercel serverless bounds when deployed)
IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
DEFAULT_MAX_DURATION = 1800 if IS_SERVERLESS else 14400  # 30 mins on serverless, 4 hours locally
DEFAULT_MAX_FILESIZE = 200 * 1024 * 1024 if IS_SERVERLESS else 2 * 1024 * 1024 * 1024  # 200 MB on serverless, 2 GB locally

MAX_VIDEO_DURATION_SECONDS = int(os.environ.get("MAX_VIDEO_DURATION_SECONDS", DEFAULT_MAX_DURATION))
MAX_ESTIMATED_FILE_SIZE_BYTES = int(os.environ.get("MAX_ESTIMATED_FILE_SIZE_BYTES", DEFAULT_MAX_FILESIZE))
FFMPEG_PATH = shutil.which("ffmpeg")
FFMPEG_AVAILABLE = FFMPEG_PATH is not None

# Detect JS runtimes for yt-dlp challenge solving
def detect_js_runtimes():
    """Detect Node.js (version 22+ preferred) or Deno for yt-dlp JavaScript challenge solving."""
    runtimes = {}
    node_path = shutil.which("node")
    if node_path:
        try:
            import subprocess
            res = subprocess.run([node_path, "--version"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                v_str = res.stdout.strip().lstrip("v")
                major = int(v_str.split(".")[0])
                if major >= 22:
                    logger.info(f"Node.js {res.stdout.strip()} (>= 22) detected: {node_path}")
                else:
                    logger.warning(f"Node.js {res.stdout.strip()} detected (recommend >= 22): {node_path}")
                runtimes["node"] = {"path": node_path}
        except Exception as ex:
            logger.warning(f"Error checking Node.js: {ex}")
            runtimes["node"] = {"path": node_path}

    deno_path = shutil.which("deno")
    if deno_path:
        runtimes["deno"] = {"path": deno_path}

    return runtimes

JS_RUNTIMES = detect_js_runtimes()

# YouTube URL validation pattern
YOUTUBE_URL_REGEX = re.compile(
    r'^(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be)/(watch\?v=|embed/|v/|shorts/)?([a-zA-Z0-9_-]{11})([&?].*)?$'
)


def is_valid_youtube_url(url: str) -> bool:
    """Validate that input is a legitimate YouTube URL to prevent SSRF and injection."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    hostname = (parsed.hostname or '').lower()
    if not (hostname == 'youtube.com' or hostname.endswith('.youtube.com') or hostname == 'youtu.be'):
        return False
    return bool(YOUTUBE_URL_REGEX.match(url))


def sanitize_filename(name: str, max_length: int = 80) -> str:
    """Sanitize title for safe Content-Disposition attachment headers."""
    if not name:
        return "vidvault_download"
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r'\s+', " ", clean).strip()
    if not clean:
        clean = "vidvault_download"
    return clean[:max_length]


def format_duration(seconds: int) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    if not seconds or seconds < 0:
        return "00:00"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    rem_seconds = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{rem_seconds:02d}"
    return f"{minutes:02d}:{rem_seconds:02d}"


def format_filesize(bytes_val: int) -> str:
    """Convert bytes to human-readable string (KB, MB, GB)."""
    if not bytes_val or bytes_val <= 0:
        return "Unknown size"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} TB"


def get_ydl_base_opts():
    """Return standard yt-dlp configuration options."""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'no_color': True,
        'socket_timeout': 20,
    }
    if JS_RUNTIMES:
        opts['js_runtimes'] = JS_RUNTIMES
    else:
        opts['extractor_args'] = {
            'youtube': {
                'player_client': ['android', 'web']
            }
        }
    if FFMPEG_PATH:
        opts['ffmpeg_location'] = FFMPEG_PATH
    return opts


# ==========================================
# Static Routes (for local dev / fallback)
# ==========================================
@app.route("/")
def serve_home():
    if os.path.exists(os.path.join(PUBLIC_DIR, "index.html")):
        return send_file(os.path.join(PUBLIC_DIR, "index.html"))
    return jsonify({"status": "VidVault API is running", "endpoints": ["/api/health", "/api/video-info", "/api/download"]})


# ==========================================
# API Endpoints
# ==========================================
@app.route("/api/health", methods=["GET"])
@app.route("/health", methods=["GET"])
def health_check():
    """Health status and capabilities endpoint."""
    return jsonify({
        "status": "ok",
        "service": "VidVault YouTube Video Downloader",
        "version": "1.0.0",
        "ffmpeg_available": FFMPEG_AVAILABLE,
        "js_runtimes": list(JS_RUNTIMES.keys()),
        "max_video_duration_minutes": MAX_VIDEO_DURATION_SECONDS // 60,
        "max_filesize_mb": MAX_ESTIMATED_FILE_SIZE_BYTES // (1024 * 1024)
    })


@app.route("/api/video-info", methods=["POST"])
@app.route("/video-info", methods=["POST"])
def get_video_info():
    """Extract and return video metadata and available download formats."""
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "Please provide a valid YouTube URL."}), 400

    if not is_valid_youtube_url(url):
        return jsonify({
            "error": "Invalid URL format. Please provide a standard YouTube video or Shorts link (e.g., https://www.youtube.com/watch?v=...)."
        }), 400

    match = YOUTUBE_URL_REGEX.match(url)
    clean_id = match.group(5) if match else "unknown"
    logger.info(f"Extracting video metadata for ID: {clean_id}")
    ydl_opts = get_ydl_base_opts()

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return jsonify({"error": "Unable to extract information for this video."}), 404

            # Basic metadata
            video_id = info.get("id", "")
            title = info.get("title", "Unknown Title")
            channel = info.get("channel") or info.get("uploader") or "Unknown Channel"
            duration = info.get("duration") or 0
            thumbnail = info.get("thumbnail") or f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            view_count = info.get("view_count") or 0
            upload_date = info.get("upload_date") or ""
            if upload_date and len(upload_date) == 8:
                formatted_date = f"{upload_date[0:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
            else:
                formatted_date = upload_date

            is_duration_exceeded = duration > MAX_VIDEO_DURATION_SECONDS

            # Parse and organize formats
            raw_formats = info.get("formats", [])
            video_formats = []
            audio_formats = []

            seen_video_keys = {}
            seen_audio_keys = set()

            for f in raw_formats:
                format_id = str(f.get("format_id", ""))
                ext = f.get("ext", "")
                vcodec = f.get("vcodec") or "none"
                acodec = f.get("acodec") or "none"
                filesize = f.get("filesize") or f.get("filesize_approx") or 0
                height = f.get("height")
                has_video = vcodec != "none"
                has_audio = acodec != "none"
                is_progressive = has_video and has_audio

                # 1. Video Formats
                if has_video and height and ext in ("mp4", "webm"):
                    res_label = f"{height}p"
                    key = (height, ext)

                    # Progressive format always takes precedence for that resolution
                    can_download = is_progressive or FFMPEG_AVAILABLE

                    format_obj = {
                        "format_id": format_id,
                        "resolution": res_label,
                        "height": height,
                        "ext": ext,
                        "filesize": filesize,
                        "filesize_formatted": format_filesize(filesize),
                        "is_progressive": is_progressive,
                        "has_audio": has_audio,
                        "requires_ffmpeg": not is_progressive,
                        "supported": can_download,
                        "fps": f.get("fps"),
                        "vcodec": vcodec.split('.')[0] if vcodec else "unknown",
                        "note": "Complete Video with Audio" if is_progressive else ("Muxed HD (Audio Auto-Merged)" if FFMPEG_AVAILABLE else "Video Stream Only")
                    }

                    if key not in seen_video_keys:
                        seen_video_keys[key] = format_obj
                    else:
                        # If existing is not progressive but this one is, replace it
                        if not seen_video_keys[key]["is_progressive"] and is_progressive:
                            seen_video_keys[key] = format_obj

                # 2. Audio-only Formats
                if has_audio and not has_video and ext in ("m4a", "webm", "mp3"):
                    abr = int(f.get("abr") or 0)
                    approx_abr = round(abr / 10) * 10 if abr else 0
                    audio_key = (ext, approx_abr)

                    if audio_key not in seen_audio_keys and abr > 0:
                        seen_audio_keys.add(audio_key)
                        audio_formats.append({
                            "format_id": format_id,
                            "ext": ext,
                            "bitrate": f"{abr} kbps",
                            "raw_abr": abr,
                            "filesize": filesize,
                            "filesize_formatted": format_filesize(filesize),
                            "acodec": acodec.split('.')[0] if acodec else "unknown",
                            "requires_ffmpeg": False,
                            "supported": True,
                            "note": "Native Audio Stream (Fast Direct Download)"
                        })

            video_formats = list(seen_video_keys.values())

            # Sort video formats descending by resolution height, prioritizing MP4
            video_formats.sort(key=lambda x: (x["height"], 1 if x["ext"] == "mp4" else 0, 1 if x["is_progressive"] else 0), reverse=True)

            # Sort audio formats descending by bitrate
            audio_formats.sort(key=lambda x: x["raw_abr"], reverse=True)

            # If FFmpeg is available and audio formats exist, offer converted MP3
            if FFMPEG_AVAILABLE and audio_formats:
                best_audio = audio_formats[0]
                audio_formats.insert(0, {
                    "format_id": f"mp3_converted_{best_audio['format_id']}",
                    "ext": "mp3",
                    "bitrate": "192 kbps (MP3)",
                    "raw_abr": 192,
                    "filesize": best_audio["filesize"],
                    "filesize_formatted": best_audio["filesize_formatted"],
                    "acodec": "mp3",
                    "requires_ffmpeg": True,
                    "supported": True,
                    "note": "Converted to MP3 via FFmpeg"
                })

            return jsonify({
                "id": video_id,
                "title": title,
                "channel": channel,
                "duration": duration,
                "duration_formatted": format_duration(duration),
                "thumbnail": thumbnail,
                "views": view_count,
                "upload_date": formatted_date,
                "is_duration_exceeded": is_duration_exceeded,
                "max_duration_seconds": MAX_VIDEO_DURATION_SECONDS,
                "video_formats": video_formats,
                "audio_formats": audio_formats,
                "ffmpeg_available": FFMPEG_AVAILABLE
            })

    except yt_dlp.utils.DownloadError as e:
        err_msg = str(e)
        logger.error(f"yt-dlp error during metadata extraction for {clean_id}: {err_msg}")
        if "429" in err_msg or "Too Many Requests" in err_msg:
            return jsonify({
                "error": "YouTube rate limit encountered (HTTP 429). Please wait a moment before trying again."
            }), 429
        elif "403" in err_msg or "Forbidden" in err_msg:
            return jsonify({
                "error": "YouTube denied access (HTTP 403 Forbidden). Video or stream is restricted."
            }), 403
        elif "Private video" in err_msg or "Sign in" in err_msg:
            return jsonify({
                "error": "This video is private, restricted, or requires login credentials."
            }), 403
        elif "Video unavailable" in err_msg:
            return jsonify({
                "error": "This video is unavailable or has been removed."
            }), 404
        return jsonify({
            "error": "Failed to analyze video. YouTube may have restricted access or the link is invalid."
        }), 400

    except Exception as e:
        logger.exception("Unexpected error during video analysis")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


@app.route("/api/download", methods=["GET", "POST"])
@app.route("/download", methods=["GET", "POST"])
def download_video():
    """
    Process and deliver video/audio downloads.
    Accepts GET with query parameters or POST with JSON body.
    Streams the output file as a browser attachment with Content-Disposition.
    """
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        url = data.get("url", "").strip()
        format_id = data.get("format_id", "").strip()
        ext = data.get("ext", "mp4").strip().lower()
        title = data.get("title", "").strip()
    else:
        url = request.args.get("url", "").strip()
        format_id = request.args.get("format_id", "").strip()
        ext = request.args.get("ext", "mp4").strip().lower()
        title = request.args.get("title", "").strip()

    if not url or not is_valid_youtube_url(url):
        return jsonify({"error": "A valid YouTube URL is required."}), 400

    if not format_id:
        return jsonify({"error": "A format_id is required for download."}), 400

    match = YOUTUBE_URL_REGEX.match(url)
    clean_id = match.group(5) if match else "unknown"

    temp_dir = tempfile.mkdtemp(prefix="vidvault_")

    try:
        is_mp3_conversion = format_id.startswith("mp3_converted_")
        target_format = format_id.replace("mp3_converted_", "") if is_mp3_conversion else format_id

        output_template = os.path.join(temp_dir, "%(title).60s.%(ext)s")

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'outtmpl': output_template,
            'socket_timeout': 30,
            'max_filesize': MAX_ESTIMATED_FILE_SIZE_BYTES,
            'http_chunk_size': 10485760,  # 10MB chunking avoids YouTube 403 on mid-stream drops
            'retries': 10,
            'fragment_retries': 10,
            'file_access_retries': 5,
        }

        if JS_RUNTIMES:
            ydl_opts['js_runtimes'] = JS_RUNTIMES

        if FFMPEG_PATH:
            ydl_opts['ffmpeg_location'] = FFMPEG_PATH

        if is_mp3_conversion:
            if not FFMPEG_AVAILABLE:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return jsonify({
                    "error": "MP3 conversion requires FFmpeg, which is not available in the current environment. Please select native M4A format."
                }), 400

            ydl_opts['format'] = target_format
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            if FFMPEG_AVAILABLE:
                if ext == "mp4":
                    ydl_opts['format'] = f"{target_format}+bestaudio[ext=m4a]/bestaudio/best"
                elif ext == "webm":
                    ydl_opts['format'] = f"{target_format}+bestaudio[ext=webm]/bestaudio/best"
                else:
                    ydl_opts['format'] = f"{target_format}+bestaudio/best"
                ydl_opts['merge_output_format'] = ext if ext in ('mp4', 'mkv', 'webm') else 'mp4'
            else:
                ydl_opts['format'] = target_format

        logger.info(f"Downloading video {clean_id} - format: {ydl_opts['format']}")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return jsonify({"error": "Unable to extract stream info for download."}), 404

            duration = info.get("duration") or 0
            if duration > MAX_VIDEO_DURATION_SECONDS:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return jsonify({
                    "error": f"Video duration ({format_duration(duration)}) exceeds processing limit of {MAX_VIDEO_DURATION_SECONDS // 60} minutes."
                }), 400

            # Execute download with ydl.download([url]) so yt-dlp can handle
            # range requests, automatic retries, and token refreshes on dropped connections.
            exit_code = ydl.download([url])
            if exit_code != 0:
                raise yt_dlp.utils.DownloadError("yt-dlp download failed with non-zero exit code.")

        downloaded_files = [
            f for f in os.listdir(temp_dir)
            if not f.endswith(('.part', '.ytdl', '.temp', '.aria2'))
        ]
        if not downloaded_files:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return jsonify({"error": "File was not generated by download worker."}), 500

        downloaded_file = os.path.join(temp_dir, downloaded_files[0])
        file_size = os.path.getsize(downloaded_file)

        if file_size > MAX_ESTIMATED_FILE_SIZE_BYTES:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return jsonify({
                "error": f"Downloaded file size ({format_filesize(file_size)}) exceeds platform response limit ({format_filesize(MAX_ESTIMATED_FILE_SIZE_BYTES)})."
            }), 413

        base_title = title or os.path.splitext(downloaded_files[0])[0]
        actual_ext = os.path.splitext(downloaded_files[0])[1].lstrip('.') or ext
        safe_filename = f"{sanitize_filename(base_title)}.{actual_ext}"

        mimetypes = {
            'mp4': 'video/mp4',
            'webm': 'video/webm',
            'mkv': 'video/x-matroska',
            'mp3': 'audio/mpeg',
            'm4a': 'audio/mp4',
            'opus': 'audio/opus'
        }
        mime_type = mimetypes.get(actual_ext.lower(), 'application/octet-stream')

        @after_this_request
        def cleanup_temp(response):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"Cleaned up temp directory: {temp_dir}")
            except Exception as ex:
                logger.warning(f"Error during temp cleanup: {ex}")
            return response

        return send_file(
            downloaded_file,
            as_attachment=True,
            download_name=safe_filename,
            mimetype=mime_type
        )

    except yt_dlp.utils.DownloadError as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        err_msg = str(e)
        logger.error(f"Download error for video {clean_id}: {err_msg}")
        if "429" in err_msg or "Too Many Requests" in err_msg:
            return jsonify({"error": "YouTube rate limit encountered (HTTP 429). Please wait before trying again."}), 429
        elif "403" in err_msg or "Forbidden" in err_msg:
            return jsonify({"error": "YouTube restricted stream access (HTTP 403 Forbidden). The requested format could not be retrieved."}), 403
        return jsonify({"error": f"Failed to download requested stream: {err_msg}"}), 400

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.exception("Unexpected error during download processing")
        return jsonify({"error": f"Download processing failed: {str(e)}"}), 500


@app.route("/api/index.py", methods=["GET", "POST"])
@app.route("/index.py", methods=["GET", "POST"])
@app.route("/api", methods=["GET", "POST"])
def vercel_entrypoint_fallback():
    """
    Fallback router if Vercel serverless environment routes directly to /api/index.py.
    Dispatches to the matching handler based on matched path headers or method/body.
    """
    matched = (
        request.headers.get("x-matched-path")
        or request.headers.get("x-forwarded-uri")
        or request.environ.get("RAW_URI", "")
    )
    if matched:
        clean_path = matched.split("?")[0].rstrip("/")
        if clean_path.endswith("/health"):
            return health_check()
        elif clean_path.endswith("/video-info"):
            return get_video_info()
        elif clean_path.endswith("/download"):
            return download_video()

    if request.method == "POST":
        return get_video_info()
    elif request.method == "GET":
        if "url" in request.args:
            return download_video()
        return health_check()

    return jsonify({"status": "healthy", "service": "vidvault-api"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting VidVault server on http://127.0.0.1:{port}")
    print(f"FFmpeg detected: {FFMPEG_AVAILABLE} ({FFMPEG_PATH})")
    print(f"JS Runtimes detected: {list(JS_RUNTIMES.keys())}")
    app.run(host="0.0.0.0", port=port, debug=True)
