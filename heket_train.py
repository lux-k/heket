import os
import numpy as np
import librosa
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import joblib
import heket_config
from datetime import datetime

DATASET_PATH = heket_config.LABELED_DIR

def extract_features(file):
    y, sr = librosa.load(file, sr=16000)
    
    # MFCCs (very effective for audio classification)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    
    # Take mean across time
    return np.mean(mfcc, axis=1)

X = []
y = []

labels = os.listdir(DATASET_PATH)

for label in labels:
    folder = os.path.join(DATASET_PATH, label)
    for file in os.listdir(folder):
        if file.endswith(".wav"):
            path = os.path.join(folder, file)
            features = extract_features(path)
            X.append(features)
            y.append(label)

X = np.array(X)

X_train = X
y_train = y

# Split for sanity check
#X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

model = RandomForestClassifier(n_estimators=100)
model.fit(X_train, y_train)

# Evaluate
#preds = model.predict(X_test)
#print(classification_report(y_test, preds))

# Save model
file = os.path.join(heket_config.CUSTOM_MODEL_DIR, "frog_model_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".pkl")
os.makedirs(heket_config.CUSTOM_MODEL_DIR, exist_ok=True)
joblib.dump(model, file)
print("Classes:", model.classes_)
print(f"Model saved as {file}")