import tkinter as tk
from tkinter import messagebox

# Hàm xử lý khi nhấn nút
def say_hello():
    name = entry.get()
    if name.strip() == "":
        messagebox.showwarning("Lỗi", "Bạn chưa nhập tên!")
    else:
        messagebox.showinfo("Xin chào", f"Chào {name}!")

# Tạo cửa sổ chính
root = tk.Tk()
root.title("Demo Tkinter")
root.geometry("300x180")

# Nhãn
label = tk.Label(root, text="Nhập tên của bạn:")
label.pack(pady=5)

# Ô nhập
entry = tk.Entry(root, width=25)
entry.pack(pady=5)

# Nút
button = tk.Button(root, text="Chào", command=say_hello)
button.pack(pady=10)

# Chạy giao diện
root.mainloop()
