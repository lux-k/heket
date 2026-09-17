# Heket

![Heket log](web_assets/heket_logo_small.png)

Heket is a locally adaptive acoustic observation system for frogs and toads.

Heket listens continuously to an audio source, detects potential frog and toad calls, preserves the evidence, and lets you review what it heard. Corrections you make can be used to retrain the local model, allowing each Heket installation to become better adapted to its own species, microphone, and acoustic environment.

A new Heket can bootstrap its first model using community-contributed clip packs from TurtlePond.us. As you review and label recordings from your own site, local examples progressively replace that borrowed knowledge.

Heket runs locally. Internet-connected services such as TurtlePond.us and iNaturalist add capabilities, but aren't required for Heket's core monitoring and learning functions.

**Local first. Learn locally. Share deliberately.**

This part of the [Turtle Pond](https://turtlepond.us) suite.

---

## What it does

- Listens continuously to RTSP audio sources such as security cameras
- Detects and classifies candidate frog and toad calls
- Preserves audio evidence for review
- Lets you correct classifications and add your own labels
- Retrains models using recordings from your own site
- Bootstraps new installations using community clip packs
- Contributes selected labeled recordings back to TurtlePond.us
- Shares selected observations and audio with iNaturalist

Heket is designed around a simple loop:

**Listen → Detect → Review → Learn → Contribute or Share**

---

## Example output

![Heket screenshot](web_assets/screenshot.png)

---

## Before you start

You will need: a machine capable of running Heket, an RTSP audio source, and—if you want to bootstrap from community clips—an Internet connection.

Heket does **not** ship with a pretrained model. Your first model is built during setup from the clip packs you choose.

### Raspberry Pi

Heket has been tested on a Raspberry Pi 5 (2GB). We have the following recommendations:
- have active cooling for model training (14 minutes fan-less vs X minutes with fan for 9 clip packs)
- purchase the M.2 Hat+ and 2230 NVME storage for more reliable storage
- use the install script (see below)

The sample cost ($USD) and BOM for a Raspberry Pi 5 setup is below.

#### Minimum configuration
| Component | Description | Cost | 
| -------- | -------- | -------- |
| Raspberry Pi 5 (2GB) | Main compute | $65 |
| Raspberry Pi 27 Watt power supply | Powers the Pi via USB-C | $13 |
| Raspberry Pi case | Encloses and protects the Pi | $10 |
| 32GB micro SDHC card | Storage for recordings; less suitable for sustained writes | $25 |
| Total | | $113 |

#### Recommended configuration
| Component | Description | Cost | 
| -------- | -------- | -------- |
| Raspberry Pi 5 (2GB) | Main compute | $65 |
| Raspberry Pi 27 Watt power supply | Powers the Pi via USB-C | $13 |
| Raspberry Pi M.2 Hat+ | Allows the Pi to use NVME storage | $15 | 
| 64 GB or larger M.2 2230 NVMe SSD | Storage of recordings -- look for remaindered but new components | $25 | 
| Raspberry Pi case | Make sure it fits the Pi board + hat | $10 |
| RTC Battery for Raspberry Pi 5 | Allows the Pi to have accurate time without the network | $5 | 
| Raspberry Pi 5 fan | Reduces processor throttling during training | $10 |
| Total| | $143 |

### VM note

If running Heket on a VM (either via Docker or directly on the VM),  the CPU type matters. TensorFlow has strong opinions about what the CPU should look like. For Proxmox/QEMU, setting the CPU Type to host is recommended for single-host deployments. Other hypervisors might need similar configuration.

---

## Installation

### Using Docker Compose (easiest)

Go to where you keep your Docker files, e.g. /opt

Create a folder for Heket., e.g. ```mkdir heket```

Go into the folder, e.g. ```cd heket```

Create a data folder, e.g. ```mkdir heket-data```

Create a docker-compose file, e.g. ```nano docker-compose.yml```

docker-compose.yml:
```
services:
  heket:
    image: ghcr.io/lux-k/heket:latest
    container_name: heket
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - ./heket-data:/data:rw
```

Bring up the new container, e.g. ```docker compose up -d```

You should then be able to connect to the machine's IP on port 5000, e.g. http://192.168.100.10:5000. When you connect for the first time, you'll be asked for your RTSP source.

### Building your own container

Go to where to want the code to live.

Grab the source code, e.g. ```git pull https://github.com/lux-k/heket.git```

Create a data folder, e.g. ```mkdir heket-data```

Add this stanza to your docker-compose.yml:

```
  heket:
    container_name: heket
    restart: unless-stopped
    build:
      context: ./heket
      dockerfile: docker/dockerfile
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - ./heket-data:/data:rw
    ports:
      - "5000:5000"
```

Build and run the container, e.g. ```docker compose up heket --build ```

You should then be able to connect to the machine's IP on port 5000, e.g. http://192.168.100.10:5000. When you connect for the first time, you'll be asked for your RTSP source.

## With our install script (tested on a Pi)

Enter these two commands on the Pi's terminal.

```
curl -fsSL https://raw.githubusercontent.com/lux-k/heket/refs/heads/main/contrib/install.sh -o /tmp/heket-install.sh
sudo bash /tmp/heket-install.sh
```

You should verify the contents of the script before running it.

## venv / non-Docker setup

```bash
apt install git ffmpeg
cd /opt
python -m venv heket-env
source heket-env/bin/activate
git clone https://github.com/lux-k/heket
mkdir heket-data
ln -s heket-data heket/data
cd heket
pip install -r requirements.txt
python heket_pipeline.py
```

You should then be able to connect to the machine's IP on port 5000, e.g. http://192.168.100.10:5000. When you connect for the first time, you'll be asked for your RTSP source.

---

## Quickstart

Navigate to the Heket website, for example http://192.168.100.10:5000. A new installation should automatically direct you to the setup page.

Enter the RTSP URL for your camera or audio source, for example: rtsp://username:password@camera_hostname:554/h264Preview_01_sub

Click **Save**.

Heket now knows where to obtain audio, but a new installation does not include a prebuilt model. Before Heket can identify what it hears, you'll need to build its initial model.

Scroll to the bottom of the screen and click the **Settings** gear.

Under **Link to TurtlePond.us**, click **Reconnect** and confirm.

Heket will display a highlighted linking code. Make note of this code, then click the TurtlePond.us link. TurtlePond.us will open in a new tab.

Enter the linking code and click **Link**.

Close the TurtlePond.us tab and return to Heket. Click **Recheck the setup**. TurtlePond.us should now appear as linked.

Click **Download Clip Packs**.

Select clip packs appropriate for the frogs and toads you expect Heket to encounter. **Also select appropriate non-frog/noise packs.** You can select multiple packs. When finished, click **Add clip packs**.

Heket will download the selected community clips and use them to train an initial model for this installation. Notifications will show the progress of the download and training process.

When training finishes successfully, Heket will automatically begin using the new model. Your Heket is now ready to listen.

Clip packs can be added at any time. If Heket encounters a sound it doesn't understand well, check TurtlePond.us for a relevant community pack. Adding a pack gives Heket examples of that sound to use during future training; local examples can then progressively replace the community examples.

---

## Why

Frog calls don't happen in laboratory conditions. They happen alongside insects, birds, wind, traffic, machinery, dogs, rain, and other frogs.

A model trained somewhere else can provide a useful starting point, but it doesn't know your pond, your microphone, or your local acoustic environment.

Heket is designed to start with community knowledge and then learn locally. Review what it hears, correct it when it's wrong, and retrain. Over time, the model becomes increasingly based on recordings from the place where it actually listens.

**The community helps make Heket yours. You decide whether something from yours helps the community.**

---

## Events

Let's say you hear a frog croaking right now. Click the "Frog Calling" button in the top, right part of the user interface. This will create an event; essentially a window of sound clips in front of and behind the time you clicked the button. The idea is that you can verify
that the frog was heard and detected correctly. If not, you can relabel the appropriately clips so they'll be used when you rebuild the model later.

Additionally, there is an option to manually create an event. If, for example, you remember that at 9:45pm last night a frog was calling but you weren't near tech.

Event windows protect recordings from being deleted until the event itself is deleted.

---

## Teaching Heket your site

The initial model built during Quickstart is a starting point, not a finished classifier. Community clip packs contain recordings from other environments and equipment.

As Heket begins listening, review its detections. Correct classifications that are wrong and label useful recordings that Heket didn't understand correctly. Non-frog examples are important too: wind, insects, birds, traffic, machinery, and other sounds can all help Heket learn what not to classify as a frog.

Non-frog labels should begin with nonfrog_, for example nonfrog_wind or nonfrog_ambient.

When you have accumulated useful local labels, train a new model. Heket uses your local recordings along with community bootstrap clips.

As local recordings accumulate for a label, they replace community recordings used for that label. The community clips are scaffolding; the goal is for your Heket to increasingly learn from your site.

---

## Is Heket really frog-specific?

Heket itself contains little that inherently limits the acoustic learning system to frogs and toads. That's simply the problem it was built to solve. In principle, the same machinery could be trained against birds, insects, dogs, machinery—or your mother-in-law—given appropriate labeled recordings.

TurtlePond community data and the Heket user experience, however, are currently focused on frogs and toads.

---

## License

(TBD)
