import os
import cv2
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
from PIL import Image, ImageTk

# ---------------------------
# Config
# ---------------------------
VEHICLE_MODEL_PATH = "yolov8n-vehicle.pt"
PLATE_MODEL_PATH = "license_plate_detector.pt"
OCR_MODEL_NAME = "cct-xs-v1-global-model"

SAVED_CARS = "saved_cars"
SAVED_PLATES = "saved_plates"
DB_PATH = "plates.db"

os.makedirs(SAVED_CARS, exist_ok=True)
os.makedirs(SAVED_PLATES, exist_ok=True)

# Load models
vehicle_model = YOLO(VEHICLE_MODEL_PATH)
plate_model = YOLO(PLATE_MODEL_PATH)
ocr = LicensePlateRecognizer(OCR_MODEL_NAME)
tracker = DeepSort(max_age=30, n_init=3, nn_budget=100)

# Thread-safe queue
result_queue = queue.Queue()

# ---------------------------
# Utils
# ---------------------------
def bbox_to_ints(xy):
    try:
        coords = xy[0] if hasattr(xy[0], "__getitem__") else xy
        a = coords.cpu().numpy() if hasattr(coords, "cpu") else np.array(coords)
        x1, y1, x2, y2 = map(int, a.tolist())
        return x1, y1, x2, y2
    except Exception:
        a = np.array(xy)
        if a.size >= 4:
            x1, y1, x2, y2 = map(int, a.flatten()[:4])
            return x1, y1, x2, y2
        raise

def centroid(box):
    x1,y1,x2,y2 = box
    return ((x1+x2)/2, (y1+y2)/2)

