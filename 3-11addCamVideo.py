import os
import shutil
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import cv2
from datetime import datetime

plate_cascade = cv2.CascadeClassifier("haarcascade_russian_plate_number.xml")


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
                path TEXT
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
listbox = tk.Listbox(left_frame, width=30, height=20)
listbox.pack()

# Label hiển thị ảnh
image_label = tk.Label(right_frame)
image_label.pack()


# ==============================
#  Hàm hiển thị ảnh khi chọn
# ==============================
def show_selected(event=None):
    try:
        idx = listbox.curselection()
        if not idx:
            return
        item = listbox.get(idx)

        cur.execute("SELECT path FROM images WHERE name = ?", (item,))
        row = cur.fetchone()
        if not row:
            return

        img_path = row[0]
        img = Image.open(img_path)

        # Resize thumbnail giữ tỉ lệ
        max_w, max_h = 350, 350
        w, h = img.size
        scale = min(max_w / w, max_h / h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        img_tk = ImageTk.PhotoImage(img)

        image_label.img = img_tk
        image_label.config(image=img_tk)

        # Click ảnh → xem ảnh to
        image_label.bind("<Button-1>", lambda e, p=img_path: open_viewer(p))

    except Exception as e:
        messagebox.showerror("Lỗi", str(e))


listbox.bind("<<ListboxSelect>>", show_selected)


# ==============================
#  Hàm tải danh sách ảnh
# ==============================
def load_images():
    listbox.delete(0, tk.END)
    cur.execute("SELECT name FROM images ORDER BY id DESC")
    rows = cur.fetchall()

    for r in rows:
        listbox.insert(tk.END, r[0])


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


# ==============================
#  Chụp ảnh từ Camera
# ==============================
def open_camera(use_video=False):
    """
    use_video = False  -> dùng camera
    use_video = True   -> dùng video file
    """

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

    while True:
        ret, frame = cap.read()
        if not ret:
            break  # hết video hoặc camera lỗi

        # ==== Nhận dạng biển số ====
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        plates = plate_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(80, 25)
        )

        for (x, y, w, h) in plates:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(frame, "Plate", (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 255, 0), 2)

        cv2.imshow("Camera/Video", frame)
        key = cv2.waitKey(1) & 0xFF

        # Space để chụp từ video hoặc camera
        if key == ord(' '):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"frame_{timestamp}.jpg"

            os.makedirs("images", exist_ok=True)
            save_path = os.path.join("images", filename)

            cv2.imwrite(save_path, frame)

            # Lưu vào DB
            cur.execute(
                "INSERT INTO images (name, path) VALUES (?, ?)",
                (filename, save_path)
            )
            conn.commit()

            load_images()
            messagebox.showinfo("OK", f"Đã lưu ảnh: {filename}")

        # ESC thoát
        elif key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()




# ==============================
#  Nút bấm
# ==============================
btn_add = tk.Button(left_frame, text="Chọn ảnh để thêm", command=add_image)
btn_add.pack(pady=10)

btn_cam = tk.Button(left_frame, text="Chụp ảnh từ camera",
                    command=lambda: open_camera(use_video=False))

btn_cam.pack(pady=10)

btn_video = tk.Button(left_frame, text="Mở video thử nghiệm",
                      command=lambda: open_camera(use_video=True))
btn_video.pack(pady=10)

# ==============================
root.mainloop()
conn.close()
