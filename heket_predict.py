import librosa
import numpy as np
import joblib
import sys
import heket_config
import json
import heket_classifier

#heket_config.MODEL_FILE = "BirdNET_GLOBAL_6K_V2.4_Model_FP32.tflite"
#heket_config.SAMPLE_RATE = 48000

model = heket_classifier.load_model_from_file(heket_config.MODEL_FILE)
file = sys.argv[1]

features = model.extract_features_from_file(file)

species, confidence = model.predict(features)

print(json.dumps( {"prediction": species, "confidence": f"{confidence:.2g}"} ))
sys.exit(0)