# ---------------------------
# GUI
# ---------------------------
class App:
    def __init__(self, root):
        self.root = root
        root.title("Vehicle + Plate OCR")
        root.geometry("1200x700")

        # Left: video + buttons
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

        # Tags for coloring
        self.tree.tag_configure('new_car', background='lightgreen')
        self.tree.tag_configure('left_car', background='lightcoral')

        # Preview
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
        self.car_states = {}  # {car_id: 'present'/'left'}

        # Polling queue
        self.root.after(200, self.process_queue)

    # ---------------------------
    def select_and_start(self):
        path = filedialog.askopenfilename(title="Chọn video (hoặc hủy để dùng camera)",
                                          filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv"), ("All files", "*.*")])
        self.current_video_path = path if path else None
        self.start_video()

    def start_video(self):
        if self.running:
            messagebox.showinfo("Thông báo", "Video đang chạy")
            return
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
        self.video_thread = threading.Thread(target=self.video_loop, daemon=True)
        self.video_thread.start()

    def stop_video(self):
        self.running = False
        self.btn_open.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

    # ---------------------------
    def process_queue(self):
        if not result_queue.empty():
            self.latest_entries = result_queue.get()
            self.update_treeview(self.latest_entries)
        self.root.after(200, self.process_queue)

    def update_treeview(self, entries):
        # Clear old Treeview
        for item in self.tree.get_children():
            self.tree.delete(item)

        current_ids = set([e['car_id'] for e in entries])
        previous_ids = set(self.car_states.keys())

        # Xe mới
        new_ids = current_ids - previous_ids
        for e in entries:
            tag = 'new_car' if e['car_id'] in new_ids else ''
            self.tree.insert('', tk.END, values=(e['car_id'], e['plate_text'] or '', e['ts']), tags=(tag,))
            self.car_states[e['car_id']] = 'present'

        # Xe rời đi
        left_ids = previous_ids - current_ids
        for car_id in left_ids:
            self.car_states[car_id] = 'left'

        # Loại bỏ xe rời đi sau 3s
        self.root.after(3000, self.remove_left_cars)

    def remove_left_cars(self):
        for item_id in self.tree.get_children():
            vals = self.tree.item(item_id, 'values')
            car_id = int(vals[0])
            if self.car_states.get(car_id) == 'left':
                self.tree.delete(item_id)
                del self.car_states[car_id]

    def on_row_selected(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if idx < 0 or idx >= len(self.latest_entries):
            return
        item = self.latest_entries[idx]
        # Preview
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

    # ---------------------------
    def video_loop(self):
        db = sqlite3.connect(DB_PATH)
        cur = db.cursor()
        cur.execute("""
                    CREATE TABLE IF NOT EXISTS plate_logs
                    (
                        id
                        INTEGER
                        PRIMARY
                        KEY
                        AUTOINCREMENT,
                        car_id
                        INTEGER,
                        plate
                        TEXT
                        UNIQUE,
                        car_path
                        TEXT,
                        plate_path
                        TEXT,
                        timestamp
                        TEXT
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

                # 1) Detect vehicles
                veh_results = vehicle_model(frame)[0]
                detections = []
                for box in veh_results.boxes:
                    try:
                        x1, y1, x2, y2 = bbox_to_ints(box.xyxy)
                    except:
                        x1, y1, x2, y2 = bbox_to_ints(box.xyxy[0])
                    conf = float(box.conf[0]) if hasattr(box.conf, "__getitem__") else float(box.conf)
                    if conf < 0.25:
                        continue
                    detections.append(([x1, y1, x2 - x1, y2 - y1], conf, None))

                # 2) Track
                tracks = tracker.update_tracks(detections, frame=frame)
                tracked_cars = []
                for t in tracks:
                    if not t.is_confirmed():
                        continue
                    tid = t.track_id
                    l, t_, r, b = t.to_ltrb()
                    x1, y1, x2, y2 = map(int, (l, t_, r, b))
                    tracked_cars.append((tid, x1, y1, x2, y2))

                # 3) Detect plates
                plate_results = plate_model(frame)[0]
                plate_bboxes = []
                for box in plate_results.boxes:
                    try:
                        px1, py1, px2, py2 = bbox_to_ints(box.xyxy)
                    except:
                        px1, py1, px2, py2 = bbox_to_ints(box.xyxy[0])
                    conf = float(box.conf[0]) if hasattr(box.conf, "__getitem__") else float(box.conf)
                    if conf < 0.25: continue
                    plate_bboxes.append((px1, py1, px2, py2))

                # 4) Match plate -> vehicle
                matches = []
                for pb in plate_bboxes:
                    pcx, pcy = centroid(pb)
                    for car_id, x1, y1, x2, y2 in tracked_cars:
                        if x1 <= pcx <= x2 and y1 <= pcy <= y2:
                            matches.append((car_id, pb))
                            break

                matched_car_ids = set([car_id for car_id, _ in matches])

                # 5) Highlight cars without plates
                overlay = frame.copy()
                alpha = 0.3
                for car_id, x1, y1, x2, y2 in tracked_cars:
                    if car_id not in matched_car_ids:
                        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), -1)  # fill red
                cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

                # 6) Draw bounding boxes and IDs
                for car_id, x1, y1, x2, y2 in tracked_cars:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"ID:{car_id}", (x1, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                (0, 255, 0), 2)

                for px1, py1, px2, py2 in plate_bboxes:
                    cv2.rectangle(frame, (px1, py1), (px2, py2), (255, 0, 0), 2)
                    cv2.putText(frame, "Plate", (px1, max(12, py1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

                # 7) Crop, OCR, save, push
                frame_entries = []
                for car_id, (px1, py1, px2, py2) in matches:
                    vb = next((v for v in tracked_cars if v[0] == car_id), None)
                    if vb is None: continue
                    _, vx1, vy1, vx2, vy2 = vb
                    car_crop = frame[vy1:vy2, vx1:vx2].copy()
                    plate_crop = frame[py1:py2, px1:px2].copy() if px2 > px1 and py2 > py1 else None

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
                        try:
                            plate_text_raw = ocr.run(cv2.cvtColor(plate_crop, cv2.COLOR_BGR2RGB))
                            plate_text = "".join(plate_text_raw) if isinstance(plate_text_raw, list) else plate_text_raw
                        except:
                            plate_text = None

                    # Save DB (unique plate)
                    try:
                        cur.execute("SELECT plate FROM plate_logs WHERE plate=?", (plate_text,))
                        if not cur.fetchone() and plate_text:
                            cur.execute("""INSERT INTO plate_logs
                                               (car_id, plate, car_path, plate_path, timestamp)
                                           VALUES (?, ?, ?, ?, ?)""",
                                        (car_id, plate_text, car_path, plate_path, ts))
                            db.commit()
                    except:
                        pass

                    frame_entries.append({
                        "car_id": car_id,
                        "plate_text": plate_text,
                        "car_path": car_path,
                        "plate_path": plate_path,
                        "ts": ts
                    })

                    if plate_text:
                        cv2.putText(frame, str(plate_text), (px1, max(12, py1 - 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                    (0, 255, 255), 2)

                # Push frame entries
                result_queue.put(frame_entries)
                cv2.imshow("Vehicle + Plate", frame)
                if cv2.waitKey(1) == 27:
                    self.running = False
                    break

        finally:
            try:
                db.close()
            except:
                pass
            try:
                cap.release()
            except:
                pass
            cv2.destroyAllWindows()
            self.running = False
            self.btn_open.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)


# ---------------------------
# Run
# ---------------------------
if __name__=="__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
