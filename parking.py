import os
import cv2
import queue
import threading
import sqlite3
import numpy as np
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from datetime import datetime, date
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort
from fast_plate_ocr import LicensePlateRecognizer
from PIL import Image, ImageTk
import csv

# ---------------- Config ----------------
VEHICLE_MODEL_PATH = "yolov8n-vehicle.pt"
PLATE_MODEL_PATH = "license_plate_detector.pt"
FACE_MODEL_PATH = "yolov8n_100e.pt"
OCR_MODEL_NAME = "cct-xs-v1-global-model"

DATA_DIR = "data_parking"
SAVED_CARS = os.path.join(DATA_DIR, "cars")
SAVED_PLATES = os.path.join(DATA_DIR, "plates")
SAVED_FACES = os.path.join(DATA_DIR, "faces")
DB_PATH = os.path.join(DATA_DIR, "parking.db")

os.makedirs(SAVED_CARS, exist_ok=True)
os.makedirs(SAVED_PLATES, exist_ok=True)
os.makedirs(SAVED_FACES, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------- Load Models ----------------
vehicle_model = YOLO(VEHICLE_MODEL_PATH)
plate_model = YOLO(PLATE_MODEL_PATH)
face_model = YOLO(FACE_MODEL_PATH)
ocr = LicensePlateRecognizer(OCR_MODEL_NAME)
tracker = DeepSort(max_age=30, n_init=3, nn_budget=100)

# ---------------- Thread-safe queue ----------------
result_queue = queue.Queue()

# ---------------- Database ----------------
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    unit TEXT,
    face_path TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate TEXT UNIQUE,
    owner_id INTEGER,
    type TEXT,
    FOREIGN KEY(owner_id) REFERENCES users(user_id)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS parking_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER,
    user_id INTEGER,
    in_time TEXT,
    out_time TEXT,
    status TEXT, -- 'in' hoặc 'out'
    car_image TEXT,
    plate_image TEXT,
    face_image TEXT,
    FOREIGN KEY(vehicle_id) REFERENCES vehicles(vehicle_id),
    FOREIGN KEY(user_id) REFERENCES users(user_id)
)
""")
conn.commit()

# ---------------- Utilities ----------------
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
    x1, y1, x2, y2 = box
    return ((x1+x2)/2, (y1+y2)/2)

def save_image(img, folder, prefix):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{ts}.jpg"
    path = os.path.join(folder, filename)
    cv2.imwrite(path, img)
    return path

# ---------------- Tkinter GUI ----------------
class ParkingApp:
    def __init__(self, root):
        self.root = root
        root.title("🚗 Quản lý Bãi Giữ Xe")
        root.geometry("1500x800")

        # -------- Left Frame: Treeview + Buttons --------
        left_frame = tk.Frame(root, width=400)
        left_frame.pack(side=tk.LEFT, fill=tk.Y)

        # Buttons
        btn_frame = tk.Frame(left_frame)
        btn_frame.pack(pady=6)
        self.btn_open = tk.Button(btn_frame, text="Chọn video / camera", command=self.select_and_start)
        self.btn_open.pack(side=tk.LEFT, padx=6)
        self.btn_stop = tk.Button(btn_frame, text="Dừng", command=self.stop_video, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=6)
        self.btn_report = tk.Button(btn_frame, text="Báo cáo CSV hôm nay", command=self.export_csv)
        self.btn_report.pack(side=tk.LEFT, padx=6)

        # Treeview
        columns = ("plate", "owner", "status", "in_time", "out_time")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=40)
        for col in columns:
            self.tree.heading(col, text=col)
        self.tree.column("plate", width=120)
        self.tree.column("owner", width=150)
        self.tree.column("status", width=60)
        self.tree.column("in_time", width=140)
        self.tree.column("out_time", width=140)
        self.tree.pack(fill=tk.Y, expand=True, pady=6)
        self.tree.bind("<<TreeviewSelect>>", self.on_row_selected)
        self.tree.tag_configure('in', background='lightgreen')
        self.tree.tag_configure('out', background='lightcoral')

        # -------- Right Frame: Image Preview --------
        right_frame = tk.Frame(root)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        preview_frame = tk.Frame(right_frame)
        preview_frame.pack(fill=tk.BOTH, expand=True)

        self.preview_car = tk.Label(preview_frame, text="Car image", relief=tk.SUNKEN)
        self.preview_car.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.preview_plate = tk.Label(preview_frame, text="Plate image", relief=tk.SUNKEN)
        self.preview_plate.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.preview_face = tk.Label(preview_frame, text="Face image", relief=tk.SUNKEN)
        self.preview_face.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)

        # -------- Internal state --------
        self.video_thread = None
        self.running = False
        self.cap = None
        self.current_video_path = None
        self.latest_entries = []
        self.car_states = {}

        # Poll queue
        self.root.after(200, self.process_queue)

    # ---------------- Video controls ----------------
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

    # ---------------- Treeview update ----------------
    def process_queue(self):
        if not result_queue.empty():
            self.latest_entries = result_queue.get()
            self.update_treeview(self.latest_entries)
        self.root.after(200, self.process_queue)

    def update_treeview(self, entries):
        self.tree.delete(*self.tree.get_children())
        for e in entries:
            tag = 'in' if e['status']=='in' else 'out'
            self.tree.insert('', tk.END, values=(e['plate'], e['owner'], e['status'], e['in_time'], e['out_time']), tags=(tag,))
            self.car_states[e['plate']] = e['status']

    # ---------------- Row selection preview ----------------
    def on_row_selected(self, event=None):
        sel = self.tree.selection()
        if not sel: return
        idx = self.tree.index(sel[0])
        if idx < 0 or idx >= len(self.latest_entries): return
        item = self.latest_entries[idx]
        self.show_preview(self.preview_car, item.get("car_path"), (400,200))
        self.show_preview(self.preview_plate, item.get("plate_path"), (400,150))
        self.show_preview(self.preview_face, item.get("face_path"), (400,150))

    def show_preview(self, label, path, size):
        if path and os.path.exists(path):
            im = Image.open(path)
            im.thumbnail(size)
            tkim = ImageTk.PhotoImage(im)
            label.config(image=tkim, text="")
            label.image = tkim
        else:
            label.config(image="", text="Không có ảnh")
            label.image = None

    # ---------------- CSV Report ----------------
    def export_csv(self):
        today = date.today().strftime("%Y%m%d")
        cur.execute("SELECT plate, name, status, in_time, out_time FROM parking_logs "
                    "LEFT JOIN vehicles ON vehicles.vehicle_id=parking_logs.vehicle_id "
                    "LEFT JOIN users ON users.user_id=parking_logs.user_id "
                    "WHERE in_time LIKE ? OR out_time LIKE ?", (today+'%', today+'%'))
        rows = cur.fetchall()
        if not rows:
            messagebox.showinfo("Báo cáo", "Không có dữ liệu hôm nay")
            return
        save_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files","*.csv")])
        if not save_path: return
        with open(save_path, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Plate","Owner","Status","In Time","Out Time"])
            writer.writerows(rows)
        messagebox.showinfo("Báo cáo", f"Đã xuất CSV: {save_path}")

    # ---------------- Video processing ----------------
    def video_loop(self):
        cap = self.cap
        try:
            while self.running:
                ret, frame = cap.read()
                if not ret: break

                # --- Vehicle detection ---
                veh_results = vehicle_model(frame)[0]
                detections = []
                for box in veh_results.boxes:
                    try: x1, y1, x2, y2 = bbox_to_ints(box.xyxy)
                    except: x1, y1, x2, y2 = bbox_to_ints(box.xyxy[0])
                    conf = float(box.conf[0]) if hasattr(box.conf,"__getitem__") else float(box.conf)
                    if conf<0.25: continue
                    detections.append(([x1, y1, x2-x1, y2-y1], conf, None))

                # --- Tracking ---
                tracks = tracker.update_tracks(detections, frame=frame)
                tracked_cars = [(t.track_id,*map(int,t.to_ltrb())) for t in tracks if t.is_confirmed()]

                # --- Plate detection ---
                plate_results = plate_model(frame)[0]
                plate_bboxes = []
                for box in plate_results.boxes:
                    try: px1, py1, px2, py2 = bbox_to_ints(box.xyxy)
                    except: px1, py1, px2, py2 = bbox_to_ints(box.xyxy[0])
                    conf = float(box.conf[0]) if hasattr(box.conf,"__getitem__") else float(box.conf)
                    if conf<0.25: continue
                    plate_bboxes.append((px1, py1, px2, py2))

                # --- Match plates to cars ---
                matches = []
                for pb in plate_bboxes:
                    pcx, pcy = centroid(pb)
                    for car_id, x1, y1, x2, y2 in tracked_cars:
                        if x1 <= pcx <= x2 and y1 <= pcy <= y2:
                            matches.append((car_id, pb))
                            break

                frame_entries = []
                for car_id, (px1, py1, px2, py2) in matches:
                    vb = next((v for v in tracked_cars if v[0]==car_id), None)
                    if vb is None: continue
                    _, vx1, vy1, vx2, vy2 = vb
                    car_crop = frame[vy1:vy2, vx1:vx2].copy()
                    plate_crop = frame[py1:py2, px1:px2].copy() if px2>px1 and py2>py1 else None

                    # --- OCR ---
                    plate_text=None
                    plate_path=None
                    if plate_crop is not None and plate_crop.size>0:
                        plate_path = save_image(plate_crop, SAVED_PLATES, f"plate_{car_id}")
                        try:
                            plate_text_raw = ocr.run(cv2.cvtColor(plate_crop, cv2.COLOR_BGR2RGB))
                            plate_text="".join(plate_text_raw) if isinstance(plate_text_raw,list) else plate_text_raw
                        except: plate_text=None

                    car_path = save_image(car_crop, SAVED_CARS, f"car_{car_id}")

                    # --- Face detection ---
                    face_path=None
                    face_results = face_model(frame)[0]
                    for f in face_results.boxes:
                        try: fx1, fy1, fx2, fy2 = bbox_to_ints(f.xyxy)
                        except: fx1, fy1, fx2, fy2 = bbox_to_ints(f.xyxy[0])
                        face_crop = frame[fy1:fy2, fx1:fx2].copy()
                        if face_crop.size>0:
                            face_path = save_image(face_crop, SAVED_FACES, f"face_{car_id}")
                            break

                    # --- Update DB ---
                    vehicle_id=None
                    user_id=None
                    if plate_text:
                        # Vehicle
                        cur.execute("SELECT vehicle_id, owner_id FROM vehicles WHERE plate=?",(plate_text,))
                        row = cur.fetchone()
                        if row:
                            vehicle_id, user_id=row
                        else:
                            cur.execute("INSERT INTO vehicles (plate) VALUES (?)",(plate_text,))
                            vehicle_id = cur.lastrowid

                        # Check existing log
                        cur.execute("SELECT log_id, status FROM parking_logs WHERE vehicle_id=? AND status='in'", (vehicle_id,))
                        row = cur.fetchone()
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        if row:  # xe đang trong bãi, đánh dấu vẫn ở trong
                            log_id, status = row
                            status='in'
                            cur.execute("UPDATE parking_logs SET car_image=?, plate_image=?, face_image=? WHERE log_id=?",
                                        (car_path, plate_path, face_path, log_id))
                        else:  # xe mới vào
                            status='in'
                            cur.execute("""INSERT INTO parking_logs
                                           (vehicle_id, user_id, in_time, status, car_image, plate_image, face_image)
                                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                        (vehicle_id, user_id, ts, status, car_path, plate_path, face_path))

                        conn.commit()

                        frame_entries.append({
                            "plate": plate_text,
                            "owner": "Unknown" if not user_id else "User#"+str(user_id),
                            "status": status,
                            "in_time": ts,
                            "out_time": "" if status=='in' else ts,
                            "car_path": car_path,
                            "plate_path": plate_path,
                            "face_path": face_path
                        })

                result_queue.put(frame_entries)

                # --- Display frame ---
                for car_id, x1, y1, x2, y2 in tracked_cars:
                    cv2.rectangle(frame,(x1,y1),(x2,y2),(0,255,0),2)
                    cv2.putText(frame,f"ID:{car_id}",(x1,max(12,y1-6)),cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,255,0),2)
                for px1,py1,px2,py2 in plate_bboxes:
                    cv2.rectangle(frame,(px1,py1),(px2,py2),(255,0,0),2)
                    cv2.putText(frame,"Plate",(px1,max(12,py1-6)),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,0,0),2)

                cv2.imshow("Parking Camera", frame)
                if cv2.waitKey(1)==27:
                    self.running=False
                    break
        finally:
            try: cap.release()
            except: pass
            cv2.destroyAllWindows()
            self.running=False
            self.btn_open.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)

# ---------------- Main ----------------
if __name__=="__main__":
    root=tk.Tk()
    app=ParkingApp(root)
    root.mainloop()
    conn.close()
