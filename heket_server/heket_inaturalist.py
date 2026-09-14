import urllib.parse
import os
import requests
import pyinaturalist

import sys
from pathlib import Path
from datetime import datetime, timezone


parent_dir = str(Path(__file__).resolve().parent.parent)

if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import heket_config
import heket_common
import time

INATURALIST_CLIENT_ID = os.getenv("INATURALIST_CLIENT_ID")
INATURALIST_CLIENT_SECRET = os.getenv("INATURALIST_CLIENT_SECRET")
INATURALIST_CALLBACK_URL = os.getenv("INATURALIST_CALLBACK_URL")

INATURALIST_URL = os.getenv("INATURALIST_OAUTH_AUTHORIZE_URL") +  urllib.parse.urlencode( {"client_id": INATURALIST_CLIENT_ID,
                             "redirect_uri": INATURALIST_CALLBACK_URL,
                             "response_type": "code"})

JWT_CACHE = {}

def exchange_oauth_code_for_token(code):
    response = requests.post("https://www.inaturalist.org/oauth/token",    data={
        "client_id": INATURALIST_CLIENT_ID,
        "client_secret": INATURALIST_CLIENT_SECRET,
        "code": code,
        "redirect_uri": INATURALIST_CALLBACK_URL,
        "grant_type": "authorization_code",
    }
    )
    response.raise_for_status()
    token_data = response.json()
    return token_data

def get_device_jwt(device_id):
    global JWT_CACHE

    if device_id not in JWT_CACHE or JWT_CACHE[device_id]["expiration"] < time.time():
        #either not there or expired
        db = heket_common.get_db()
        cur = db.cursor()
        cur.execute(f"""select access_token from external_accounts where device_id = ? and provider = ?""", [device_id,'iNaturalist'])
        rows = cur.fetchall()
        if len(rows) == 1:
            print("JWT cache miss")
            JWT_CACHE[device_id] = {}
            JWT_CACHE[device_id]["jwt"] = get_jwt_from_access_token(heket_config.CRYPTO.decrypt(rows[0][0]))
            JWT_CACHE[device_id]["expiration"] = int(time.time()  + 24 * 3600 - 300)
            return JWT_CACHE[device_id]["jwt"]
        else:
            return None
    else:
        print("JWT cache hit")
        return JWT_CACHE[device_id]["jwt"]
    
def is_device_linked(device_id):
    ok = True
    jwt = None
    try:
        jwt = get_device_jwt(device_id)
        if jwt is None:
            ok = False
    except Exception as e:
        ok = False

    if ok:
        try:
            user = pyinaturalist.get_current_user(access_token=jwt)
        except Exception as e:
            ok = False

    return ok

def get_jwt_from_access_token(access_token):
    response = requests.get("https://www.inaturalist.org/users/api_token", headers={'Authorization': 'Bearer ' + access_token})
    response.raise_for_status()
    response = response.json()
    return response["api_token"]

def species_to_taxa(species):
    response = pyinaturalist.get_taxa(q=species)
    if response["total_results"] > 0:
        return response["results"][0]["id"]

    return None

def share_detection(device_id=None,species=None,utc_ts=None, latitude=None,longitude=None,sound=None):
    if species is None:
        print("No species given")
        return False
    
    if utc_ts is None:
        print("No utc_ts given")
        return False
    
    if latitude is None:
        print("No latitude given")
        return False

    if longitude is None:
        print("No longitude given")
        return False

    if sound is None:
        print("No sound given")
        return False

    if device_id is None:
        print("No device_id given")
        return False

    print("Device id is", device_id)
    jwt = get_device_jwt(device_id)
    if jwt is None:
        print("Couldn't get device jwt")
        return False

    taxon_id = species_to_taxa(species)
    if taxon_id is None:
        print("Unknown species", species)
        return False

    ts = datetime.fromtimestamp(utc_ts).isoformat()

    try:
        return True, pyinaturalist.create_observation(access_token=jwt,taxon_id=taxon_id,observed_on=ts,time_zone="UTC",latitude=latitude, longitude=longitude,sounds=sound)
    except Exception as e:
        return False