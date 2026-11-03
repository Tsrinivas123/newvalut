/**
 * VidVault - Professional YouTube Video Downloader
 * Frontend Application Logic (Vanilla JavaScript)
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const videoUrlInput = document.getElementById("video-url-input");
  const btnAnalyze = document.getElementById("btn-analyze");
  const btnPaste = document.getElementById("btn-paste");
  const btnClear = document.getElementById("btn-clear");
  const alertBanner = document.getElementById("alert-banner");
  const alertText = document.getElementById("alert-text");
  const loadingIndicator = document.getElementById("loading-indicator");
  const videoResultSection = document.getElementById("video-result-section");
  const sampleChips = document.querySelectorAll(".sample-chip");
  const navStatus = document.getElementById("nav-status");
  const downloadToast = document.getElementById("download-toast");
  const downloadToastMsg = document.getElementById("download-toast-msg");
  const mobileMenuBtn = document.getElementById("mobile-menu-btn");
  const navLinks = document.getElementById("nav-links");

  // Format Tabs
  const tabVideo = document.getElementById("tab-video");
  const tabAudio = document.getElementById("tab-audio");
  const panelVideo = document.getElementById("panel-video");
  const panelAudio = document.getElementById("panel-audio");
  const videoGrid = document.getElementById("video-formats-grid");
  const audioGrid = document.getElementById("audio-formats-grid");
  const videoCountBadge = document.getElementById("video-count-badge");
  const audioCountBadge = document.getElementById("audio-count-badge");

  // Video Info Elements
  const videoThumb = document.getElementById("video-thumb");
  const videoDuration = document.getElementById("video-duration");
  const videoTitle = document.getElementById("video-title");
  const videoChannel = document.getElementById("video-channel");
  const videoViews = document.getElementById("video-views");
  const videoDate = document.getElementById("video-date");

  // State
  let currentVideoData = null;
  let backendHealth = null;

  // Regex pattern for client-side instant validation
  const YOUTUBE_REGEX = /^(https?:\/\/)?(www\.|m\.)?(youtube\.com|youtu\.be)\/(watch\?v=|embed\/|v\/|shorts\/)?([a-zA-Z0-9_-]{11})([&?].*)?$/;

  // =========================================================================
  // Health Check
  // =========================================================================
  async function checkBackendHealth() {
    try {
      const res = await fetch("/api/health");
      if (res.ok) {
        backendHealth = await res.json();
        if (navStatus) {
          const ffmpegBadge = backendHealth.ffmpeg_available ? " • FFmpeg Active" : "";
          navStatus.innerHTML = `<span class="status-dot"></span> Online${ffmpegBadge}`;
          navStatus.style.borderColor = "rgba(16, 185, 129, 0.4)";
          navStatus.style.color = "#34D399";
        }
      }
    } catch (err) {
      console.warn("Backend health check failed:", err);
      if (navStatus) {
        navStatus.innerHTML = `<span class="status-dot" style="background:#EF4444"></span> Connecting...`;
        navStatus.style.borderColor = "rgba(239, 68, 68, 0.4)";
        navStatus.style.color = "#F87171";
      }
    }
  }
  checkBackendHealth();

  // =========================================================================
  // UI Helpers: Alerts & Toasts
  // =========================================================================
  function showAlert(msg, type = "danger") {
    alertBanner.className = `alert-banner alert-${type}`;
    alertBanner.style.display = "flex";
    alertText.innerHTML = msg;
    alertBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function hideAlert() {
    alertBanner.style.display = "none";
    alertText.innerHTML = "";
  }

  function showToast(message, duration = 4500) {
    if (!downloadToast) return;
    downloadToastMsg.textContent = message;
    downloadToast.style.display = "flex";

    setTimeout(() => {
      downloadToast.style.display = "none";
    }, duration);
  }

  function formatNumber(num) {
    if (!num) return "0";
    return new Intl.NumberFormat().format(num);
  }

  // =========================================================================
  // Input Handling: Paste, Clear, Sample Chips
  // =========================================================================
  videoUrlInput.addEventListener("input", () => {
    const val = videoUrlInput.value.trim();
    btnClear.style.display = val.length > 0 ? "inline-flex" : "none";
    if (val.length === 0) {
      hideAlert();
    }
  });

  btnClear.addEventListener("click", () => {
    videoUrlInput.value = "";
    btnClear.style.display = "none";
    hideAlert();
    videoUrlInput.focus();
  });

  btnPaste.addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        videoUrlInput.value = text.trim();
        btnClear.style.display = "inline-flex";
        hideAlert();
        analyzeVideo();
      }
    } catch (err) {
      showAlert("Clipboard permission denied. Please paste the URL manually.", "warning");
    }
  });

  sampleChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const url = chip.getAttribute("data-url");
      if (url) {
        videoUrlInput.value = url;
        btnClear.style.display = "inline-flex";
        hideAlert();
        analyzeVideo();
      }
    });
  });

  // Mobile Menu Toggle
  if (mobileMenuBtn && navLinks) {
    mobileMenuBtn.addEventListener("click", () => {
      const isVisible = navLinks.style.display === "flex";
      navLinks.style.display = isVisible ? "none" : "flex";
      if (!isVisible) {
        navLinks.style.flexDirection = "column";
        navLinks.style.position = "absolute";
        navLinks.style.top = "72px";
        navLinks.style.left = "0";
        navLinks.style.right = "0";
        navLinks.style.background = "#080D18";
        navLinks.style.padding = "20px 24px";
        navLinks.style.borderBottom = "1px solid rgba(255, 255, 255, 0.1)";
      }
    });
  }

  // =========================================================================
  // Format Tabs Toggle
  // =========================================================================
  tabVideo.addEventListener("click", () => {
    tabVideo.classList.add("active");
    tabAudio.classList.remove("active");
    panelVideo.classList.add("active");
    panelAudio.classList.remove("active");
  });

  tabAudio.addEventListener("click", () => {
    tabAudio.classList.add("active");
    tabVideo.classList.remove("active");
    panelAudio.classList.add("active");
    panelVideo.classList.remove("active");
  });

  // =========================================================================
  // Analyze Video
  // =========================================================================
  async function analyzeVideo() {
    const rawUrl = videoUrlInput.value.trim();

    hideAlert();

    if (!rawUrl) {
      showAlert("Please enter a YouTube video URL first.", "warning");
      videoUrlInput.focus();
      return;
    }

    if (!YOUTUBE_REGEX.test(rawUrl)) {
      showAlert("Please enter a valid YouTube video link (e.g., https://www.youtube.com/watch?v=... or https://youtu.be/...)", "danger");
      return;
    }

    // Set loading state
    btnAnalyze.disabled = true;
    btnAnalyze.innerHTML = `
      <div class="spinner" style="width:20px;height:20px;border-width:2px;margin:0;"></div>
      <span>Analyzing Formats...</span>
    `;
    loadingIndicator.style.display = "block";
    videoResultSection.style.display = "none";

    try {
      const response = await fetch("/api/video-info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: rawUrl })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Failed to retrieve video information.");
      }

      currentVideoData = data;
      renderVideoResult(data);

      // Check if video duration warning is needed
      if (data.is_duration_exceeded) {
        const maxMins = data.max_duration_seconds ? Math.floor(data.max_duration_seconds / 60) : 30;
        showAlert(
          `⚠️ Note: This video is ${data.duration_formatted} long. Videos longer than ${maxMins} minutes exceed processing limits.`,
          "warning"
        );
      }

    } catch (err) {
      console.error("Error analyzing video:", err);
      showAlert(err.message || "An unexpected error occurred while communicating with the server.", "danger");
    } finally {
      btnAnalyze.disabled = false;
      btnAnalyze.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
        <span>Analyze Video</span>
      `;
      loadingIndicator.style.display = "none";
    }
  }

  btnAnalyze.addEventListener("click", analyzeVideo);

  videoUrlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      analyzeVideo();
    }
  });

  // =========================================================================
  // Render Video Results & Formats
  // =========================================================================
  function renderVideoResult(data) {
    videoThumb.src = data.thumbnail;
    videoDuration.textContent = data.duration_formatted;
    videoTitle.textContent = data.title;
    videoChannel.textContent = data.channel;
    videoViews.textContent = `${formatNumber(data.views)} views`;
    videoDate.textContent = data.upload_date ? `Published ${data.upload_date}` : "Available";

    // Badges count
    const videoFormats = data.video_formats || [];
    const audioFormats = data.audio_formats || [];
    videoCountBadge.textContent = videoFormats.length;
    audioCountBadge.textContent = audioFormats.length;

    // Render Video formats
    videoGrid.innerHTML = "";
    if (videoFormats.length === 0) {
      videoGrid.innerHTML = `
        <div style="grid-column: 1/-1; padding: 30px; text-align: center; color: var(--text-muted);">
          No direct video streams were discovered for this video.
        </div>
      `;
    } else {
      videoFormats.forEach((fmt) => {
        const card = createVideoFormatCard(fmt, data);
        videoGrid.appendChild(card);
      });
    }

    // Render Audio formats
    audioGrid.innerHTML = "";
    if (audioFormats.length === 0) {
      audioGrid.innerHTML = `
        <div style="grid-column: 1/-1; padding: 30px; text-align: center; color: var(--text-muted);">
          No separate audio streams were discovered for this video.
        </div>
      `;
    } else {
      audioFormats.forEach((fmt) => {
        const card = createAudioFormatCard(fmt, data);
        audioGrid.appendChild(card);
      });
    }

    // Reveal section & scroll into view smoothly
    videoResultSection.style.display = "block";
    videoResultSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function createVideoFormatCard(fmt, videoData) {
    const card = document.createElement("div");
    card.className = "format-card";

    const isHD = fmt.height >= 720;
    const badgeClass = isHD ? "badge-hd" : "badge-sd";
    const badgeLabel = fmt.is_progressive ? "Direct MP4" : (isHD ? "HD Stream" : "SD Stream");

    card.innerHTML = `
      <div class="format-card-header">
        <div>
          <div class="format-quality">${fmt.resolution}</div>
          <span style="font-size:0.78rem; color:var(--text-muted);">${fmt.ext.toUpperCase()} • ${fmt.vcodec}</span>
        </div>
        <span class="format-badge ${badgeClass}">${badgeLabel}</span>
      </div>

      <div class="format-details">
        <div class="detail-row">
          <span class="detail-label">File Size:</span>
          <span class="detail-val">${fmt.filesize_formatted}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Audio:</span>
          <span class="detail-val" style="color: ${fmt.has_audio ? 'var(--color-success)' : 'var(--text-muted)'};">
            ${fmt.has_audio ? "✓ Included" : (fmt.supported ? "✓ Auto-Muxed" : "Video Only")}
          </span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Type:</span>
          <span class="detail-val" style="font-size:0.75rem;">${fmt.note}</span>
        </div>
      </div>

      <button class="btn-download" data-format-id="${fmt.format_id}" data-ext="${fmt.ext}">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="7 10 12 15 17 10"></polyline>
          <line x1="12" y1="15" x2="12" y2="3"></line>
        </svg>
        <span>Download ${fmt.resolution}</span>
      </button>
    `;

    const downloadBtn = card.querySelector(".btn-download");
    downloadBtn.addEventListener("click", () => {
      triggerDownload(videoData, fmt.format_id, fmt.ext, `${fmt.resolution} Video`, downloadBtn);
    });

    return card;
  }

  function createAudioFormatCard(fmt, videoData) {
    const card = document.createElement("div");
    card.className = "format-card";

    card.innerHTML = `
      <div class="format-card-header">
        <div>
          <div class="format-quality">${fmt.bitrate}</div>
          <span style="font-size:0.78rem; color:var(--text-muted);">${fmt.ext.toUpperCase()} • ${fmt.acodec}</span>
        </div>
        <span class="format-badge badge-audio">${fmt.ext.toUpperCase()}</span>
      </div>

      <div class="format-details">
        <div class="detail-row">
          <span class="detail-label">File Size:</span>
          <span class="detail-val">${fmt.filesize_formatted}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Format:</span>
          <span class="detail-val">${fmt.acodec.toUpperCase()} Audio</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Processing:</span>
          <span class="detail-val" style="font-size:0.75rem;">${fmt.note}</span>
        </div>
      </div>

      <button class="btn-download" data-format-id="${fmt.format_id}" data-ext="${fmt.ext}">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="7 10 12 15 17 10"></polyline>
          <line x1="12" y1="15" x2="12" y2="3"></line>
        </svg>
        <span>Download Audio</span>
      </button>
    `;

    const downloadBtn = card.querySelector(".btn-download");
    downloadBtn.addEventListener("click", () => {
      triggerDownload(videoData, fmt.format_id, fmt.ext, `${fmt.bitrate} Audio`, downloadBtn);
    });

    return card;
  }

  // =========================================================================
  // Download Processing
  // =========================================================================
  async function triggerDownload(videoData, formatId, ext, qualityLabel, buttonEl) {
    if (videoData.is_duration_exceeded) {
      const maxMins = videoData.max_duration_seconds ? Math.floor(videoData.max_duration_seconds / 60) : 30;
      showAlert(`Cannot download: Video duration (${videoData.duration_formatted}) exceeds the ${maxMins}-minute processing limit.`, "danger");
      return;
    }

    const originalText = buttonEl.innerHTML;
    buttonEl.disabled = true;
    buttonEl.innerHTML = `
      <div class="spinner" style="width:16px;height:16px;border-width:2px;margin:0;"></div>
      <span>Processing...</span>
    `;

    showToast(`⏳ Preparing download for "${videoData.title.slice(0, 35)}..." (${qualityLabel})`);

    // Build API download URL with clean params
    const rawUrl = videoUrlInput.value.trim();
    const downloadUrl = `/api/download?url=${encodeURIComponent(rawUrl)}&format_id=${encodeURIComponent(formatId)}&ext=${encodeURIComponent(ext)}&title=${encodeURIComponent(videoData.title)}`;

    try {
      const res = await fetch(downloadUrl);
      if (!res.ok) {
        let errorMsg = `Download failed with HTTP ${res.status}`;
        try {
          const errData = await res.json();
          if (errData && errData.error) {
            errorMsg = errData.error;
          }
        } catch (_) {}
        showAlert(errorMsg, "danger");
        return;
      }

      const blob = await res.blob();
      const contentDisposition = res.headers.get("Content-Disposition");
      let filename = `${videoData.title.slice(0, 40)}.${ext}`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)["']?/i);
        if (match && match[1]) {
          filename = decodeURIComponent(match[1]);
        }
      }

      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);

      showToast(`✓ Download started! Saved as ${filename}`);
    } catch (err) {
      showAlert(`Download error: ${err.message || "Failed to communicate with server."}`, "danger");
    } finally {
      buttonEl.disabled = false;
      buttonEl.innerHTML = originalText;
    }
  }

  // =========================================================================
  // FAQ Accordion
  // =========================================================================
  const faqItems = document.querySelectorAll(".faq-item");
  faqItems.forEach((item) => {
    const trigger = item.querySelector(".faq-trigger");
    const content = item.querySelector(".faq-content");

    trigger.addEventListener("click", () => {
      const isOpen = item.classList.contains("open");

      // Close all others
      faqItems.forEach((other) => {
        if (other !== item) {
          other.classList.remove("open");
          const otherContent = other.querySelector(".faq-content");
          if (otherContent) otherContent.style.maxHeight = null;
        }
      });

      // Toggle current
      if (isOpen) {
        item.classList.remove("open");
        content.style.maxHeight = null;
      } else {
        item.classList.add("open");
        content.style.maxHeight = content.scrollHeight + "px";
      }
    });
  });
});

