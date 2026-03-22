const express = require('express');
const { execSync, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = 3100;

const KNOCKOFF_DIR = path.join(__dirname, '..');
const AVATARS_DIR = path.join(KNOCKOFF_DIR, 'avatars');
const PIPER_DIR = path.join(KNOCKOFF_DIR, 'models', 'piper');
const OUTPUT_DIR = path.join(KNOCKOFF_DIR, '.tmp', 'avatar', 'output');

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// List available avatars
app.get('/api/avatars', (req, res) => {
  const avatars = fs.readdirSync(AVATARS_DIR)
    .filter(f => f.endsWith('.mp4'))
    .map(f => f.replace('.mp4', ''));
  res.json(avatars);
});

// List available voices
app.get('/api/voices', (req, res) => {
  const voices = fs.readdirSync(PIPER_DIR)
    .filter(f => f.endsWith('.onnx'))
    .map(f => f.replace('.onnx', '').replace('en_US-', '').replace('-medium', ''));
  res.json(voices);
});

// Generate script via Ollama
app.post('/api/generate-script', async (req, res) => {
  const { topic, length } = req.body;

  const wordCount = {
    '30s': 75,
    '60s': 150,
    '90s': 225,
    '2m': 300,
    '3m': 450
  }[length] || 150;

  const prompt = `Write a video narration script about: ${topic}

Requirements:
- Exactly ${wordCount} words (for a ${length} video)
- Conversational, natural speaking tone
- Use contractions (don't, can't, you'll)
- Start with a hook that grabs attention
- End with "Visit dmpgh.com for more tips and guides"
- No stage directions, no [brackets], just the spoken words
- No title or headers, just the script text

Write ONLY the narration text, nothing else.`;

  try {
    const response = await fetch('http://localhost:11434/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'llama3.1:8b',
        prompt: prompt,
        stream: false
      })
    });
    const data = await response.json();
    res.json({ script: data.response.trim() });
  } catch (err) {
    res.status(500).json({ error: 'Failed to generate script: ' + err.message });
  }
});

// Job tracking
const jobs = {};

// Generate video via KnockOff (async job)
app.post('/api/generate-video', (req, res) => {
  const { script, avatar, voice } = req.body;

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const jobId = timestamp;
  const scriptFile = path.join(KNOCKOFF_DIR, '.tmp', `script-${timestamp}.txt`);

  fs.mkdirSync(path.dirname(scriptFile), { recursive: true });
  fs.writeFileSync(scriptFile, script);

  jobs[jobId] = { status: 'rendering', log: '', startTime: Date.now() };

  // Return immediately with job ID
  res.json({ jobId, status: 'rendering' });

  // Run in background
  const cmd = `cd /Users/douglasmorse/KnockOff && /opt/homebrew/bin/python3.12 tools/generate_avatar_video.py --script "${scriptFile}" --avatar ${avatar} --voice ${voice} 2>&1`;
  console.log('Running:', cmd);
  const child = spawn('bash', ['-c', cmd]);

  child.stdout.on('data', (data) => { jobs[jobId].log += data.toString(); });
  child.stderr.on('data', (data) => { jobs[jobId].log += data.toString(); });

  child.on('close', () => {
    const match = jobs[jobId].log.match(/Video generated: (.+\.mp4)/);
    if (match) {
      const videoName = path.basename(match[1]);
      jobs[jobId].status = 'complete';
      jobs[jobId].video = `/api/video/${videoName}`;
      jobs[jobId].duration = Math.round((Date.now() - jobs[jobId].startTime) / 1000);

      // Copy to NAS via SSH (no SCP on NAS)
      const nasCmd = `ssh nas "mkdir -p /var/services/homes/dmpgh/videos/knockoff" && cat "${match[1]}" | ssh nas "cat > /var/services/homes/dmpgh/videos/knockoff/${videoName}"`;
      spawn('bash', ['-c', nasCmd]).on('close', (rc) => {
        if (rc === 0) console.log(`Video copied to NAS: ${videoName}`);
        else console.log(`NAS copy failed for: ${videoName}`);
      });
    } else {
      jobs[jobId].status = 'failed';
      jobs[jobId].error = 'Video generation failed';
    }
  });
});

// Check job status
app.get('/api/job/:jobId', (req, res) => {
  const job = jobs[req.params.jobId];
  if (!job) return res.status(404).json({ error: 'Job not found' });
  const elapsed = Math.round((Date.now() - job.startTime) / 1000);
  res.json({ ...job, elapsed });
});

// Serve generated videos
app.get('/api/video/:filename', (req, res) => {
  const videoPath = path.join(OUTPUT_DIR, req.params.filename);
  if (fs.existsSync(videoPath)) {
    res.sendFile(videoPath);
  } else {
    res.status(404).json({ error: 'Video not found' });
  }
});

// List generated videos
app.get('/api/videos', (req, res) => {
  if (!fs.existsSync(OUTPUT_DIR)) return res.json([]);
  const videos = fs.readdirSync(OUTPUT_DIR)
    .filter(f => f.endsWith('.mp4'))
    .map(f => ({
      name: f,
      url: `/api/video/${f}`,
      size: fs.statSync(path.join(OUTPUT_DIR, f)).size,
      created: fs.statSync(path.join(OUTPUT_DIR, f)).mtime
    }))
    .sort((a, b) => b.created - a.created);
  res.json(videos);
});

app.listen(PORT, () => {
  console.log(`KnockOff Video Generator running at http://localhost:${PORT}`);
});
