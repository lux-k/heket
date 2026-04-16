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
apt install git ffmpeg
cd /opt
python -m venv heket-env
source heket-env/bin/activate
git clone https://github.com/lux-k/heket
cd heket
pip install -r requirements.txt
echo "HEKET_RTSP_URL=rtsp://admin:password@192.168.100.1:554/stream" > .env
python heket_pipeline.py
```

You should then be able to connect to the machine's IP on port 5000, e.g. http://192.168.100.10:5000

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
