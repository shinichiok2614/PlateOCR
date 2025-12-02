import os
import cv2
import shutil
import queue
import threading
import sqlite3
import numpy as np
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort
from fast_plate_ocr import LicensePlateRecognizer

# ==========================
# Config
# ==========================
VEHICLE_MODEL_GATE = "yolov8n-vehicle.pt"
PLATE_MODEL = "license_plate_detector.pt"
FACE_MODEL = "yolov8n_100e.pt"
OCR_MODEL_NAME = "cct-xs-v1-global-model"

SAVED_CARS = "saved_cars"
SAVED_PLATES = "saved_plates"
SAVED_FACES = "saved_faces"
DB_PATH = "parking.db"

os.makedirs(SAVED_CARS, exist_ok=True)
os.makedirs(SAVED_PLATES, exist_ok=True)
os.makedirs(SAVED_FACES, exist_ok=True)

vehicle_model_gate = YOLO(VEHICLE_MODEL_GATE)
vehicle_model_parking = YOLO(VEHICLE_MODEL_GATE)
plate_model = YOLO(PLATE_MODEL)
face_model = YOLO(FACE_MODEL)
ocr = LicensePlateRecognizer(OCR_MODEL_NAME)
tracker = DeepSort(max_age=30, n_init=3, nn_budget=100)
result_queue_gate = queue.Queue()
result_queue_parking = queue.Queue()

# ==========================
# Database
# ==========================
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Log ra vào cổng
cur.execute("""
CREATE TABLE IF NOT EXISTS gate_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER,
    user_id INTEGER,
    timestamp TEXT,
    status TEXT,
    car_image TEXT,
    plate_image TEXT,
    face_image TEXT
)
""")
# Log xe trong bãi
cur.execute("""
CREATE TABLE IF NOT EXISTS parking_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER,
    plate TEXT,
    car_image TEXT,
    plate_image TEXT,
    face_image TEXT,
    timestamp TEXT,
    status TEXT
)
""")
# Người/xe cố định
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
    except:
        a = np.array(xy)
        if a.size>=4:
            x1, y1, x2, y2 = map(int,a.flatten()[:4])
            return x1, y1, x2, y2
        raise

def centroid(box):
    x1, y1, x2, y2 = box
    return ((x1+x2)/2, (y1+y2)/2)

