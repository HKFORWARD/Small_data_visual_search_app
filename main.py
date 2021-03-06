"""
Small data visual search app 
App API Example

Copyright (c) 2020 Alyona Galyeva
Licensed under the MIT License (see LICENSE for details)
------------------------------------------------------------
Usage: run from the command line as such:
    to use small model:
        python main.py small
    to use large model:
        python main.py large
"""


import json
import random
import sys

import numpy as np
import skimage
import tensorflow as tf
import uvicorn

from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel

from api.settings import (APP_TEST_DATA, COCO_DATA, MASK_RCNN_MODEL_PATH, MODEL_DIR)

COCO_DATA = COCO_DATA
APP_TEST_DATA = APP_TEST_DATA
MASK_RCNN_MODEL_PATH = MASK_RCNN_MODEL_PATH

if MASK_RCNN_MODEL_PATH not in sys.path:
    sys.path.append(MASK_RCNN_MODEL_PATH)
    
from samples.coco import coco
from mrcnn import utils
from mrcnn import model as modellib
from mrcnn import visualize
    
from lib import utils as siamese_utils
from lib import model as siamese_model
from lib import config as siamese_config


class RequestBody(BaseModel):
    number: int 


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)


class SmallEvalConfig(siamese_config.Config):
    # Set batch size to 1 since we'll be running inference on
    # one image at a time. Batch size = GPU_COUNT * IMAGES_PER_GPU
    GPU_COUNT = 1
    IMAGES_PER_GPU = 1
    NUM_CLASSES = 1 + 1
    NAME = 'coco'
    EXPERIMENT = 'evaluation'
    CHECKPOINT_DIR = 'checkpoints/'
    NUM_TARGETS = 1


class LargeEvalConfig(siamese_config.Config):
    # Set batch size to 1 since we'll be running inference on
    # one image at a time. Batch size = GPU_COUNT * IMAGES_PER_GPU
    GPU_COUNT = 1
    IMAGES_PER_GPU = 1
    NUM_CLASSES = 1 + 1
    NAME = 'coco'
    EXPERIMENT = 'evaluation'
    CHECKPOINT_DIR = 'checkpoints/'
    NUM_TARGETS = 1
    
    # Large image sizes
    TARGET_MAX_DIM = 192
    TARGET_MIN_DIM = 150
    IMAGE_MIN_DIM = 800
    IMAGE_MAX_DIM = 1024
    # Large model size
    FPN_CLASSIF_FC_LAYERS_SIZE = 1024
    FPN_FEATUREMAPS = 256
    # Large number of rois at all stages
    RPN_ANCHOR_STRIDE = 1
    RPN_TRAIN_ANCHORS_PER_IMAGE = 256
    POST_NMS_ROIS_TRAINING = 2000
    POST_NMS_ROIS_INFERENCE = 1000
    TRAIN_ROIS_PER_IMAGE = 200
    DETECTION_MAX_INSTANCES = 100
    MAX_GT_INSTANCES = 100    


def load_model(model_size):
    global model
    global config
    if model_size == "small":
        config = SmallEvalConfig()
        checkpoint = 'checkpoints/small_siamese_mrcnn_0160.h5'
    elif model_size == "large":
        config = LargeEvalConfig()
        checkpoint = 'checkpoints/large_siamese_mrcnn_0320.h5'
    model = siamese_model.SiameseMaskRCNN(mode="inference", model_dir=MODEL_DIR, config=config)
    model.load_checkpoint(checkpoint)
    global graph
    graph = tf.get_default_graph()
    return model, graph


def prepare_dataset():
    one_shot_classes = np.array([4*i + 1 for i in range(20)])
    coco_val = siamese_utils.IndexedCocoDataset()
    coco_val.load_coco(COCO_DATA, subset="val", year="2017", return_coco=True)
    coco_val.prepare()
    coco_val.build_indices()
    coco_val.ACTIVE_CLASSES = one_shot_classes
    return coco_val


def prepare_image(image):
    if image.shape[-1] == 4:
        image = image[..., :3]
    return image


app = FastAPI(
    title="VisualSearch",
    description="Proof of concept for Visual Search app powered by Siamese Mask R-CNN exclusive for Pydata Amsterdam Festival 2020 :)",
    version="1.0.0",
)
model = None

model, graph = load_model(sys.argv[1])
coco_val = prepare_dataset()

@app.get("/")
def read_root():
    msg = (
        "PyData Amsterdam Festival rulezzz!!!!!!!!"
    )
    return {"message": msg}


@app.post("/api/v1/predict_by_category")
def predict_by_category(body: RequestBody):

    category = body.number
    if category not in range(1, 81):
        return {"msg": "Please indicate a number in the range from 1 to 80"}

    image_id = np.random.choice(coco_val.category_image_index[category])
    target = siamese_utils.get_one_target(category, coco_val, model.config)
    image = coco_val.load_image(image_id)

    with graph.as_default():
        prediction = model.detect([[target]], [image], verbose=0)
    
    results = prediction[0]
    json_results = json.dumps({"rois": results["rois"], "masks": results["masks"],
                               "class_ids": results["class_ids"], "scores": results["scores"]}, cls=NumpyEncoder)

    return json_results


@app.post("/api/v1/predict_image")
def predict_image(image_file: UploadFile=File(...)):
    file_path = APP_TEST_DATA+image_file.filename
    image = skimage.io.imread(file_path)
    image = prepare_image(image)
    image = utils.resize_image(image, min_dim=config.IMAGE_MIN_DIM, max_dim=config.IMAGE_MAX_DIM, min_scale=config.IMAGE_MIN_SCALE, mode=config.IMAGE_RESIZE_MODE)

    target = siamese_utils.get_one_target(np.random.choice(80), coco_val, model.config)
     
    with graph.as_default():
        prediction = model.detect([[target]], [image[0]], verbose=0)
    
    results = prediction[0]
    json_results = json.dumps({"rois": results["rois"], "masks": results["masks"],
                               "class_ids": results["class_ids"], "scores": results["scores"]}, cls=NumpyEncoder)

    return json_results

if __name__ == "__main__":
    
    uvicorn.run("main:app", host="127.0.0.1", port=8000, log_level="info")