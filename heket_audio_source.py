from abc import ABC, abstractmethod
from typing import BinaryIO
from io import BytesIO
import json
import os
import re
import subprocess
from pathlib import Path
import time
import select
import signal

class AudioSource(ABC):
    def configuration() -> dict:
        return {
            "name": {
                "type": "text",
                "label": "Name",
                "required": True,
            },
            "enabled": {
                "type": "checkbox",
                "label": "Enabled",
                "required": False,
            },
            "latitude": {
                "type": "text",
                "label": "Latitude",
                "required": True,
            },
            "longitude": {
                "type": "text",
                "label": "Longitude",
                "required": True,
            },
        }

class RTSPAudioSource(AudioSource):

    def __init__(self, bucket, endpoint_url, access_key_id, secret_access_key, region: str, base=""):
        self.bucket = bucket
        self.base = base
        print(f"RTSP client store using {endpoint_url}")

    def configuration() -> dict:
        return AudioSource.configuration() | {
            "endpoint_url": {
                "type": "text",
                "label": "Endpoint URL RTSP",
                "required": True,
            },
            "sr": {
                "type": "text",
                "label": "Sample Rate (hz)",
                "required": True,
                "coerce": int
            },
            "segment_length": {
                "type": "text",
                "label": "Segment Length (s)",
                "required": True,
                "coerce": float
            },
        }    

class ALSAAudioSource(AudioSource):

    def __init__(self, bucket, endpoint_url, access_key_id, secret_access_key, region: str, base=""):
        self.bucket = bucket
        self.base = base
        print(f"ALSA client store using {endpoint_url}")

    def configuration() -> dict:
        return AudioSource.configuration() | {
            "hw_addr": {
                "type": "select",
                "label": "ALSA Device",
                "required": True,
                "options": [ {"name": d["name"], "value": d["physical_path"]} for d in ALSAAudioSource.enumerate_recording_sources()]
            },
            "sr": {
                "type": "text",
                "label": "Sample Rate (hz)",
                "required": True,
                "coerce": int
            },
            "segment_length": {
                "type": "text",
                "label": "Segment Length (s)",
                "required": True,
                "coerce": float
            },
        }

    def enumerate_recording_sources():
        files = os.listdir("/sys/class/sound")

        sources = []
        for f in sorted(files):
            #step 1... look at the sound cards in sysfs... grab the names
            match = re.search(r"^card(\d+)$", f)
            if match:
                try:
                    result = subprocess.run(['udevadm','info','--query=property','/sys/class/sound/' + f], capture_output=True, text=True)
                    results = {"card_name": f, "card_number": match.group(1)}
                except:
                    continue
            else:
                #print(f, "is not a candidate card")
                continue

            #step 2... grab the physical location of the cards
            match = re.search(r"DEVPATH=(\S+)/sound/card\d+", result.stdout)
            if match:
                results["physical_path"] = match.group(1)
            else:
                print("Could not find a devpath for ",  f)
                continue

            #step 3... grab the capture subsevices
            attrs = os.listdir("/sys/class/sound/"+f)
            results["capture_devices"] = []
            for a in sorted(attrs):
                match = re.search(r"^pcmC\d+D(\d+)c$", a)
                if match:
                    results["capture_devices"].append(match.group(1))

            if len(results["capture_devices"]) == 0:
                print("No capture subdevices found for", f)
                continue

            dev = Path("/dev/snd/pcmC"+results["card_number"]+"D"+results["capture_devices"][0]+"c")
            if dev.exists() or True:
                results["dev"] = str(dev)
                results["alsa_device"] = "plughw:" + results["card_number"] + "," + results["capture_devices"][0]
            else:
                print("No /dev devices found for", f)
                pass #continue

            name = ""
            id = Path("/proc/asound/" + results["card_name"] + "/id")
            if id.exists():
                with id.open("r", encoding="utf-8") as file:
                    name = file.readline().rstrip('\n')

            stream = Path("/proc/asound/" + results["card_name"] + "/stream0")
            if stream.exists():
                with stream.open("r", encoding="utf-8") as file:
                    first_line = file.readline()
                    match = re.search(r"^(.+) at ", first_line)
                    if match:
                        if len(name) > 0:
                            name += " - "
                        name +=  match.group(1)
            results["name"] = name

            #if "name" in results and "dev" in results and len(results["capture_devices"]) > 0:
            sources.append(results)
        return sources

    def physical_path_to_alsa(path):
        devs = ALSAAudioSource.enumerate_recording_sources()
        for d in devs:
            if d["physical_path"] == path:
                return d["alsa_device"]
        return None

