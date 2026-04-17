# Heket

![Heket log](web_assets/heket_logo_small.png)

Acoustic detection of frog calls from continuous audio streams.

---

## What it does

- Listens to live RTSP streams (likely from security cameras)
- Detects candidate frog calls
- Stores and presents detections
- Provides simple playback of events
- Allows retraining of the model for improved accuracy

---

## Example output

---

![Heket screenshot](web_assets/screenshot.png)


## Current state

This is an early project.

- Designed to run locally
- Flask-based web interface
- Focused on simplicity over completeness

It is only (poorly) trained on a few frogs: American bullfrog, grey tree frog, Fowler's toad and green frogs. You will need to expand and enhance your model to tune it for your yard. (See below)

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

## Docker setup

Go to where ever you keep your Docker files, e.g. /opt

docker-compose.yml
```
services:
  heket:
    container_name: heket
    restart: unless-stopped
    build: ./heket
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - ./heket-data:/data:rw
    ports:
      - "5000:5000"
```

Make a Heket container folder and a Heket data directory. Grab the code.
```
mkdir heket
cd heket
git pull https://github.com/lux-k/heket
ln -s ./heket/docker/dockerfile dockerfile
```

Configure the basics for Heket
```
echo "HEKET_DATA_DIR=/data" >> .env
echo "HEKET_RTSP_URL=rtsp://admin:password@camera:554/h264Preview_01_sub" >> .env
```

Build the container and bring it up. Due to the deps, this may take a few minutes.
```
docker compose up heket --build
```

---

## Why

Most detection systems assume ideal input.

Heket is built to work in noisy, real-world conditions:
- wind
- traffic
- overlapping species

If it works here, it can work anywhere.

---

## Tuning

As mentioned, this model is trained on a very small number of frog samples. Those frogs may or may not be present in your yard and may not sound the same with your environment (yard noise, microphone, etc.) Because of this, tuning is required.

Run the base system for a little while.. a few hours or so. See how the output looks. In particular, if you HEAR frogs, make note of the time so you can find those clips. 

You will start by listening to the clips in the "Iffy" column. If the clip is a frog, label it as such (select it from the dropdown, click the label button). If you need to add labels, there is a spot on the interface for adding them.

Of note, non frog labels are also important. Things like the wind, dogs, etc. could be labeled frogs. Just make sure that "nonfrogs" have a label name prefix of of "nonfrog_", e.g. "nonfrog_wind".

After you classify some clips, hit the training button. This will instruct the model to relearn the sounds based on your labels. Give it a little time to do so. You should then be able to hit the "reload" button on the custom models and see a recently created model.

Click on the new model to switch to using it. This will classify new clips using your refined model.

---

## Of note

There is no inherent tuning done on the audio to make this a "frog/toad only" system -- that was just the use case I had in mind when I built it. You could, conceivably, train Heket to listen to birds, insects, dogs, your mother-in-law as long as you use the system to
label clips.

---

## License

(TBD)