def save_face(face_img):
    folder = SAVED_FACES
    os.makedirs(folder, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{folder}/face_{ts}.jpg"
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

        self.cap_gate = None
        self.cap_parking = None
        self.running_gate = False
        self.running_parking = False
        self.car_states = {}

        # ---------------- Notebook ----------------
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Gate
        self.tab_gate = ttk.Frame(self.nb)
        self.nb.add(self.tab_gate, text="Ra vào cổng")
        self.setup_tab_gate()

        # Tab 2: Parking Detection
        self.tab_parking_detect = ttk.Frame(self.nb)
        self.nb.add(self.tab_parking_detect, text="Nhận diện xe trong bãi")
        self.setup_tab_parking_detect()

        # Tab 3: Bãi giữ xe
        self.tab_parking = ttk.Frame(self.nb)
        self.nb.add(self.tab_parking, text="Bãi giữ xe")
        self.setup_tab_parking()

        # Tab 4: CSDL cố định
        self.tab_db = ttk.Frame(self.nb)
        self.nb.add(self.tab_db, text="Quản lý cơ sở dữ liệu")
        self.setup_tab_db()

        # Poll queues
        self.root.after(200, self.process_queue_gate)
        self.root.after(200, self.process_queue_parking)

    # ==========================
    # Tab 1: Gate
    # ==========================
    def setup_tab_gate(self):
        frame_top = tk.Frame(self.tab_gate)
        frame_top.pack(side=tk.TOP, fill=tk.X, pady=5)
        self.btn_open_gate = tk.Button(frame_top, text="Chọn video/camera", command=self.select_and_start_gate)
        self.btn_open_gate.pack(side=tk.LEFT, padx=5)
        self.btn_stop_gate = tk.Button(frame_top, text="Dừng", command=self.stop_gate, state=tk.DISABLED)
        self.btn_stop_gate.pack(side=tk.LEFT, padx=5)

        frame_bottom = tk.Frame(self.tab_gate)
        frame_bottom.pack(fill=tk.BOTH, expand=True)
        self.preview_car_gate = tk.Label(frame_bottom, text="Xe", relief=tk.SUNKEN)
        self.preview_car_gate.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.preview_plate_gate = tk.Label(frame_bottom, text="Biển số", relief=tk.SUNKEN)
        self.preview_plate_gate.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.preview_face_gate = tk.Label(frame_bottom, text="Khuôn mặt", relief=tk.SUNKEN)
        self.preview_face_gate.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)

    # ==========================
    # Tab 2: Parking Detection
    # ==========================
    def setup_tab_parking_detect(self):
        frame_top = tk.Frame(self.tab_parking_detect)
        frame_top.pack(side=tk.TOP, fill=tk.X, pady=5)
        self.btn_open_parking = tk.Button(frame_top, text="Chọn video/camera", command=self.select_and_start_parking)
        self.btn_open_parking.pack(side=tk.LEFT, padx=5)
        self.btn_stop_parking = tk.Button(frame_top, text="Dừng", command=self.stop_parking, state=tk.DISABLED)
        self.btn_stop_parking.pack(side=tk.LEFT, padx=5)

        self.frame_preview_parking = tk.Frame(self.tab_parking_detect)
        self.frame_preview_parking.pack(fill=tk.BOTH, expand=True)
        self.preview_car_parking = tk.Label(self.frame_preview_parking, text="Xe")
        self.preview_car_parking.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.preview_plate_parking = tk.Label(self.frame_preview_parking, text="Biển số")
        self.preview_plate_parking.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.preview_face_parking = tk.Label(self.frame_preview_parking, text="Khuôn mặt")
        self.preview_face_parking.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # ==========================
    # Tab 3: Parking Logs
    # ==========================
    def setup_tab_parking(self):
        columns = ("vehicle_id","plate","status","timestamp")
        self.tree_parking = ttk.Treeview(self.tab_parking, columns=columns, show="headings")
        for col in columns:
            self.tree_parking.heading(col, text=col)
        self.tree_parking.pack(fill=tk.BOTH, expand=True)
        self.update_parking_tree()

    def update_parking_tree(self):
        for item in self.tree_parking.get_children():
            self.tree_parking.delete(item)
        cur.execute("SELECT vehicle_id, plate, status, timestamp FROM parking_logs WHERE status='IN'")
        rows = cur.fetchall()
        for r in rows:
            self.tree_parking.insert("", tk.END, values=r)
        self.root.after(5000, self.update_parking_tree)

    # ==========================
    # Tab 4: User DB
    # ==========================
    def setup_tab_db(self):
        frame_top = tk.Frame(self.tab_db)
        frame_top.pack(fill=tk.X, pady=5)
        self.btn_add_user = tk.Button(frame_top, text="Thêm người/xe", command=self.add_user)
        self.btn_add_user.pack(side=tk.LEFT, padx=2)
        self.btn_refresh_db = tk.Button(frame_top, text="Tải lại", command=self.load_users)
        self.btn_refresh_db.pack(side=tk.LEFT, padx=2)

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
    # Gate video
    # ==========================
    def select_and_start_gate(self):
        path = filedialog.askopenfilename(title="Chọn video/camera",
                                          filetypes=[("Video files","*.*")])
        self.cap_gate = cv2.VideoCapture(path) if path else cv2.VideoCapture(0)
        if not self.cap_gate.isOpened():
            messagebox.showerror("Lỗi","Không mở được camera/video")
            return
        self.running_gate = True
        self.btn_open_gate.config(state=tk.DISABLED)
        self.btn_stop_gate.config(state=tk.NORMAL)
        threading.Thread(target=self.video_loop_gate, daemon=True).start()

    def stop_gate(self):
        self.running_gate = False
        self.btn_open_gate.config(state=tk.NORMAL)
        self.btn_stop_gate.config(state=tk.DISABLED)

    def process_queue_gate(self):
        if not result_queue_gate.empty():
            entry = result_queue_gate.get()
            # Update preview
            if entry.get("car_path"):
                im = Image.open(entry["car_path"]); im.thumbnail((400,200))
                self.preview_car_gate.config(image=ImageTk.PhotoImage(im)); self.preview_car_gate.image = im
            if entry.get("plate_path"):
                im = Image.open(entry["plate_path"]); im.thumbnail((400,150))
                self.preview_plate_gate.config(image=ImageTk.PhotoImage(im)); self.preview_plate_gate.image = im
            if entry.get("face_path"):
                im = Image.open(entry["face_path"]); im.thumbnail((400,150))
                self.preview_face_gate.config(image=ImageTk.PhotoImage(im)); self.preview_face_gate.image = im
        self.root.after(200, self.process_queue_gate)

    # ==========================
    # Parking video
    # ==========================
    def select_and_start_parking(self):
        path = filedialog.askopenfilename(title="Chọn video/camera",
                                          filetypes=[("Video files","*.*")])
        self.cap_parking = cv2.VideoCapture(path) if path else cv2.VideoCapture(0)
        if not self.cap_parking.isOpened():
            messagebox.showerror("Lỗi","Không mở được camera/video")
            return
        self.running_parking = True
        self.btn_open_parking.config(state=tk.DISABLED)
        self.btn_stop_parking.config(state=tk.NORMAL)
        threading.Thread(target=self.video_loop_parking, daemon=True).start()

    def stop_parking(self):
        self.running_parking = False
        self.btn_open_parking.config(state=tk.NORMAL)
        self.btn_stop_parking.config(state=tk.DISABLED)

    def process_queue_parking(self):
        if not result_queue_parking.empty():
            entry = result_queue_parking.get()
            if entry.get("car_path"):
                im = Image.open(entry["car_path"]); im.thumbnail((400,200))
                self.preview_car_parking.config(image=ImageTk.PhotoImage(im)); self.preview_car_parking.image = im
            if entry.get("plate_path"):
                im = Image.open(entry["plate_path"]); im.thumbnail((400,150))
                self.preview_plate_parking.config(image=ImageTk.PhotoImage(im)); self.preview_plate_parking.image = im
            if entry.get("face_path"):
                im = Image.open(entry["face_path"]); im.thumbnail((400,150))
                self.preview_face_parking.config(image=ImageTk.PhotoImage(im)); self.preview_face_parking.image = im
        self.root.after(200, self.process_queue_parking)

    # ==========================
    # Video loops (chi tiết nhận diện + OCR)
    # ==========================
    def video_loop_gate(self):
        cap = self.cap_gate
        db = sqlite3.connect(DB_PATH)
        cur = db.cursor()
        while self.running_gate:
            ret, frame = cap.read()
            if not ret: break
            # TODO: nhận diện xe + face + OCR, lưu vào gate_logs
            # Sau khi xử lý xong push dict vào result_queue_gate
        cap.release()

    def video_loop_parking(self):
        cap = self.cap_parking
        db = sqlite3.connect(DB_PATH)
        cur = db.cursor()
        while self.running_parking:
            ret, frame = cap.read()
            if not ret: break
            # TODO: nhận diện xe trong bãi + OCR, lưu vào parking_logs
            # Sau khi xử lý xong push dict vào result_queue_parking
        cap.release()

if __name__=="__main__":
    root=tk.Tk()
    app=ParkingApp(root)
    root.mainloop()
    conn.close()
