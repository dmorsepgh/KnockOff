#!/usr/bin/env python3
"""
KnockOff News Dashboard - Live rendering progress monitor.

Opens a browser dashboard showing active jobs, progress, and recent output.

Usage:
    python tools/dashboard.py
"""

import re
import glob
import subprocess
import time
from pathlib import Path
from datetime import datetime
from flask import Flask, jsonify, render_template_string

PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
OUTPUT_DIR = PROJECT_ROOT / ".tmp" / "avatar" / "output"
KEEPERS_DIR = PROJECT_ROOT / "output" / "keepers"

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>KnockOff News — Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0d0d1a;
            color: #e0e0e0;
            font-family: -apple-system, 'Helvetica Neue', sans-serif;
            padding: 20px;
        }
        h1 {
            color: #cc0000;
            font-size: 28px;
            margin-bottom: 5px;
        }
        .subtitle {
            color: #666;
            font-size: 14px;
            margin-bottom: 30px;
        }
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: #1a1a2e;
            border-radius: 10px;
            padding: 20px;
            border: 1px solid #2a2a3e;
        }
        .card h2 {
            color: #cc0000;
            font-size: 16px;
            margin-bottom: 15px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .progress-bar {
            background: #2a2a3e;
            border-radius: 5px;
            height: 24px;
            margin: 10px 0;
            overflow: hidden;
            position: relative;
        }
        .progress-fill {
            background: linear-gradient(90deg, #cc0000, #ff4444);
            height: 100%;
            border-radius: 5px;
            transition: width 0.5s ease;
        }
        .progress-text {
            position: absolute;
            top: 3px;
            left: 10px;
            font-size: 12px;
            font-weight: bold;
            color: white;
            text-shadow: 0 1px 2px rgba(0,0,0,0.5);
        }
        .status { font-size: 14px; line-height: 1.8; }
        .status .label { color: #888; }
        .status .value { color: #fff; font-weight: bold; }
        .active { color: #44ff44; }
        .idle { color: #888; }
        .log-line {
            font-family: 'SF Mono', 'Menlo', monospace;
            font-size: 11px;
            color: #aaa;
            padding: 2px 0;
            border-bottom: 1px solid #1a1a2e;
        }
        .log-line .time { color: #666; }
        .log-line .info { color: #4488ff; }
        .log-line .warn { color: #ffaa00; }
        .log-line .err { color: #ff4444; }
        .recent-videos {
            list-style: none;
        }
        .recent-videos li {
            padding: 8px 0;
            border-bottom: 1px solid #2a2a3e;
            font-size: 13px;
        }
        .recent-videos .filename { color: #4488ff; }
        .recent-videos .meta { color: #666; font-size: 11px; }
        .stat-number {
            font-size: 36px;
            font-weight: bold;
            color: #fff;
        }
        .stat-label {
            font-size: 12px;
            color: #888;
            text-transform: uppercase;
        }
        .stats-row {
            display: flex;
            gap: 30px;
            margin-bottom: 10px;
        }
        .stat-box { text-align: center; }
        .pulse {
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #44ff44;
            border-radius: 50%;
            animation: pulse 1.5s infinite;
            margin-right: 6px;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        .full-width { grid-column: 1 / -1; }
    </style>
</head>
<body>
    <h1>KNOCKOFF NEWS</h1>
    <div class="subtitle">Production Dashboard — Fair. Balanced. Completely Made Up.</div>

    <div class="grid">
        <div class="card">
            <h2>Active Jobs</h2>
            <div id="active-jobs"><span class="idle">Checking...</span></div>
        </div>

        <div class="card">
            <h2>Stats</h2>
            <div id="stats" class="stats-row"></div>
        </div>

        <div class="card">
            <h2>Recent Output</h2>
            <ul id="recent-videos" class="recent-videos"></ul>
        </div>

        <div class="card">
            <h2>Cast</h2>
            <div id="cast" style="font-size: 13px; line-height: 1.8;"></div>
        </div>

        <div class="card full-width">
            <h2>Live Log</h2>
            <div id="log-feed" style="max-height: 300px; overflow-y: auto;"></div>
        </div>
    </div>

    <script>
        function update() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    // Active jobs
                    let jobsHtml = '';
                    if (data.active_jobs.length === 0) {
                        jobsHtml = '<span class="idle">No active renders</span>';
                    } else {
                        data.active_jobs.forEach(job => {
                            jobsHtml += `
                                <div class="status">
                                    <span class="pulse"></span>
                                    <span class="value active">${job.name}</span><br>
                                    <span class="label">Step:</span> <span class="value">${job.step}</span><br>
                                    <span class="label">Progress:</span> <span class="value">${job.progress}</span>
                                </div>
                                <div class="progress-bar">
                                    <div class="progress-fill" style="width: ${job.percent}%"></div>
                                    <div class="progress-text">${job.percent}%</div>
                                </div>
                            `;
                        });
                    }
                    document.getElementById('active-jobs').innerHTML = jobsHtml;

                    // Stats
                    document.getElementById('stats').innerHTML = `
                        <div class="stat-box">
                            <div class="stat-number">${data.stats.total_videos}</div>
                            <div class="stat-label">Videos</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number">${data.stats.total_size}</div>
                            <div class="stat-label">Total Size</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number">${data.stats.cast_count}</div>
                            <div class="stat-label">Cast</div>
                        </div>
                    `;

                    // Recent videos
                    let vidHtml = '';
                    data.recent_videos.forEach(v => {
                        vidHtml += `<li>
                            <span class="filename">${v.name}</span><br>
                            <span class="meta">${v.size} · ${v.time}</span>
                        </li>`;
                    });
                    document.getElementById('recent-videos').innerHTML = vidHtml;

                    // Cast
                    document.getElementById('cast').innerHTML = data.cast;

                    // Log
                    let logHtml = '';
                    data.log_lines.forEach(l => {
                        let cls = 'info';
                        if (l.includes('WARNING')) cls = 'warn';
                        if (l.includes('ERROR')) cls = 'err';
                        logHtml += `<div class="log-line"><span class="${cls}">${l}</span></div>`;
                    });
                    document.getElementById('log-feed').innerHTML = logHtml;
                    // Auto scroll to bottom
                    const logFeed = document.getElementById('log-feed');
                    logFeed.scrollTop = logFeed.scrollHeight;
                });
        }

        update();
        setInterval(update, 3000);  // Refresh every 3 seconds
    </script>
</body>
</html>
"""

CAST_ROSTER = {
    "CNN": ["Anderson Cooper", "Jake Tapper"],
    "MSNBC": ["Rachel Maddow", "Mika Brzezinski", "Joe Scarborough", "Lawrence O'Donnell", "Jonathan Capehart", "Eugene Daniels"],
    "Fox News": ["Sean Hannity", "Tucker Carlson", "Laura Ingraham", "Bill O'Reilly"],
    "NBC": ["Lester Holt"],
    "ESPN": ["Stephen A. Smith"],
    "NewsNation": ["Leland Vittert", "Chris Cuomo"],
}


def get_active_jobs():
    """Detect active rendering jobs by checking running processes + log files."""
    jobs = []

    # Check for running processes first — most reliable signal
    try:
        ps_result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True
        )
        ps_output = ps_result.stdout
    except Exception:
        ps_output = ""

    active_processes = {}
    if "news_desk.py" in ps_output:
        active_processes["newsdesk"] = "News Desk"
    if "zoom_call.py" in ps_output:
        active_processes["zoom"] = "Zoom Call"
    if "quick_video.py" in ps_output:
        active_processes["quick"] = "Quick Video"
    if "cast_intro.py" in ps_output:
        active_processes["cast"] = "Cast Intro"
    if "cast_shorts.py" in ps_output:
        active_processes["shorts"] = "Shorts"

    # Also check if Wav2Lip/inference is running
    wav2lip_active = "inference.py" in ps_output

    today = datetime.now().strftime("%Y%m%d")

    for key, job_name in active_processes.items():
        # Find matching log file
        log_file = LOG_DIR / f"{key}_{today}.log"
        if not log_file.exists():
            # Try alternate names
            for alt in ["newsdesk_", "zoom_", "quick_", "knockoff_"]:
                alt_file = LOG_DIR / f"{alt}{today}.log"
                if alt_file.exists() and key in alt:
                    log_file = alt_file
                    break

        step = "Starting..."
        progress = ""
        percent = 5
        total_lines = 0
        current_line = 0

        if log_file.exists():
            lines = log_file.read_text().strip().split('\n')

            for l in lines:
                if "TTS line" in l or "TTS complete" in l:
                    step = "TTS"
                    percent = 8
                if "TTS complete" in l:
                    m = re.search(r'for (.+?)s of audio', l)
                    step = "Wav2Lip"
                    percent = 10
                if "Lip-syncing line" in l:
                    m = re.search(r'line (\d+)/(\d+)', l)
                    if m:
                        current_line = int(m.group(1))
                        total_lines = int(m.group(2))
                        step = "Wav2Lip"
                        percent = int((current_line / total_lines) * 75) + 10
                        progress = f"Line {current_line}/{total_lines}"
                if "Wav2Lip complete" in l:
                    step = "Assembly"
                    percent = 88
                    progress = "Compositing video"
                if "Adding broadcast" in l or "Adding bumper" in l:
                    step = "Broadcast Package"
                    percent = 92
                    progress = "Adding intro/outro"
                if "BROADCAST COMPLETE" in l or "COMPLETE" in l:
                    step = "Done"
                    percent = 100

        # If wav2lip is actively running and we're in that step, show it
        if wav2lip_active and step == "Wav2Lip" and not progress:
            progress = "Lip syncing in progress..."

        if percent < 100:
            jobs.append({
                "name": job_name,
                "step": step,
                "progress": progress or "Processing...",
                "percent": percent,
            })

    return jobs


def get_recent_videos(limit=8):
    """Get most recent output videos."""
    videos = []
    patterns = [
        str(OUTPUT_DIR / "*.mp4"),
        str(KEEPERS_DIR / "**" / "*.mp4"),
    ]
    all_files = []
    for p in patterns:
        all_files.extend(glob.glob(p, recursive=True))

    all_files.sort(key=lambda x: Path(x).stat().st_mtime, reverse=True)

    for f in all_files[:limit]:
        p = Path(f)
        size = p.stat().st_size
        if size > 1024 * 1024:
            size_str = f"{size / 1024 / 1024:.1f} MB"
        else:
            size_str = f"{size / 1024:.0f} KB"
        mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%I:%M %p")
        videos.append({
            "name": p.name,
            "size": size_str,
            "time": mtime,
        })

    return videos


def get_stats():
    """Get overall stats."""
    all_videos = list(OUTPUT_DIR.glob("*.mp4")) + list(KEEPERS_DIR.rglob("*.mp4"))
    total_size = sum(f.stat().st_size for f in all_videos)
    if total_size > 1024 * 1024 * 1024:
        size_str = f"{total_size / 1024 / 1024 / 1024:.1f}G"
    else:
        size_str = f"{total_size / 1024 / 1024:.0f}M"

    return {
        "total_videos": len(all_videos),
        "total_size": size_str,
        "cast_count": 16,
    }


def get_log_lines(limit=30):
    """Get recent log lines from today's logs."""
    today = datetime.now().strftime("%Y%m%d")
    lines = []
    for log_pattern in ["newsdesk_", "zoom_", "quick_", "knockoff_"]:
        log_file = LOG_DIR / f"{log_pattern}{today}.log"
        if log_file.exists():
            file_lines = log_file.read_text().strip().split('\n')
            lines.extend(file_lines[-50:])

    # Sort by timestamp and take most recent
    lines.sort()
    return lines[-limit:]


def get_cast_html():
    """Generate cast roster HTML."""
    html = ""
    for network, hosts in CAST_ROSTER.items():
        html += f"<strong style='color:#cc0000'>{network}:</strong> "
        html += ", ".join(hosts)
        html += "<br>"
    return html


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/api/status')
def status():
    return jsonify({
        "active_jobs": get_active_jobs(),
        "recent_videos": get_recent_videos(),
        "stats": get_stats(),
        "log_lines": get_log_lines(),
        "cast": get_cast_html(),
    })


if __name__ == "__main__":
    import webbrowser
    import threading

    print("\n" + "=" * 50)
    print("  KNOCKOFF NEWS — Production Dashboard")
    print("  http://localhost:5555")
    print("=" * 50 + "\n")

    # Open browser after a short delay
    threading.Timer(1.0, lambda: webbrowser.open("http://localhost:5555")).start()

    app.run(host="0.0.0.0", port=5555, debug=False)
