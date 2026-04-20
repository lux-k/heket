import librosa
import numpy as np
import joblib
import sys
import heket_config
import json

def extract_features(file):
    y, sr = librosa.load(file, sr=16000)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    return np.mean(mfcc, axis=1)

model = joblib.load(heket_config.MODEL_FILE)

file = sys.argv[1]
features = extract_features(file).reshape(1, -1)

prediction = model.predict(features)[0]
probs = model.predict_proba(features)[0]

print(json.dumps( {"prediction": prediction, "confidence": max(probs)} ))
sys.exit(0)
