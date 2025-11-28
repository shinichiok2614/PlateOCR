# Hướng dẫn Cài đặt & Tài nguyên YOLO + OCR

## 📦 Interpreter / Packages

``` bash
pip install opencv-python
pip install ultralytics opencv-python
pip install ultralytics opencv-python-headless
pip install onnxruntime

pip uninstall opencv-python opencv-python-headless -y
```

------------------------------------------------------------------------

## 🔗 Tài nguyên tham khảo

### YOLOv8 ALPR

-   https://github.com/Muhammad-Zeerak-Khan/Automatic-License-Plate-Recognition-using-YOLOv8?tab=readme-ov-file\
-   https://drive.google.com/file/d/1Zmf5ynaTFhmln2z7Qvv-tgjkWQYQ9Zdw/view

### License Plate Recognition (HuggingFace)

-   https://huggingface.co/MKgoud/License-Plate-Recognizer

### Roboflow Model

-   https://universe.roboflow.com/ml-sdznj/yolov8-number-plate-detection/model/1

### YOLOv8 Face

-   https://github.com/Yusepp/YOLOv8-Face?tab=readme-ov-file
    -   nano:
        https://drive.google.com/file/d/1ZD_CEsbo3p3_dd8eAtRfRxHDV44M0djK/view?usp=sharing\
    -   large:
        https://drive.google.com/file/d/1iHL-XjvzpbrE8ycVqEbGla4yc1dWlSWU/view?usp=sharing

### Fast Plate OCR

-   https://github.com/ankandrew/fast-plate-ocr/tree/master\

``` bash
pip install fast-plate-ocr[onnx]
```

------------------------------------------------------------------------

## 🚗 Vehicle Detection (YOLO + DeepSORT)

``` bash
pip install ultralytics deep-sort-realtime onnxruntime opencv-python
```

### Model YOLOv8

  ---------------------------------------------------------------------------------------------------------------------
  File              Link tải                                                                    Detect
  ----------------- --------------------------------------------------------------------------- -----------------------
  **yolov8n.pt**    https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt   car, motorcycle, bus,
                                                                                                truck

  **yolov8s.pt**    https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8s.pt   chính xác hơn

  **yolov8m.pt**    https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8m.pt   mạnh hơn
  ---------------------------------------------------------------------------------------------------------------------

Nguồn tổng hợp model YOLOv8:\
https://github.com/keremberke/awesome-yolov8-models

------------------------------------------------------------------------

## 🎬 MoviePy

``` bash
pip install moviepy
# phiên bản khuyến nghị
moviepy==2.2.1
```
