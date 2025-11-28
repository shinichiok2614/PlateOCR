import tkinter as tk
from tkinter import filedialog, ttk
import cv2
import os
from datetime import datetime
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort
from fast_plate_ocr import LicensePlateRecognizer
import sqlite3
import threading

# ============================
# DATABASE
# ============================
# conn = sqlite3.connect("plates.db")
# cur = conn.cursor()
# cur.execute("""
#     CREATE TABLE IF NOT EXISTS plate_logs (
#         id INTEGER PRIMARY KEY AUTOINCREMENT,
#         car_id INTEGER,
#         plate TEXT,
#         frame_path TEXT,
#         crop_path TEXT,
#         timestamp TEXT
#     )
# """)
# conn.commit()

# ============================
# MODELS
# ============================
vehicle_model = YOLO("yolov8n-vehicle.pt")          # detect xe
plate_model = YOLO("license_plate_detector.pt")  # detect biển số
ocr = LicensePlateRecognizer("cct-xs-v1-global-model")
tracker = DeepSort(max_age=30, n_init=3, nn_budget=100)

# ============================
# UTILS
# ============================
def iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA) * max(0, yB - yA)
    if interArea == 0:
        return 0
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    return interArea / float(boxAArea + boxBArea - interArea)

# ============================
# TKINTER GUI
# ============================
root = tk.Tk()
root.title("YOLO Plate Detection")
root.geometry("1200x600")

# LEFT: Video
video_frame = tk.Frame(root, width=800, height=600)
video_frame.pack(side=tk.LEFT, padx=5, pady=5)

lbl_video = tk.Label(video_frame)
lbl_video.pack()

# RIGHT: Treeview hiển thị Car ID + Plate
right_frame = tk.Frame(root, width=400)
right_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

columns = ("car_id", "plate")
tree = ttk.Treeview(right_frame, columns=columns, show="headings", height=30)
tree.heading("car_id", text="Car ID")
tree.heading("plate", text="Plate")
tree.column("car_id", width=80)
tree.column("plate", width=150)
tree.pack(fill=tk.Y, expand=True)

# ============================
# RUN VIDEO / CAMERA
# ============================
def run_camera_or_video():
    filepath = filedialog.askopenfilename(
        title="Chọn video",
        filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv"), ("All files", "*.*")]
    )

    if not filepath:
        cap = cv2.VideoCapture(0)
    else:
        cap = cv2.VideoCapture(filepath)

    os.makedirs("captures", exist_ok=True)
    os.makedirs("plates", exist_ok=True)

    def video_loop():
        # Tạo connection riêng cho thread
        conn_thread = sqlite3.connect("plates.db")
        cur_thread = conn_thread.cursor()
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # 1) Detect xe
            detections = []
            tracked_cars = []

            veh_res = vehicle_model(frame)[0]
            for box in veh_res.boxes:
                conf = float(box.conf[0])
                if conf < 0.3:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append(([x1, y1, x2 - x1, y2 - y1], conf, None))

            tracks = tracker.update_tracks(detections, frame=frame)
            for t in tracks:
                if not t.is_confirmed():
                    continue
                tid = t.track_id
                x1, y1, x2, y2 = map(int, t.to_ltrb())
                tracked_cars.append((tid, x1, y1, x2, y2))
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"Car {tid}", (x1, y1 - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # 2) Detect biển số
            plate_boxes = []
            plate_res = plate_model(frame)[0]
            for box in plate_res.boxes:
                conf = float(box.conf[0])
                if conf < 0.3:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                plate_boxes.append((x1, y1, x2, y2))
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)

            # 3) Match biển số ↔ xe
            matches = []
            for px1, py1, px2, py2 in plate_boxes:
                best_iou = 0
                best_car = None
                for car_id, x1, y1, x2, y2 in tracked_cars:
                    iou_val = iou((px1, py1, px2, py2), (x1, y1, x2, y2))
                    if iou_val > best_iou:
                        best_iou = iou_val
                        best_car = (car_id, (px1, py1, px2, py2))
                if best_car and best_iou > 0.1:
                    matches.append(best_car)

            # 4) OCR + update Treeview + save DB
            tree.delete(*tree.get_children())  # xóa trước khi thêm mới
            for car_id, (x1, y1, x2, y2) in matches:
                crop = frame[y1:y2, x1:x2]
                try:
                    plate_text = ocr.run(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
                    if isinstance(plate_text, list):
                        plate_text = "".join(plate_text)
                except:
                    plate_text = None

                if plate_text:
                    # Vẽ trên frame
                    cv2.putText(frame, plate_text, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                    # Thêm vào Treeview
                    tree.insert("", tk.END, values=(car_id, plate_text))
                    # Lưu DB
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    frame_path = f"captures/frame_{car_id}_{timestamp}.jpg"
                    crop_path  = f"plates/plate_{car_id}_{timestamp}.jpg"
                    cv2.imwrite(frame_path, frame)
                    cv2.imwrite(crop_path, crop)
                    # Lưu database
                    cur_thread.execute("""
                                       INSERT INTO plate_logs (car_id, plate, frame_path, crop_path, timestamp)
                                       VALUES (?, ?, ?, ?, ?)
                                       """, (car_id, plate_text, frame_path, crop_path, timestamp))
                    conn_thread.commit()


            # Show video trong Tkinter
            img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = cv2.resize(img, (800, 600))
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            imgtk = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            imgtk = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            imgtk = cv2.resize(img, (800, 600))
            imgtk = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            imgtk = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            imgtk = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            imgtk = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            # Dùng OpenCV window tạm nếu muốn, hoặc chuyển sang Tkinter Label
            cv2.imshow("Video", frame)
            if cv2.waitKey(1) == 27:
                break
        conn_thread.close()
        cap.release()
        cv2.destroyAllWindows()

    threading.Thread(target=video_loop, daemon=True).start()

# ============================
btn = tk.Button(root, text="Chọn video / camera và chạy", command=run_camera_or_video, width=40, height=2)
btn.pack(pady=10)

root.mainloop()

