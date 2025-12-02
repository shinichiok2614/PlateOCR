import os
import shutil
import sqlite3
import threading
import queue
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import cv2
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort
from fast_plate_ocr import LicensePlateRecognizer
import numpy as np
# ==========================
# Config
# ==========================
VEHICLE_MODEL_PATH = "yolov8n-vehicle.pt"
PLATE_MODEL_PATH = "license_plate_detector.pt"
OCR_MODEL_NAME = "cct-xs-v1-global-model"
FACE_MODEL_PATH = "yolov8n_100e.pt"

SAVED_CARS = "saved_cars"
SAVED_PLATES = "saved_plates"
SAVED_FACES = "saved_faces"
DB_PATH = "parking.db"

os.makedirs(SAVED_CARS, exist_ok=True)
os.makedirs(SAVED_PLATES, exist_ok=True)
os.makedirs(SAVED_FACES, exist_ok=True)

vehicle_model = YOLO(VEHICLE_MODEL_PATH)
plate_model = YOLO(PLATE_MODEL_PATH)
face_model = YOLO(FACE_MODEL_PATH)
ocr = LicensePlateRecognizer(OCR_MODEL_NAME)
tracker = DeepSort(max_age=30, n_init=3, nn_budget=100)
result_queue = queue.Queue()

