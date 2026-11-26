# CGOLD VERSE V2
Local-first audio transcription. Demucs separates vocals before FFmpeg pitch-preserving tempo adjustment and faster-whisper transcription. Optional original comparison, noise reduction, normalization, waveform selection, microphone recording and exports.

## Ubuntu setup
Use Python 3.11. Install FFmpeg (`sudo apt install ffmpeg`) and Python venv support. Open a terminal in this extracted folder:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Open http://127.0.0.1:8000. First run downloads model weights; allow several GB of disk and RAM. Start with a 15-second clip and base model. CPU inference may be slow. Microphone requires localhost or HTTPS. Audio is processed on the server, not in the browser. Temporary files are deleted after requests. Only process audio you have permission to use.

## GitHub upload
From this folder (not the old project folder), after confirming the remote is empty:

```sh
git init -b main
git add .
git commit -m "Build CGOLD Verse V2"
git remote add origin https://github.com/promzycgold-code/CGOLD-VERSE-V2.git
git push -u origin main
```
If the remote already contains commits, do not force push; reconcile first.

## Deployment
Dockerfile provides a single-service container. Build with `docker build -t cgold-verse .` and run `docker run --rm -p 127.0.0.1:8000:8000 cgold-verse`. Public deployment requires authentication, upstream upload limits, rate limiting, HTTPS, sufficient compute and persistent model cache. Do not expose this unauthenticated local prototype publicly. Static hosting alone cannot run Demucs. Request processing is synchronous; production should use a job queue.

## Tests and limitations
Run `python -m unittest discover -s tests` after installing dependencies. `node --check static/app.js` checks JavaScript syntax. Real model inference, browser microphone and deployment must be tested separately. Isolation may remove or distort vocals. Slowing audio does not guarantee accuracy. Comparison is side-by-side, not automatic correction. Subtitle exports reflect original timestamped segments, not edits to the plain-text editor. Maximum upload 100 MB and selected duration 10 minutes. No account system or cloud history.

## Upgrade: local jobs and drafts
Run with a single Uvicorn worker. Job progress is approximate (stage milestones and Whisper segment timestamps). Cancellation interrupts FFmpeg/Demucs subprocesses and checks between Whisper segments; model loading may delay cancellation. Draft history is browser-local, text-only, up to 20 entries; clear it on shared devices. Word confidence is a model estimate, not a correctness guarantee. Job results are in memory and expire on subsequent job creation after 30 minutes. Public deployment requires authentication, resource limits and durable job management. Existing synchronous API remains available.
