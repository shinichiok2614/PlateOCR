import tkinter as tk
import sqlite3
from tkinter import messagebox

# -------------------------
# Kết nối SQLite
# -------------------------
conn = sqlite3.connect("data.db")
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL
    )
""")
conn.commit()

# -------------------------
# Hàm xử lý
# -------------------------
def add_user():
    name = entry.get()
    if not name.strip():
        messagebox.showwarning("Lỗi", "Chưa nhập tên!")
        return
    cur.execute("INSERT INTO users (name) VALUES (?)", (name,))
    conn.commit()
    messagebox.showinfo("Thành công", "Đã thêm người dùng!")
    entry.delete(0, tk.END)

def show_users():
    cur.execute("SELECT * FROM users")
    rows = cur.fetchall()

    text.delete("1.0", tk.END)
    for r in rows:
        text.insert(tk.END, f"{r[0]} - {r[1]}\n")

# -------------------------
# Giao diện
# -------------------------
root = tk.Tk()
root.title("Tkinter + SQLite")
root.geometry("350x300")

label = tk.Label(root, text="Nhập tên:")
label.pack(pady=5)

entry = tk.Entry(root, width=30)
entry.pack()

btn_add = tk.Button(root, text="Thêm", command=add_user)
btn_add.pack(pady=5)

btn_show = tk.Button(root, text="Xem danh sách", command=show_users)
btn_show.pack(pady=5)

text = tk.Text(root, width=40, height=10)
text.pack(pady=10)

root.mainloop()

# Đóng kết nối Django
conn.close()