# ==========================
# Database
# ==========================
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
# Bảng log ra vào bãi
cur.execute("""
CREATE TABLE IF NOT EXISTS parking_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER,
    user_id INTEGER,
    in_time TEXT,
    out_time TEXT,
    status TEXT,
    car_image TEXT,
    plate_image TEXT,
    face_image TEXT
)
""")
# Bảng người/xe
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    phone TEXT,
    plate TEXT
)
""")
conn.commit()

# ==========================
# Utils
# ==========================
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

def save_face(face_img):
    folder = SAVED_FACES
    os.makedirs(folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{folder}/face_{timestamp}.jpg"
    cv2.imwrite(path, face_img)
    return path

# ==========================
# Main App
# ==========================
class ParkingApp:
    def __init__(self, root):
        self.root = root
        root.title("🚗 Quản lý Bãi Giữ Xe")
        root.geometry("1400x800")

        self.video_thread = None
        self.running = False
        self.cap = None
        self.current_video_path = None
        self.latest_entries = []
        self.car_states = {}

        # ---------------- Notebook ----------------
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Ra vào cổng
        self.tab_gate = ttk.Frame(self.nb)
        self.nb.add(self.tab_gate, text="Ra vào cổng")
        self.setup_tab_gate()

        # Tab 2: Bãi xe
        self.tab_parking = ttk.Frame(self.nb)
        self.nb.add(self.tab_parking, text="Bãi giữ xe")
        self.setup_tab_parking()

        # Tab 3: Quản lý cơ sở dữ liệu
        self.tab_db = ttk.Frame(self.nb)
        self.nb.add(self.tab_db, text="Cơ sở dữ liệu")
        self.setup_tab_db()

        # Poll queue
        self.root.after(200, self.process_queue)

    # ==========================
    # Tab Gate: Ra vào cổng
    # ==========================
    def setup_tab_gate(self):
        frame_top = tk.Frame(self.tab_gate)
        frame_top.pack(side=tk.TOP, fill=tk.X, pady=5)
        self.btn_open = tk.Button(frame_top, text="Chọn video / camera", command=self.select_and_start)
        self.btn_open.pack(side=tk.LEFT, padx=5)
        self.btn_stop = tk.Button(frame_top, text="Dừng", command=self.stop_video, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        frame_bottom = tk.Frame(self.tab_gate)
        frame_bottom.pack(fill=tk.BOTH, expand=True)

        # Preview
        self.preview_car = tk.Label(frame_bottom, text="Xe", relief=tk.SUNKEN)
        self.preview_car.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.preview_plate = tk.Label(frame_bottom, text="Biển số", relief=tk.SUNKEN)
        self.preview_plate.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.preview_face = tk.Label(frame_bottom, text="Khuôn mặt", relief=tk.SUNKEN)
        self.preview_face.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)

    # ==========================
    # Tab Parking: Bãi xe
    # ==========================
    def setup_tab_parking(self):
        columns = ("car_id","plate","status","in_time")
        self.tree_parking = ttk.Treeview(self.tab_parking, columns=columns, show="headings")
        for col in columns:
            self.tree_parking.heading(col, text=col)
        self.tree_parking.pack(fill=tk.BOTH, expand=True)
        self.update_parking_tree()

    def update_parking_tree(self):
        for item in self.tree_parking.get_children():
            self.tree_parking.delete(item)
        cur.execute("SELECT vehicle_id, plate_image, status, in_time FROM parking_logs WHERE status='IN'")
        rows = cur.fetchall()
        for r in rows:
            self.tree_parking.insert("", tk.END, values=r)
        self.root.after(5000, self.update_parking_tree)

    # ==========================
    # Tab DB: Quản lý cơ sở dữ liệu
    # ==========================
    def setup_tab_db(self):
        frame_top = tk.Frame(self.tab_db)
        frame_top.pack(fill=tk.X, pady=5)

        self.btn_add_user = tk.Button(frame_top, text="Thêm người/xe", command=self.add_user)
        self.btn_add_user.pack(side=tk.LEFT, padx=2)
        self.btn_refresh_db = tk.Button(frame_top, text="Tải lại", command=self.load_users)
        self.btn_refresh_db.pack(side=tk.LEFT, padx=2)

        # Treeview
        columns = ("id","name","phone","plate")
        self.tree_users = ttk.Treeview(self.tab_db, columns=columns, show="headings")
        for col in columns:
            self.tree_users.heading(col, text=col)
        self.tree_users.pack(fill=tk.BOTH, expand=True)
        self.load_users()

    def load_users(self):
        for item in self.tree_users.get_children():
            self.tree_users.delete(item)
        cur.execute("SELECT id,name,phone,plate FROM users")
        rows = cur.fetchall()
        for r in rows:
            self.tree_users.insert("", tk.END, values=r)

    def add_user(self):
        top = tk.Toplevel(self.root)
        top.title("Thêm người/xe")
        tk.Label(top, text="Tên").grid(row=0,column=0)
        tk.Label(top, text="SĐT").grid(row=1,column=0)
        tk.Label(top, text="Biển số").grid(row=2,column=0)
        e_name = tk.Entry(top); e_name.grid(row=0,column=1)
        e_phone = tk.Entry(top); e_phone.grid(row=1,column=1)
        e_plate = tk.Entry(top); e_plate.grid(row=2,column=1)
        def save():
            cur.execute("INSERT INTO users (name,phone,plate) VALUES (?,?,?)",
                        (e_name.get(),e_phone.get(),e_plate.get()))
            conn.commit()
            self.load_users()
            top.destroy()
        tk.Button(top, text="Lưu", command=save).grid(row=3,column=0,columnspan=2)

    # ==========================
    # Video controls
    # ==========================
    def select_and_start(self):
        path = filedialog.askopenfilename(title="Chọn video",
                                          filetypes=[("Video files","*.mp4 *.avi *.mov *.mkv"),("All files","*.*")])
        self.current_video_path = path if path else None
        self.start_video()

    def start_video(self):
        if self.running:
            messagebox.showinfo("Thông báo", "Video đang chạy")
            return
        cap = cv2.VideoCapture(self.current_video_path) if self.current_video_path else cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("Lỗi","Không mở được video/camera")
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

    def process_queue(self):
        if not result_queue.empty():
            self.latest_entries = result_queue.get()
            self.update_preview(self.latest_entries[-1])
        self.root.after(200, self.process_queue)

    def update_preview(self, entry):
        # Car
        if entry.get("car_path") and os.path.exists(entry["car_path"]):
            im = Image.open(entry["car_path"]); im.thumbnail((400,200))
            self.preview_car.config(image=ImageTk.PhotoImage(im), text=""); self.preview_car.image = im
        # Plate
        if entry.get("plate_path") and os.path.exists(entry["plate_path"]):
            im = Image.open(entry["plate_path"]); im.thumbnail((400,150))
            self.preview_plate.config(image=ImageTk.PhotoImage(im), text=""); self.preview_plate.image = im
        # Face
        if entry.get("face_path") and os.path.exists(entry["face_path"]):
            im = Image.open(entry["face_path"]); im.thumbnail((400,150))
            self.preview_face.config(image=ImageTk.PhotoImage(im), text=""); self.preview_face.image = im

    # ==========================
    # Video loop
    # ==========================
    def video_loop(self):
        cap = self.cap
        db = sqlite3.connect(DB_PATH)
        cur = db.cursor()
        try:
            while self.running:
                ret, frame = cap.read()
                if not ret: break
                # Vehicle detection
                veh_results = vehicle_model(frame)[0]
                detections = []
                for box in veh_results.boxes:
                    x1,y1,x2,y2 = bbox_to_ints(box.xyxy)
                    conf = float(box.conf[0]) if hasattr(box.conf,"__getitem__") else float(box.conf)
                    if conf<0.25: continue
                    detections.append(([x1,y1,x2-x1,y2-y1], conf, None))
                # Tracking
                tracks = tracker.update_tracks(detections, frame=frame)
                tracked_cars = [(t.track_id,*map(int,t.to_ltrb())) for t in tracks if t.is_confirmed()]
                # Plate detection
                plate_results = plate_model(frame)[0]
                plate_bboxes = []
                for box in plate_results.boxes:
                    px1,py1,px2,py2 = bbox_to_ints(box.xyxy)
                    conf = float(box.conf[0]) if hasattr(box.conf,"__getitem__") else float(box.conf)
                    if conf<0.25: continue
                    plate_bboxes.append((px1,py1,px2,py2))
                # Match plates
                matches = []
                for pb in plate_bboxes:
                    pcx,pcy = centroid(pb)
                    for car_id,x1,y1,x2,y2 in tracked_cars:
                        if x1<=pcx<=x2 and y1<=pcy<=y2:
                            matches.append((car_id,pb)); break
                frame_entries=[]
                for car_id,(px1,py1,px2,py2) in matches:
                    vb = next((v for v in tracked_cars if v[0]==car_id), None)
                    if vb is None: continue
                    _,vx1,vy1,vx2,vy2 = vb
                    car_crop = frame[vy1:vy2, vx1:vx2].copy()
                    plate_crop = frame[py1:py2, px1:px2].copy() if px2>px1 and py2>py1 else None
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    car_path = os.path.join(SAVED_CARS,f"car_{car_id}_{ts}.jpg")
                    cv2.imwrite(car_path, car_crop)
                    plate_path, plate_text = None, None
                    if plate_crop is not None:
                        plate_path=os.path.join(SAVED_PLATES,f"plate_{car_id}_{ts}.jpg")
                        cv2.imwrite(plate_path, plate_crop)
                        try:
                            plate_text_raw = ocr.run(cv2.cvtColor(plate_crop,cv2.COLOR_BGR2RGB))
                            plate_text="".join(plate_text_raw) if isinstance(plate_text_raw,list) else plate_text_raw
                        except: plate_text=None
                    face_path = None
                    # Save DB
                    try:
                        if plate_text:
                            # kiểm tra user
                            cur.execute("SELECT id FROM users WHERE plate=?",(plate_text,))
                            row=cur.fetchone()
                            user_id=row[0] if row else None
                            status='IN'
                            cur.execute("""INSERT INTO parking_logs
                                           (vehicle_id,user_id,in_time,status,car_image,plate_image,face_image)
                                           VALUES (?,?,?,?,?,?,?)""",
                                        (car_id,user_id,ts,status,car_path,plate_path,face_path))
                            db.commit()
                    except: pass
                    frame_entries.append({"car_path":car_path,"plate_path":plate_path,"face_path":face_path})
                result_queue.put(frame_entries)
                cv2.imshow("Video",frame)
                if cv2.waitKey(1)==27:
                    self.running=False
                    break
        finally:
            try: db.close()
            except: pass
            try: cap.release()
            except: pass
            cv2.destroyAllWindows()
            self.running=False
            self.btn_open.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)

if __name__=="__main__":
    root=tk.Tk()
    app=ParkingApp(root)
    root.mainloop()
    conn.close()
