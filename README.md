# VidVault – Professional YouTube Video Downloader

VidVault is a production-grade YouTube video and audio downloader web application built from scratch with Python, Flask, yt-dlp, HTML5, CSS3, and Vanilla JavaScript. It is designed for single-repository unified deployment on **Vercel** utilizing Vercel's native Python Serverless Functions.

---

## 🌟 Highlights & Features

- **Direct Extraction with yt-dlp**: Fetches and renders genuine, verifiable formats directly from YouTube. Zero simulated or fake quality tiers.
- **Deep Dark Aesthetic**: Engineered with `#080D18` background, `#111827` cards, `#6366F1` purple accent, and `#06B6D4` cyan gradients.
- **Progressive & Separate Streams**: Supports progressive MP4 streams (no FFmpeg needed) and muxed/audio-only tracks with audio extraction (M4A / MP3).
- **Vercel Serverless Optimized**: Built to respect serverless memory limits (512MB `/tmp`), execution windows (30 min video limit), and dynamic cleanup hooks.
- **Hardened Security**: Validates incoming YouTube URLs with strict regex patterns, sanitizes file headers, and shields against Server-Side Request Forgery (SSRF).
- **Zero Framework Bloat**: Pure HTML5, modern CSS3 with custom variables, and clean vanilla JavaScript using the Fetch API.

---

## 📁 Project Architecture

```
vidvault/
├── api/
│   └── index.py            # Flask app & Vercel Serverless Function entry point
├── public/                 # Static assets served directly by Vercel edge CDN
│   ├── index.html          # Responsive landing page & user interface
│   ├── css/
│   │   └── style.css       # Deep dark theme, glassmorphism, responsive styles
│   └── js/
│       └── app.js          # Client logic, URL validation, Fetch API calls
├── requirements.txt        # Python backend dependencies
├── vercel.json             # Vercel unified routing & rewrites configuration
├── run.py                  # Local development server runner
└── README.md               # Documentation and deployment guide
```

---

## 🛠️ API Endpoints

### 1. `GET /api/health`
Returns backend health status, detected tools, and serverless constraints.
```json
{
  "status": "ok",
  "service": "VidVault YouTube Video Downloader",
  "version": "1.0.0",
  "ffmpeg_available": true,
  "max_video_duration_minutes": 30,
  "max_filesize_mb": 200
}
```

### 2. `POST /api/video-info`
Analyzes a YouTube video URL and returns metadata alongside valid video and audio formats.
- **Request Body**:
  ```json
  {
    "url": "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
  }
  ```
- **Response**: Returns video title, thumbnail, channel name, duration, view count, and categorized lists of `video_formats` and `audio_formats`.

### 3. `GET /api/download` or `POST /api/download`
Processes the requested format and streams the media file directly as a browser attachment (`Content-Disposition: attachment; filename="..."`).
- **Query Parameters**:
  - `url`: YouTube video URL
  - `format_id`: yt-dlp format identifier (or `mp3_converted_<id>`)
  - `ext`: Desired extension (`mp4`, `m4a`, `mp3`, `webm`)
  - `title`: Video title for naming

---

## 🚀 Local Development

1. **Clone or navigate to the project directory**:
   ```bash
   cd vidvault
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the local server**:
   ```bash
   python run.py
   ```

4. **Open in your browser**:
   Visit [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## ☁️ Deploying to Vercel

VidVault is configured to deploy with zero extra configuration on Vercel:

1. **Push to GitHub / GitLab / Bitbucket**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit of VidVault"
   git remote add origin <your-repo-url>
   git push -u origin main
   ```

2. **Import Project on Vercel**:
   - Go to [vercel.com/new](https://vercel.com/new).
   - Select your repository.
   - Vercel will automatically read `vercel.json` and deploy both the static frontend (`public/`) and the serverless Flask backend (`api/index.py`).
   - Click **Deploy**.

Alternatively, if you have the Vercel CLI:
```bash
npx vercel
```

---

## ⚖️ Legal & Ethical Usage Notice

VidVault is designed solely for personal use and backup of user-owned media, open-source media, Creative Commons projects, or public domain content. Users are responsible for complying with the copyright policies and Terms of Service of their respective content sources.
