import os
import cv2
import time
import queue
import threading
import sqlite3
import numpy as np
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from datetime import datetime
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort
from fast_plate_ocr import LicensePlateRecognizer

# ---------------------------
# Config (thay đường dẫn model nếu cần)
# ---------------------------
VEHICLE_MODEL_PATH = "yolov8n-vehicle.pt"
PLATE_MODEL_PATH = "license_plate_detector.pt"
OCR_MODEL_NAME = "cct-xs-v1-global-model"

SAVED_CARS = "saved_cars"
SAVED_PLATES = "saved_plates"
DB_PATH = "plates.db"

# Tạo thư mục lưu
os.makedirs(SAVED_CARS, exist_ok=True)
os.makedirs(SAVED_PLATES, exist_ok=True)

# ---------------------------
# Load models (chậm khi import lần đầu)
# ---------------------------
vehicle_model = YOLO(VEHICLE_MODEL_PATH)
plate_model = YOLO(PLATE_MODEL_PATH)
ocr = LicensePlateRecognizer(OCR_MODEL_NAME)

# DeepSort tracker
tracker = DeepSort(max_age=30, n_init=3, nn_budget=100)

# ---------------------------
# Thread-safe queue để truyền kết quả từ thread video -> main thread (GUI)
# Mỗi item là dict: {"car_id": int, "plate": str or None, "car_path": str, "plate_path": str, "time": ts}
# ---------------------------
result_queue = queue.Queue()

# ---------------------------
# Utility functions
# ---------------------------
def bbox_to_ints(xy):
    """
    Trả về tuple (x1,y1,x2,y2) int từ box.xyxy[0] object.
    Hỗ trợ tensor hoặc list.
    """
    try:
        coords = xy[0]
        # If torch tensor
        if hasattr(coords, "cpu"):
            a = coords.cpu().numpy()
        else:
            a = np.array(coords)
        x1, y1, x2, y2 = map(int, a.tolist())
        return x1, y1, x2, y2
    except Exception:
        # fallback: try convert directly
        a = np.array(xy)
        if a.size >= 4:
            x1, y1, x2, y2 = map(int, a.flatten()[:4])
            return x1, y1, x2, y2
        raise

def centroid(box):
    x1,y1,x2,y2 = box
    return ((x1+x2)/2, (y1+y2)/2)

