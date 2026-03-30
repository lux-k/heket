# Heket

Acoustic detection of frog calls from continuous audio streams.

---

## What it does

- Listens to live or recorded audio
- Detects candidate frog calls
- Stores and presents detections
- Provides simple playback of events

---

## Current state

This is an early MVP.

- Designed to run locally
- Flask-based web interface
- Focused on simplicity over completeness

---

## Quick start

```bash
apt install ffmpeg
cd /opt
python -m venv heket
cd heket
source bin/activate
pip install -r requirements.txt
python heket_pipeline.py &
python heket_web.py
```
---

## Example output

See: https://turtlepond.us/heket/

---

## Why

Most detection systems assume ideal input.

Heket is built to work in noisy, real-world conditions:
- wind
- traffic
- overlapping species

If it works here, it can work anywhere.

---

## License

(TBD)
