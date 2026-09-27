import os
import heket_config
import heket_classifier

DATASET_PATH = heket_config.LABELED_DIR

model = heket_classifier.load_model_from_mode(heket_config.MODEL_LEVEL, sample_rate=heket_config.SAMPLE_RATE, slice_time=heket_config.SLICE_TIME)
model.train(DATASET_PATH)
model.save_metadata()
