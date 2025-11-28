import os
import shutil
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import cv2
from datetime import datetime
from ultralytics import YOLO

model = YOLO("license_plate_detector.pt")
face_model = YOLO("yolov8n_100e.pt")

# ==============================
#  Khởi tạo database
# ==============================
conn = sqlite3.connect("images.db")
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS images
    (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        path TEXT,
        zoom_path TEXT,
        timestamp TEXT,
        face_path TEXT
    )
""")
conn.commit()

# ==============================
#  App Tkinter
# ==============================
root = tk.Tk()
root.title("Quản lý ảnh")
root.geometry("1100x500")

# ========== FRAME TRÁI: TREEVIEW + NÚT ==========
left_frame = tk.Frame(root)
left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

# ========== FRAME GIỮA: ẢNH PLATE ZOOM ==========
center_frame = tk.Frame(root, bg="#202020")
center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

label_zoom = tk.Label(center_frame, bg="#202020")
label_zoom.pack(pady=10)

# ========== FRAME PHẢI: ẢNH KHUÔN MẶT ==========
right_frame = tk.Frame(root, bg="#202020")
right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

label_face = tk.Label(right_frame, bg="#202020")
label_face.pack(pady=10)


# ========== TREEVIEW ==========
columns = ("name", "timestamp", "zoom", "face")
tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=18)
tree.heading("name", text="Tên ảnh")
tree.heading("timestamp", text="Ngày giờ")
tree.heading("zoom", text="Zoom")
tree.heading("face", text="Face")

tree.column("name", width=120)
tree.column("timestamp", width=120)
tree.column("zoom", width=80)
tree.column("face", width=80)
tree.pack()


# ========== HIỂN THỊ ẢNH ==========
def show_zoom_image(path):
    if not path or not os.path.exists(path):
        label_zoom.config(image="", text="Không có ảnh zoom")
        return

    img = Image.open(path)
    img.thumbnail((400, 350))
    tk_img = ImageTk.PhotoImage(img)

    label_zoom.config(image=tk_img)
    label_zoom.image = tk_img


def show_face_image(path):
    if not path or not os.path.exists(path):
        label_face.config(image="", text="Không có ảnh mặt")
        return

    img = Image.open(path)
    img.thumbnail((280, 280))
    tk_img = ImageTk.PhotoImage(img)

    label_face.config(image=tk_img)
    label_face.image = tk_img


# ==============================
#  Chọn 1 hàng → Hiển thị ảnh
# ==============================
def view_selected(event=None):
    selected = tree.selection()
    if not selected:
        return

    values = tree.item(selected[0])["values"]
    name = values[0]

    cur.execute("SELECT path, zoom_path, face_path FROM images WHERE name=?", (name,))
    row = cur.fetchone()
    if not row:
        return

    img_path, zoom_path, face_path = row

    # hiển thị zoom
    show_zoom_image(zoom_path)
    # hiển thị khuôn mặt
    show_face_image(face_path)


tree.bind("<<TreeviewSelect>>", view_selected)
tree.bind("<Double-1>", view_selected)


# ==============================
#  Load danh sách
# ==============================
def load_images():
    for row in tree.get_children():
        tree.delete(row)

    cur.execute("SELECT name, timestamp, zoom_path, face_path FROM images ORDER BY id DESC")
    rows = cur.fetchall()

    for name, timestamp, zoom_path, face_path in rows:
        tree.insert("", tk.END, values=(
            name,
            timestamp if timestamp else "",
            "OK" if zoom_path else "Không",
            "OK" if face_path else "Không"
        ))


load_images()


# ==============================
#  Thêm ảnh thủ công
# ==============================
def add_image():
    filepath = filedialog.askopenfilename(
        filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif")]
    )
    if not filepath:
        return

    os.makedirs("images", exist_ok=True)
    filename = os.path.basename(filepath)
    new_path = os.path.join("images", filename)

    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(new_path):
        new_path = os.path.join("images", f"{base}_{counter}{ext}")
        counter += 1

    shutil.copy(filepath, new_path)

    cur.execute("INSERT INTO images (name, path) VALUES (?, ?)",
                (os.path.basename(new_path), new_path))
    conn.commit()
    load_images()
    messagebox.showinfo("OK", "Đã thêm ảnh!")


# ==============================
#  Xem ảnh lớn
# ==============================
def open_viewer(path):
    if not path:
        return
    viewer = tk.Toplevel()
    viewer.title("Xem ảnh")
    img = Image.open(path)
    img.thumbnail((800, 600))
    tk_img = ImageTk.PhotoImage(img)
    lbl = tk.Label(viewer, image=tk_img)
    lbl.image = tk_img
    lbl.pack()


# ==============================
#  Lưu ảnh khuôn mặt
# ==============================
def save_face(face_img):
    folder = "data_faces"
    os.makedirs(folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{folder}/face_{timestamp}.jpg"
    cv2.imwrite(path, face_img)

    cur.execute("UPDATE images SET face_path=? WHERE id=(SELECT MAX(id) FROM images)", (path,))
    conn.commit()


# ==============================
#  Chụp khuôn mặt
# ==============================
def capture_face_window():
    cap = cv2.VideoCapture(0)
    cv2.namedWindow("Face Capture", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Face Capture", 800, 600)

    face_crop = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = face_model(frame, conf=0.5)

        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0,255,0), 2)
                face_crop = frame[y1:y2, x1:x2]

        cv2.imshow("Face Capture", frame)

        key = cv2.waitKey(1)
        if key == 32:  # SPACE
            if face_crop is not None:
                save_face(face_crop)
                load_images()
                messagebox.showinfo("OK", "Đã lưu khuôn mặt!")
            break
        elif key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


# ==============================
#  Camera + YOLO Plate
# ==============================
def open_camera_yolo(use_video=False):
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    max_w = int(screen_w * 0.8)
    max_h = int(screen_h * 0.8)

    if use_video:
        path = filedialog.askopenfilename(filetypes=[("Video files", "*.*")])
        if not path:
            return
        cap = cv2.VideoCapture(path)
    else:
        cap = cv2.VideoCapture(0)

    cv2.namedWindow("Camera/Video", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Plate Zoom", cv2.WINDOW_AUTOSIZE)

    zoom_img = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model(frame)[0]

        for r in results.boxes:
            x1, y1, x2, y2 = map(int, r.xyxy[0])
            conf = float(r.conf[0])
            if conf < 0.5:
                continue

            crop = frame[y1:y2, x1:x2]
            if crop.size > 0:
                zoom_img = cv2.resize(crop, None, fx=3.5, fy=3.5)

            break

        if zoom_img is not None:
            h, w = zoom_img.shape[:2]
            scale = min(max_w / w, max_h / h, 1.0)
            zoom_resized = cv2.resize(zoom_img, (int(w*scale), int(h*scale)))
            cv2.imshow("Plate Zoom", zoom_resized)

        cv2.imshow("Camera/Video", frame)

        key = cv2.waitKey(1)
        if key == 32:  # SPACE
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_dir = "images/captured"
            os.makedirs(save_dir, exist_ok=True)

            filename = f"frame_{timestamp}.jpg"
            save_path = f"{save_dir}/{filename}"
            cv2.imwrite(save_path, frame)

            zoom_path = None
            if zoom_img is not None:
                zoom_path = f"{save_dir}/plate_{timestamp}.jpg"
                cv2.imwrite(zoom_path, zoom_resized)

            cur.execute("""INSERT INTO images (name, path, zoom_path, timestamp)
                           VALUES (?, ?, ?, ?)""",
                        (filename, save_path, zoom_path, timestamp))
            conn.commit()

            load_images()
            messagebox.showinfo("OK", "Đã lưu ảnh!")

        elif key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


# ==============================
#  NÚT
# ==============================
btn_add = tk.Button(left_frame, text="Thêm ảnh", command=add_image)
btn_add.pack(pady=5)

btn_cam = tk.Button(left_frame, text="Camera YOLO", command=lambda: open_camera_yolo(False))
btn_cam.pack(pady=5)

btn_vid = tk.Button(left_frame, text="Video YOLO", command=lambda: open_camera_yolo(True))
btn_vid.pack(pady=5)

btn_face = tk.Button(left_frame, text="Chụp khuôn mặt", command=capture_face_window)
btn_face.pack(pady=5)


# ==============================
root.mainloop()
conn.close()