# ---------------------------
# GUI class
# ---------------------------
class App:
    def __init__(self, root):
        self.root = root
        root.title("Vehicle + Plate OCR")
        root.geometry("1200x700")

        # Left: video display (we use OpenCV window for simplicity)
        left = tk.Frame(root)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        btn_frame = tk.Frame(left)
        btn_frame.pack(pady=6)
        self.btn_open = tk.Button(btn_frame, text="Chọn video / camera", command=self.select_and_start)
        self.btn_open.pack(side=tk.LEFT, padx=6)
        self.btn_stop = tk.Button(btn_frame, text="Dừng", command=self.stop_video, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=6)

        # Right: Treeview + preview
        right = tk.Frame(root, width=380)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=6, pady=6)

        tk.Label(right, text="Danh sách phát hiện", font=("Arial", 12, "bold")).pack()

        columns = ("car_id", "plate", "time")
        self.tree = ttk.Treeview(right, columns=columns, show="headings", height=30)
        self.tree.heading("car_id", text="Car ID")
        self.tree.heading("plate", text="Plate")
        self.tree.heading("time", text="Time")
        self.tree.column("car_id", width=70)
        self.tree.column("plate", width=150)
        self.tree.column("time", width=140)
        self.tree.pack(fill=tk.Y, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_row_selected)

        # Preview images
        preview = tk.Frame(right)
        preview.pack(pady=6, fill=tk.X)
        tk.Label(preview, text="Preview (click row):").pack(anchor="w")
        self.lbl_car = tk.Label(preview, text="Car image", width=40, height=10, relief=tk.SUNKEN)
        self.lbl_car.pack(fill=tk.X, pady=2)
        self.lbl_plate = tk.Label(preview, text="Plate image", width=40, height=6, relief=tk.SUNKEN)
        self.lbl_plate.pack(fill=tk.X, pady=2)

        # Internal
        self.video_thread = None
        self.running = False
        self.cap = None
        self.current_video_path = None
        self.latest_entries = []  # list of dicts stored for GUI display

        # Start polling queue -> GUI
        self.root.after(200, self.process_queue)

    def select_and_start(self):
        path = filedialog.askopenfilename(title="Chọn video (hoặc hủy để dùng camera)",
                                          filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv"), ("All files", "*.*")])
        self.current_video_path = path if path else None
        self.start_video()

    def start_video(self):
        if self.running:
            messagebox.showinfo("Thông báo", "Video đang chạy")
            return
        # open capture
        if self.current_video_path:
            cap = cv2.VideoCapture(self.current_video_path)
            if not cap.isOpened():
                messagebox.showerror("Lỗi", f"Không mở được file: {self.current_video_path}")
                return
        else:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                messagebox.showerror("Lỗi", "Không mở được camera")
                return

        self.cap = cap
        self.running = True
        self.btn_open.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)

        # start thread
        self.video_thread = threading.Thread(target=self.video_loop, daemon=True)
        self.video_thread.start()

    def stop_video(self):
        self.running = False
        self.btn_open.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        # video thread will stop and release cap

    def reload_table(self, new_entries):
        """
        Xóa toàn bộ dữ liệu cũ trên Treeview và thêm dữ liệu mới.
        """
        # Xóa Treeview
        for item in self.tree.get_children():
            self.tree.delete(item)
        # Xóa list cũ
        self.latest_entries.clear()
        # Thêm dữ liệu mới
        for item in new_entries:
            self.latest_entries.append(item)
            self.tree.insert("", tk.END, values=(item["car_id"], item["plate_text"] or "", item["ts"]))

    def process_queue(self):
        """
        Lấy toàn bộ items từ queue, xóa dữ liệu cũ, thêm dữ liệu mới.
        """
        new_entries = []
        while not result_queue.empty():
            item = result_queue.get()
            new_entries.append(item)

        if new_entries:
            self.reload_table(new_entries)

        self.root.after(200, self.process_queue)

    def on_row_selected(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if idx < 0 or idx >= len(self.latest_entries):
            return
        item = self.latest_entries[idx]
        # load and display car image & plate image thumbnails (use OpenCV -> PIL? But simpler: use Tk PhotoImage via PIL)
        try:
            from PIL import Image, ImageTk
            if item.get("car_path") and os.path.exists(item["car_path"]):
                im = Image.open(item["car_path"])
                im.thumbnail((360, 200))
                tkim = ImageTk.PhotoImage(im)
                self.lbl_car.config(image=tkim, text="")
                self.lbl_car.image = tkim
            else:
                self.lbl_car.config(image="", text="Không có ảnh xe")
                self.lbl_car.image = None
            if item.get("plate_path") and os.path.exists(item["plate_path"]):
                im2 = Image.open(item["plate_path"])
                im2.thumbnail((360, 120))
                tkim2 = ImageTk.PhotoImage(im2)
                self.lbl_plate.config(image=tkim2, text="")
                self.lbl_plate.image = tkim2
            else:
                self.lbl_plate.config(image="", text="Không có ảnh biển số")
                self.lbl_plate.image = None
        except Exception as e:
            # nếu PIL không cài, show path text
            self.lbl_car.config(text=item.get("car_path", "No car"))
            self.lbl_plate.config(text=item.get("plate_path", "No plate"))

    def video_loop(self):
        """
        Chạy trong thread riêng: detect -> track -> match -> OCR -> save -> push result queue
        Mở DB riêng trong thread để tránh lỗi sqlite multi-thread.
        """
        # Open DB connection for this thread
        db = sqlite3.connect(DB_PATH)
        cur = db.cursor()
        # ensure table exists (safe to create again)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS plate_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                car_id INTEGER,
                plate TEXT,
                car_path TEXT,
                plate_path TEXT,
                timestamp TEXT
            )
        """)
        db.commit()

        cap = self.cap
        frame_idx = 0

        try:
            while self.running:
                ret, frame = cap.read()
                if not ret:
                    break
                frame_idx += 1
                h, w = frame.shape[:2]

                # 1) Detect vehicles (all frames)
                veh_results = vehicle_model(frame)[0]
                detections = []
                for box in veh_results.boxes:
                    try:
                        x1,y1,x2,y2 = bbox_to_ints(box.xyxy)
                    except Exception:
                        # fallback if attribute different
                        x1,y1,x2,y2 = bbox_to_ints(box.xyxy[0])
                    conf = float(box.conf[0]) if hasattr(box.conf, "__getitem__") else float(box.conf)
                    # you can filter by class if the model is COCO-based; here we accept all detections from vehicle model
                    if conf < 0.25:
                        continue
                    # DeepSort expects [x,y,w,h]
                    detections.append(([x1, y1, x2-x1, y2-y1], conf, None))

                # 2) Update tracker and draw boxes
                tracks = tracker.update_tracks(detections, frame=frame)
                tracked_cars = []  # list of tuples (track_id, x1,y1,x2,y2)
                for t in tracks:
                    if not t.is_confirmed():
                        continue
                    tid = t.track_id
                    l, t_, r, b = t.to_ltrb()
                    x1, y1, x2, y2 = map(int, (l, t_, r, b))
                    # clamp
                    x1 = max(0, min(w-1, x1)); y1 = max(0, min(h-1, y1))
                    x2 = max(0, min(w-1, x2)); y2 = max(0, min(h-1, y2))
                    tracked_cars.append((tid, x1, y1, x2, y2))
                    # draw
                    cv2.rectangle(frame, (x1,y1), (x2,y2), (0,255,0), 2)
                    cv2.putText(frame, f"ID:{tid}", (x1, max(12,y1-6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)

                # 3) Detect plates (whole frame)
                plate_results = plate_model(frame)[0]
                plate_bboxes = []
                for box in plate_results.boxes:
                    try:
                        px1,py1,px2,py2 = bbox_to_ints(box.xyxy)
                    except Exception:
                        px1,py1,px2,py2 = bbox_to_ints(box.xyxy[0])
                    conf = float(box.conf[0]) if hasattr(box.conf, "__getitem__") else float(box.conf)
                    if conf < 0.25:
                        continue
                    # clamp
                    px1 = max(0, min(w-1, px1)); py1 = max(0, min(h-1, py1))
                    px2 = max(0, min(w-1, px2)); py2 = max(0, min(h-1, py2))
                    plate_bboxes.append((px1, py1, px2, py2))
                    cv2.rectangle(frame, (px1,py1), (px2,py2), (255,0,0), 2)
                    cv2.putText(frame, "Plate", (px1, max(12,py1-6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,0,0), 2)

                # 4) Match plate -> vehicle by checking centroid of plate inside vehicle bbox
                matches = []  # list of (car_id, plate_bbox)
                for pb in plate_bboxes:
                    pcx, pcy = centroid(pb)
                    matched = False
                    for (car_id, x1,y1,x2,y2) in tracked_cars:
                        if x1 <= pcx <= x2 and y1 <= pcy <= y2:
                            matches.append((car_id, pb))
                            matched = True
                            break
                    # if not matched, ignore

                # 5) For each match: crop car, crop plate, run OCR, save, push queue & DB
                for car_id, (px1,py1,px2,py2) in matches:
                    # find vehicle bbox for this car_id
                    vb = next((v for v in tracked_cars if v[0] == car_id), None)
                    if vb is None:
                        continue
                    _, vx1,vy1,vx2,vy2 = vb
                    # car crop is vehicle bbox
                    car_crop = frame[vy1:vy2, vx1:vx2].copy()
                    plate_crop = frame[py1:py2, px1:px2].copy() if (py2>py1 and px2>px1) else None

                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    car_filename = f"car_{car_id}_{ts}.jpg"
                    car_path = os.path.join(SAVED_CARS, car_filename)
                    cv2.imwrite(car_path, car_crop)

                    plate_path = None
                    plate_text = None
                    if plate_crop is not None and plate_crop.size > 0:
                        plate_filename = f"plate_{car_id}_{ts}.jpg"
                        plate_path = os.path.join(SAVED_PLATES, plate_filename)
                        cv2.imwrite(plate_path, plate_crop)
                        # OCR (convert to RGB)
                        try:
                            plate_text_raw = ocr.run(cv2.cvtColor(plate_crop, cv2.COLOR_BGR2RGB))
                            if isinstance(plate_text_raw, list):
                                plate_text = "".join(plate_text_raw)
                            else:
                                plate_text = plate_text_raw
                        except Exception:
                            plate_text = None

                    # Save to DB (thread-local connection)
                    try:
                        cur.execute("""
                            INSERT INTO plate_logs (car_id, plate, car_path, plate_path, timestamp)
                            VALUES (?, ?, ?, ?, ?)
                        """, (int(car_id), plate_text, car_path, plate_path, ts))
                        db.commit()
                    except Exception as e:
                        print("DB insert error:", e)

                    # Push to GUI queue
                    result_queue.put({
                        "car_id": int(car_id),
                        "plate_text": plate_text,
                        "car_path": car_path,
                        "plate_path": plate_path,
                        "ts": ts
                    })

                    # draw plate_text on frame near plate bbox
                    if plate_text:
                        cv2.putText(frame, str(plate_text), (px1, max(12, py1-20)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,255), 2)

                # 6) show frame with rectangles (use OpenCV window)
                cv2.imshow("Vehicle + Plate (press ESC to stop)", frame)
                if cv2.waitKey(1) == 27:
                    # user pressed ESC
                    self.running = False
                    break

        finally:
            # cleanup
            try:
                db.close()
            except:
                pass
            try:
                cap.release()
            except:
                pass
            cv2.destroyAllWindows()
            # notify main thread
            self.running = False
            self.btn_open.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)

# ---------------------------
# Run application
# ---------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
