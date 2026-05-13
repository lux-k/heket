import os
import heket_config
import heket_classifier

DATASET_PATH = heket_config.LABELED_DIR

os.makedirs(heket_config.CUSTOM_MODEL_DIR, exist_ok=True)

model = heket_classifier.load_model_from_mode(heket_config.MODEL_LEVEL)
model.train(DATASET_PATH)