class ExternalAudioSource(AudioSource):

    def __init__(self, bucket, endpoint_url, access_key_id, secret_access_key, region: str, base=""):
        self.bucket = bucket
        self.base = base
        print(f"PAM client store using {endpoint_url}")

    def configuration() -> dict:
        return AudioSource.configuration() | {
            "device": {
                "type": "text",
                "label": "Card Reader Device",
                "required": True,
            },
            "capture_button": {
                "type": "button",
                "label": "Card Reader",
                "text": "Capture",
                "onclick": "start_ext_capture()"
            },
            "segment_length": {
                "type": "text",
                "label": "Segment Length (s)",
                "required": True,
                "coerce": float
            },
        }
    
    def udev_line_to_devices(l):
        match = re.search(r"\[\d+\.\d+\] add +(\S+)", l)
        if not match:
            return None, None
        else:
            whole_path = match.group(1)
            parts = whole_path.split("/")
            idx = parts.index("block") - 1
            path = "/".join(parts[0:idx]) + "/"
            return path, parts[-1]

    def is_valid_partition(device):
        result = subprocess.run(['udevadm','info','--query=property','/dev/' + device], capture_output=True, text=True)
        match = re.search(r"DEVTYPE=partition", result.stdout)
        if not match:
            return False
        match = re.search(r"PARTN=1", result.stdout)
        if not match:
            return False
        return True

    def monitor_udev(timeout=None,fn=None,target=None):
        proc = subprocess.Popen(
            [
                "udevadm",
                "monitor",
                "--udev",
                "--subsystem-match=block",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        shutdown_r, shutdown_w = os.pipe()

        def shutdown(signum, frame):
            print("Got shutdown")
            os.write(shutdown_w, b"x")

        old_handler = None
        try:
            old_handler = signal.signal(signal.SIGTERM, shutdown)
        except:
            pass

        deadline = None
        if timeout is not None:
            deadline = time.monotonic() + timeout

        try:
            resume = True
            while resume:
                wait = None
                if deadline is not None:
                    wait = deadline - time.monotonic()

                    if wait <= 0:
                        return None

                ready, _, _ = select.select(
                    [proc.stdout, shutdown_r],
                    [],
                    [],
                    wait
                )

                print("SELECT RETURNED")

                if not ready:
                    return None
                elif shutdown_r in ready:
                    return None
                elif proc.stdout in ready:
                    line = proc.stdout.readline()

                    if line == "":
                        return None

                    if not line or not line.startswith("UDEV"):
                        continue
                    line = line.strip()
                    print("Got line", line)
                    value = fn(line,target)
                    if value is not None:
                        if old_handler is not None:
                            signal.signal(signal.SIGTERM, old_handler)
                            old_handler = None
                        return value
                else:
                    return None
        finally:
            if proc.poll() is None:
                proc.terminate()

                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            else:
                # Already exited, but make sure we've reaped it.
                proc.wait()

            if old_handler is not None:
                old_handler(None,None)

    def grab_parent(line,target):
        parent, device = ExternalAudioSource.udev_line_to_devices(line)
        if parent and device and ExternalAudioSource.is_valid_partition(device):
            print("Found parent device:", parent)
            #call the response function
            return parent
        else:
            return None
         
    def grab_dev(line,target_parent):
        parent, device = ExternalAudioSource.udev_line_to_devices(line)
        if parent and device and parent == target_parent and ExternalAudioSource.is_valid_partition(device):
            return device
        else:
            return None

class PAMAudioSource(AudioSource):

    def __init__(self, bucket, endpoint_url, access_key_id, secret_access_key, region: str, base=""):
        self.bucket = bucket
        self.base = base
        print(f"RTSP client store using {endpoint_url}")

    def configuration() -> dict:
        return AudioSource.configuration() | {
            "serial": {
                "type": "text",
                "label": "Serial #",
                "required": True,
            },
            "segment_length": {
                "type": "text",
                "label": "Segment Length (s)",
                "required": True,
                "coerce": float
            },
        }    

_backends = {
    "rtsp": {"name": "RTSP", "class": RTSPAudioSource},
    "alsa": {"name": "ALSA Device", "class": ALSAAudioSource},
    "ext": {"name": "External Storage", "class": ExternalAudioSource},
    "pam": {"name": "PAM Device", "class": PAMAudioSource},
}

def types():
    return _backends

def create(type: str, configuration: dict):
    if type not in _backends:
        raise ValueError(f"Unknown audio source type: {type}")
    else:
        return _backends[type]["class"](**configuration)

def configuration(type: str) -> dict:
    return _backends[type]["class"].configuration()

def toJson(values = {}):
    cfg = configuration(values["type"])

    for k in cfg:
        if k in values and "coerce" in cfg[k]:
            print(cfg[k]["coerce"])
            values[k] = cfg[k]["coerce"](values[k])

    return json.dumps(values)

#print(ALSAAudioSource.enumerate_recording_sources())
#print(ALSAAudioSource.physical_path_to_alsa("/devices/pci0000:00/0000:00:14.0/usb1/1-2/1-2.4/1-2.4:1.0"))