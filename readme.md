# Hướng dẫn Cài đặt & Tài nguyên YOLO + OCR

## 📦 Interpreter / Packages

Bước 1 – Cài Python 3.12 (12 hoặc 11)

Tải Python 3.12.7:

https://www.python.org/downloads/release/python-3127/

Tick Add to PATH khi cài.
``` bash
pip install pillow
pip install numpy==1.26.4
pip install opencv-python==4.12.0.88
pip install ultralytics
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

Nguồn tổng hợp model YOLOv8:\
https://github.com/keremberke/awesome-yolov8-models

------------------------------------------------------------------------

## 🎬 MoviePy

``` bash
pip install moviepy==2.2.1
# phiên bản khuyến nghị
moviepy==2.2.1
```

Đóng gói thành file thực thi (.exe) cho Windows

pip install pyinstaller

Chuyển đến thư mục chứa file chính (ví dụ main.py) và chạy:

pyinstaller --onefile main.py

Tùy chọn khác:
pyinstaller --onefile --windowed main.py

--windowed: dùng cho ứng dụng GUI, không hiện console.

Lưu ý

Nếu code sử dụng các thư viện bên ngoài (OpenCV, Pillow, PyQt…), PyInstaller sẽ tự đóng gói nhưng đôi khi cần thêm tùy chọn:

pyinstaller --onefile --add-data "path/to/data;data" main.py

--add-data "source;destination": copy file dữ liệu (ví dụ hình ảnh, database, config).

Trên Windows, dùng dấu ; để phân tách.

Nếu exe bị chậm khi khởi động, đó là vì PyInstaller unpack mọi thứ vào bộ nhớ trước khi chạy.


✅ Cách sửa nhanh nhất (khuyên dùng)
Cách 1: Cài bản OpenCV có GUI – "opencv-python-headless" gỡ và cài lại bản đủ GUI

Chạy:

pip uninstall opencv-python opencv-python-headless -y
pip install opencv-python==4.9.0.80


Lý do:
Bản 4.9.0.80 là bản cuối cùng tương thích ổn định Windows GUI.

Nếu Python 3.13 không cho cài → bạn phải dùng Python 3.12.

⭐ Cách 2 (đề xuất mạnh nhất):
👉 Dùng Python 3.12 hoặc 3.11 (ổn định nhất cho OpenCV + YOLO + Tkinter)

Lý do:

Tkinter + OpenCV + Ultralytics YOLO đã được test ổn nhất trên Python 3.10–3.12.

Python 3.13 hiện đang quá mới → nhiều thư viện chưa cập nhật backend GUI.

Cài Python 3.12:

Bước 1 – Cài Python 3.12

https://www.python.org/downloads/release/python-3120/

Bước 2 – Tạo venv riêng:
py -3.12 -m venv venv312
venv312\Scripts\activate

Bước 3 – Cài OpenCV GUI + Tkinter + YOLO
pip install opencv-python
pip install ultralytics


→ Chắc chắn chạy được cv2.imshow() và cv2.namedWindow().

❗ Nếu bạn buộc dùng Python 3.13

OpenCV GUI chưa hỗ trợ, bạn phải tự tạo cửa sổ bằng Tkinter + PIL, không dùng highgui.

Ví dụ fix lại để không dùng cv2.namedWindow():