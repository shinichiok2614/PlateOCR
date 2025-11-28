import os
import shutil
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

# ==============================
#  Khởi tạo database
# ==============================
conn = sqlite3.connect("images.db")
cur = conn.cursor()
cur.execute("""
            CREATE TABLE IF NOT EXISTS images
            (
                id
                INTEGER
                PRIMARY
                KEY
                AUTOINCREMENT,
                name
                TEXT,
                path
                TEXT
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

        # === Resize thumbnail giữ tỉ lệ ===
        max_w, max_h = 350, 350
        w, h = img.size
        scale = min(max_w / w, max_h / h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        img_tk = ImageTk.PhotoImage(img)

        image_label.img = img_tk
        image_label.config(image=img_tk)

        # === Khi click vào ảnh → mở cửa sổ xem ảnh lớn ===
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
#  Hàm chọn ảnh và lưu vào thư mục + DB
# ==============================
def add_image():
    filepath = filedialog.askopenfilename(
        filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif")]
    )
    if not filepath:
        return

    # Tạo thư mục images nếu chưa có
    os.makedirs("images", exist_ok=True)

    # Tên file gốc
    filename = os.path.basename(filepath)

    # Đường dẫn ảnh trong thư mục dự án
    new_path = os.path.join("images", filename)

    # Nếu file trùng tên → đổi tên
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(new_path):
        new_path = os.path.join("images", f"{base}_{counter}{ext}")
        counter += 1

    # Copy ảnh vào thư mục dự án
    shutil.copy(filepath, new_path)

    # Lưu vào DB
    cur.execute("INSERT INTO images (name, path) VALUES (?, ?)", (os.path.basename(new_path), new_path))
    conn.commit()

    # Cập nhật listbox
    load_images()
    messagebox.showinfo("Thành công", "Đã thêm ảnh!")

def open_viewer(img_path):
    viewer = tk.Toplevel()
    viewer.title("Xem ảnh lớn")

    # Cho phép phóng to cửa sổ
    viewer.geometry("800x600")

    # Khung hiển thị ảnh
    lbl = tk.Label(viewer, bg="black")
    lbl.pack(fill="both", expand=True)

    # Load ảnh gốc
    original_img = Image.open(img_path)

    def resize_image(event=None):
        # Lấy kích thước cửa sổ
        fw = viewer.winfo_width()
        fh = viewer.winfo_height()

        # Chặn trường hợp kích thước quá nhỏ (Tkinter khởi tạo)
        if fw < 50 or fh < 50:
            return

        # Lấy kích thước ảnh gốc
        w, h = original_img.size

        # Giữ nguyên tỉ lệ
        scale = min(fw / w, fh / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))

        resized = original_img.resize((new_w, new_h), Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(resized)

        lbl.img = tk_img
        lbl.config(image=tk_img)

    viewer.bind("<Configure>", resize_image)
    resize_image()

# Nút chọn ảnh
btn_add = tk.Button(left_frame, text="Chọn ảnh để thêm", command=add_image)
btn_add.pack(pady=10)

root.mainloop()
conn.close()
