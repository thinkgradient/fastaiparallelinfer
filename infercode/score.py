# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license.

import os
import json

from base64 import b64decode
from io import BytesIO

from azureml.core.model import Model
from fastai.vision import load_learner, open_image

def init():
    global model
    model_path = Model.get_model_path(model_name='model-fatos-resnet18')
    # ! We cannot use the *model_name* variable here otherwise the execution on Azure will fail !
    
    model_dir_path, model_filename = os.path.split(model_path)
    print("Model dir: ", model_dir_path)
    print("Model filename: ", model_filename)
    model_filename = model_filename
    model = load_learner(path=model_dir_path, file=model_filename)


def run(raw_data):
    print(f"{raw_data}")
    # Expects raw_data to be a list within a json file
    result = []    
    for im in raw_data:
        try:
            im = open_image(im)
            pred_class, pred_idx, outputs = model.predict(im)
            result.append({"label": str(pred_class), "probability": str(outputs[pred_idx].item())})
        except Exception as e:
            result.append({"label": str(e), "probability": ''})
    return result
