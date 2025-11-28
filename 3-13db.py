import os
import shutil
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import cv2
from datetime import datetime
from ultralytics import YOLO


# Dùng model đã train sẵn cho license plate detection
model = YOLO("license_plate_detector.pt")  # tải model phù hợp
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
root.geometry("600x420")

# Frame trái (danh sách)
left_frame = tk.Frame(root)
left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

# Frame phải (hiển thị ảnh)
right_frame = tk.Frame(root)
right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

# Listbox hiển thị ảnh
# listbox = tk.Listbox(left_frame, width=30, height=20)
# listbox.pack()

# Treeview hiển thị ảnh
columns = ("name", "timestamp", "zoom")
tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=20)
tree.heading("name", text="Tên ảnh")
tree.heading("timestamp", text="Ngày giờ")
tree.heading("zoom", text="Xem Plate Zoom")
tree.column("name", width=120)
tree.column("timestamp", width=120)
tree.column("zoom", width=100)
tree.pack()


# Label hiển thị ảnh
# Label hiển thị ảnh (giống code 2)
image_label = tk.Label(right_frame)
image_label.pack()


# ==============================
#  Hàm hiển thị ảnh khi chọn
# ==============================
def view_selected(event=None):
    selected = tree.selection()
    if not selected:
        return

    item = tree.item(selected[0])
    name, timestamp, zoom_text = item["values"]

    # Lấy path + zoom_path từ DB
    cur.execute("SELECT path, zoom_path FROM images WHERE name = ?", (name,))
    row = cur.fetchone()
    if not row:
        return

    img_path, zoom_path = row

    # Nếu không có zoom_path → dùng ảnh gốc
    display_path = zoom_path if zoom_path else img_path

    # ---- HIỂN THỊ ẢNH ZOOM TRONG GIAO DIỆN ----
    try:
        img = Image.open(display_path)

        max_w, max_h = 350, 350
        w, h = img.size
        scale = min(max_w / w, max_h / h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        img_tk = ImageTk.PhotoImage(img)

        image_label.img = img_tk
        image_label.config(image=img_tk)

        # Click để xem phóng to ảnh zoom
        image_label.bind("<Button-1>", lambda e, p=display_path: open_viewer(p))

    except Exception as e:
        messagebox.showerror("Lỗi", str(e))

    # ---- NÚT XEM ẢNH GỐC ----
    def view_original():
        open_viewer(img_path)

    # Xoá nút cũ trong right_frame
    for w in right_frame.pack_slaves():
        if isinstance(w, tk.Button):
            w.destroy()

    btn_view_original = tk.Button(right_frame, text="Xem ảnh gốc", command=view_original)
    btn_view_original.pack(pady=5)



# Bind double-click để xem (giống code cũ)
tree.bind("<Double-1>", view_selected)

# Bind chọn hàng để hiển thị ảnh ngay
tree.bind("<<TreeviewSelect>>", view_selected)



# ==============================
#  Hàm tải danh sách ảnh
# ==============================
def load_images():
    for row in tree.get_children():
        tree.delete(row)

    cur.execute("SELECT id, name, zoom_path, timestamp FROM images ORDER BY id DESC")
    rows = cur.fetchall()

    for r in rows:
        id_, name, zoom_path, timestamp = r
        tree.insert("", tk.END, values=(name, timestamp, "Xem" if zoom_path else "Không"))



load_images()


# ==============================
#  Chọn ảnh từ máy và lưu DB
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
    messagebox.showinfo("Thành công", "Đã thêm ảnh!")


# ==============================
#  Xem ảnh lớn (giữ tỉ lệ)
# ==============================
def open_viewer(img_path):
    viewer = tk.Toplevel()
    viewer.title("Xem ảnh lớn")
    viewer.geometry("800x600")

    lbl = tk.Label(viewer, bg="black")
    lbl.pack(fill="both", expand=True)

    original_img = Image.open(img_path)

    def resize_image(event=None):
        fw = viewer.winfo_width()
        fh = viewer.winfo_height()

        if fw < 50 or fh < 50:
            return

        w, h = original_img.size
        scale = min(fw / w, fh / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))

        resized = original_img.resize((new_w, new_h), Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(resized)

        lbl.img = tk_img
        lbl.config(image=tk_img)

    viewer.bind("<Configure>", resize_image)
    resize_image()

def save_face(face_img):
    folder = "data_faces"
    os.makedirs(folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{folder}/face_{timestamp}.jpg"

    cv2.imwrite(path, face_img)

    # cập nhật hàng dữ liệu cuối (biển số vừa lưu trước đó)
    cur.execute("UPDATE images SET face_path=? WHERE id=(SELECT MAX(id) FROM images)", (path,))
    conn.commit()

# ==============================
#  Chụp ảnh từ Camera
# ==============================


def open_camera_yolo(use_video=False):

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    max_w = int(screen_w * 0.8)  # tối đa 80% màn hình
    max_h = int(screen_h * 0.8)

    if use_video:
        video_path = filedialog.askopenfilename(
            title="Chọn file video",
            filetypes=[("Video files", "*.mp4 *.avi *.mkv *.mov")]
        )
        if not video_path:
            return
        cap = cv2.VideoCapture(video_path)
    else:
        cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        messagebox.showerror("Lỗi", "Không mở được camera hoặc video!")
        return

    cv2.namedWindow("Camera/Video", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Plate Zoom", cv2.WINDOW_AUTOSIZE)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # ===== YOLO Realtime Detection =====
        results = model(frame)[0]  # detect frame

        zoom_img = None
        for r in results.boxes:  # list các box
            x1, y1, x2, y2 = map(int, r.xyxy[0])
            conf = float(r.conf[0])

            if conf < 0.5:
                continue

            # Vẽ khung
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, "Plate", (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # Crop + zoom vùng biển số
            crop = frame[y1:y2, x1:x2]
            if crop.size > 0:
                zoom_img = cv2.resize(crop, None, fx=3.5, fy=3.5,
                                      interpolation=cv2.INTER_LINEAR)

            break  # chỉ zoom biển số đầu tiên

        # Hiển thị
        if zoom_img is not None:
            h, w = zoom_img.shape[:2]
            scale = min(max_w / w, max_h / h, 1.0)  # không vượt quá màn hình
            new_w = int(w * scale)
            new_h = int(h * scale)
            zoom_resized = cv2.resize(zoom_img, (new_w, new_h),
                                      interpolation=cv2.INTER_LINEAR)
            cv2.imshow("Plate Zoom", zoom_resized)

        cv2.imshow("Camera/Video", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord(' '):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_dir = os.path.join("images", "captured")
            os.makedirs(save_dir, exist_ok=True)

            # Lưu ảnh gốc
            filename = f"frame_{timestamp}.jpg"
            save_path = os.path.join(save_dir, filename)
            cv2.imwrite(save_path, frame)

            # Lưu ảnh Plate Zoom
            zoom_filename = f"plate_{timestamp}.jpg"
            zoom_path = os.path.join(save_dir, zoom_filename)
            if zoom_img is not None:
                h, w = zoom_img.shape[:2]
                scale = min(max_w / w, max_h / h, 1.0)
                new_w = int(w * scale)
                new_h = int(h * scale)
                zoom_resized = cv2.resize(zoom_img, (new_w, new_h),
                                          interpolation=cv2.INTER_LINEAR)
                cv2.imwrite(zoom_path, zoom_resized)
            else:
                zoom_path = None

            # Lưu vào DB
            cur.execute("""
                        INSERT INTO images (name, path, zoom_path, timestamp)
                        VALUES (?, ?, ?, ?)
                        """, (filename, save_path, zoom_path, timestamp))
            conn.commit()
            load_images()
            messagebox.showinfo("OK", f"Đã lưu ảnh gốc và Plate Zoom: {filename}")


        elif key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()

def capture_face_window():
    cap = cv2.VideoCapture(0)
    cv2.namedWindow("Face Capture", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Face Capture", 800, 600)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = face_model(frame, conf=0.5)

        face_crop = None

        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0,255,0), 2)

                # Lấy khuôn mặt crop
                face_crop = frame[y1:y2, x1:x2]

        cv2.imshow("Face Capture", frame)

        # Nhấn SPACE để lưu
        key = cv2.waitKey(1)
        if key == 32:  # SPACE
            if face_crop is not None:
                save_face(face_crop)
                messagebox.showinfo("Thành công", "Đã lưu khuôn mặt chủ xe!")
            break

        elif key == 27:  # ESC
            break

    cap.release()
    cv2.destroyWindow("Face Capture")



# ==============================
#  Nút bấm
# ==============================
btn_add = tk.Button(left_frame, text="Chọn ảnh để thêm", command=add_image)
btn_add.pack(pady=10)

btn_cam_yolo = tk.Button(left_frame, text="Camera YOLO",
                         command=lambda: open_camera_yolo(False))
btn_cam_yolo.pack(pady=10)

btn_video_yolo = tk.Button(left_frame, text="Video YOLO",
                           command=lambda: open_camera_yolo(True))
btn_video_yolo.pack(pady=10)

btn_face = tk.Button(root, text="Chụp khuôn mặt", command=capture_face_window)
btn_face.pack(pady=5)

# ==============================
root.mainloop()
conn.close()
