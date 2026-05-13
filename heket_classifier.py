import numpy as np
import librosa
import heket_config
import os
from datetime import datetime
from io import BytesIO
import librosa.display
import matplotlib.pyplot as plt
   
def load_model_from_file(file):
    if file.endswith(".pkl"):
        #cnn models
        return RandomForestModel(file)
    elif file.endswith(".keras"):
        return CnnModel(file)
    else:
        raise NotImplementedError()

def load_model_from_mode(mode):
    if mode in ["simple","deltas"]:
        return RandomForestModel(mode=heket_config.MODEL_LEVEL)
    elif mode in ["cnn"]:
        return CnnModel(mode=heket_config.MODEL_LEVEL)
    else:
        print("Unknown operating mode", mode)
        return None

def generate_spectrogram(wav_file, output_file, n_mels=128):
    # Load audio
    y, sr = librosa.load(wav_file, sr=heket_config.SAMPLE_RATE)

    # Generate mel spectrogram
    mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=n_mels)

    # Convert to decibels
    mel_db = librosa.power_to_db(mel, ref=np.max)

    # Create figure
    plt.figure(figsize=(10, 3), dpi=50)

    # Render spectrogram
    plt.imshow(mel_db, aspect='auto', origin='lower', cmap='inferno')

    # Remove axes/borders
    plt.axis('off')

    # Remove padding/margins
    plt.tight_layout(pad=0)

    # Save image
    # plt.savefig(output_file, bbox_inches='tight', pad_inches=0)

    # Cleanup matplotlib memory
	
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
    buf.seek(0)

    plt.close('all')

    return buf

class HeketModel:
    file = ""
    model = None
    
    def predict(self, path):
        raise NotImplementedError()

    def extract_features_from_file(self, file):
        y, sr = librosa.load(file, sr=heket_config.SAMPLE_RATE)
        return self.extract_features_from_audio(y, sr)

class RandomForestModel(HeketModel):
    mode = "unknown"
    
    def __init__(self, file=None, mode=None):
        import joblib
        
        if file is not None:
            self.file = file
            self.model = joblib.load(file)

        if mode is None:
            if self.model.n_features_in_ == 20:
                self.mode = "simple"
            elif self.model.n_features_in_ == 80:
                self.mode = "deltas"
        else:
            self.mode = mode

        print("Set mode to", self.mode)
            
    def extract_features_from_audio(self, y, sr):
        if self.mode == "simple":
            return self._extract_features_simple(y, sr)
        elif self.mode == "deltas":
            return self._extract_features_more_details(y, sr)
        else:
            print("Unknown model shape")
            return None
            
    def predict(self, features):
        probs = self.model.predict_proba([features])[0]
        idx = probs.argmax()
        species = self.model.classes_[idx]
        confidence = float(probs[idx])
        return species, confidence

    def _extract_features_simple(self, y, sr):
        # MFCCs (very effective for audio classification)
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
        
        # Take mean across time
        return np.mean(mfcc, axis=1)

    def _extract_features_more_details(self, y, sr):
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
        
        mfcc_mean = np.mean(mfcc, axis=1)
        mfcc_std  = np.std(mfcc, axis=1)

        delta = librosa.feature.delta(mfcc)

        delta_mean = np.mean(delta, axis=1)
        delta_std  = np.std(delta, axis=1)

        features = np.concatenate([
            mfcc_mean,
            mfcc_std,
            delta_mean,
            delta_std
        ])
        
        return features

    def train(self, source_path):
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import classification_report
        import joblib
        print("Training using random forest classifier")
        X = []
        y = []

        labels = os.listdir(source_path)

        for label in sorted(labels):
            folder = os.path.join(source_path, label)
            for file in os.listdir(folder):
                if file.endswith(".wav"):
                    path = os.path.join(folder, file)
                    features = self.extract_features_from_file(path)
                    X.append(features)
                    y.append(label)

        X = np.array(X)

        X_train = X
        y_train = y

        model = RandomForestClassifier(n_estimators=100)
        model.fit(X_train, y_train)

        # Save model
        file = os.path.join(heket_config.CUSTOM_MODEL_DIR, "frog_model_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".pkl")
        joblib.dump(model, file)
        print("Classes:", model.classes_)
        print(f"Model saved as {file}")
        
class CnnModel(HeketModel):
    label_file = ""
    labels = []
    
    def __init__(self, file=None, mode=None):
        from tensorflow import keras
        if file is not None:
            self.file = file
            self.model = keras.models.load_model(file)
            self.label_file = self.file.replace(".keras", ".labels")
            with open(self.label_file) as f:
                self.labels = [line.strip() for line in f]        

    def predict(self, features):
        features = np.expand_dims(features, axis=0)
        features = features[..., np.newaxis]

        probs = self.model.predict(features)[0]

        idx = probs.argmax()

        species = self.labels[idx]

        confidence = float(probs[idx])

        return species, confidence

    def extract_features_from_audio(self, y, sr):
        return self._extract_features_cnn(y, sr)

    def normalize_audio(self, y, sr):
        TARGET_SAMPLES = heket_config.SEGMENT_TIME * sr

        if len(y) > TARGET_SAMPLES:
            y = y[:TARGET_SAMPLES]

        elif len(y) < TARGET_SAMPLES:
            padding = TARGET_SAMPLES - len(y)
            y = np.pad(y, (0, padding))

        return y, sr
        
    def _extract_features_cnn(self, y, sr):
        y, sr = self.normalize_audio(y, sr)

        mel = librosa.feature.melspectrogram( y=y, sr=sr, n_mels=64 )

        mel_db = librosa.power_to_db(mel)

        return mel_db

    def train(self, source_path):
        from sklearn.preprocessing import LabelEncoder
        from tensorflow import keras
        from tensorflow.keras import layers
        print("Using CNN..")
        X = []
        y = []

        labels = os.listdir(source_path)

        # Load dataset
        for label in labels:
            folder = os.path.join(source_path, label)

            for file in sorted(os.listdir(folder)):
                if file.endswith(".wav"):
                    path = os.path.join(folder, file)
                    features = self.extract_features_from_file(path)

                    X.append(features)
                    y.append(label)

        X = np.array(X)
        X = X[..., np.newaxis]

        # Encode labels as integers
        encoder = LabelEncoder()
        y_encoded = encoder.fit_transform(y)

        # Build CNN model
        model = keras.Sequential([
            layers.Input(shape=(64, 469, 1)),
            layers.Conv2D(32, (3,3), activation='relu'),
            layers.MaxPooling2D((2,2)),
            layers.Conv2D(64, (3,3),  activation='relu'),
            layers.MaxPooling2D((2,2)),
            layers.Flatten(),
            layers.Dense(64, activation='relu' ),
            layers.Dense(len(labels), activation='softmax')
        ])

        # Configure training
        model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])

        # Train
        model.fit(X, y_encoded, epochs=10, batch_size=16 )

        file = os.path.join(heket_config.CUSTOM_MODEL_DIR, "frog_model_cnn_" +  datetime.now().strftime("%Y%m%d_%H%M%S") + ".keras")

        model.save(file)
        label_file = file.replace(".keras", ".labels")

        with open(label_file, "w") as f:
            for label in encoder.classes_:
                f.write(f"{label}\n")

        print(f"Model saved as {file}")
        print(f"Labels saved as {label_file}")    
        print("Classes:", encoder.classes_)        