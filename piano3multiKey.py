import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import sqlite3

# -----------------------------
# Database setup
# -----------------------------
conn = sqlite3.connect("piano_keys.db")
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS key_presses (
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    key_id TEXT,
    hand TEXT,
    finger INTEGER
)
""")
conn.commit()

# -----------------------------
# App
# -----------------------------
class PianoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Piano Key Press Recorder")
        self.selected_keys = set()

        self.main_frame = tk.Frame(root)
        self.main_frame.pack()

        self.btn = tk.Button(self.main_frame, text="Lưu hợp âm (Chord)", command=self.save_chord)
        self.btn.pack()

        self.history_frame = tk.Frame(root)
        self.history_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(self.history_frame, columns=("key","hand","finger","time"), show="headings")
        for col in ("key","hand","finger","time"):
            self.tree.heading(col, text=col.capitalize())
        self.tree.pack(fill="both", expand=True)

        self.canvas = None
        self.key_rects = {}

        self.create_piano_canvas()
        self.load_history()

    # -----------------------------
    # Piano creation
    # -----------------------------
    def create_piano_canvas(self):
        screen_w = self.root.winfo_screenwidth()
        total_cycles = 7
        white_notes = 7

        white_width = screen_w // (total_cycles * white_notes)
        white_height = 150
        black_width = int(white_width * 0.6)
        black_height = 90

        self.white_width = white_width
        self.black_width = black_width
        self.white_height = white_height
        self.black_height = black_height

        self.canvas = tk.Canvas(self.main_frame, width=screen_w, height=white_height)
        self.canvas.pack()

        for c in range(total_cycles):
            cycle_offset = c * white_notes * white_width

            # White keys
            for i in range(white_notes):
                x1 = cycle_offset + i * white_width
                x2 = x1 + white_width
                rect = self.canvas.create_rectangle(x1, 0, x2, white_height, fill="white", outline="black")
                key_id = f"W{c}-{i}"
                self.key_rects[key_id] = rect
                self.canvas.tag_bind(rect, "<Button-1>", lambda e, k=key_id: self.press_key(k))

            # Black keys
            black_positions = [1, 2, 4, 5, 6]
            for bp in black_positions:
                x1 = cycle_offset + bp * white_width - black_width // 2
                x2 = x1 + black_width
                rect = self.canvas.create_rectangle(x1, 0, x2, black_height, fill="black", outline="black")
                key_id = f"B{c}-{bp}"
                self.key_rects[key_id] = rect
                self.canvas.tag_bind(rect, "<Button-1>", lambda e, k=key_id: self.press_key(k))

    # -----------------------------
    # Key press logic
    # -----------------------------
    def press_key(self, key_id):
        if key_id in self.selected_keys:
            self.selected_keys.remove(key_id)
            self.reset_key_color(key_id)
        else:
            self.selected_keys.add(key_id)
            self.canvas.itemconfig(self.key_rects[key_id], fill="orange")

    def reset_key_color(self, key_id):
        if key_id.startswith("W"):
            self.canvas.itemconfig(self.key_rects[key_id], fill="white")
        else:
            self.canvas.itemconfig(self.key_rects[key_id], fill="black")

    # -----------------------------
    # Save chord
    # -----------------------------
    def save_chord(self):
        if not self.selected_keys:
            messagebox.showwarning("Không có phím", "Bạn chưa chọn phím nào")
            return
        cur.execute("BEGIN")
        for k in self.selected_keys:
            cur.execute("INSERT INTO key_presses (key_id, hand, finger) VALUES (?,?,?)", (k, "Chord", 0))
        conn.commit()
        ts = cur.execute("SELECT timestamp FROM key_presses ORDER BY timestamp DESC LIMIT 1").fetchone()[0]
        for k in self.selected_keys:
            self.tree.insert("", 0, values=(k, "Chord", 0, ts))
            self.reset_key_color(k)
        self.selected_keys.clear()

    # -----------------------------
    # History
    # -----------------------------
    def load_history(self):
        self.tree.delete(*self.tree.get_children())
        for row in cur.execute("SELECT key_id, hand, finger, timestamp FROM key_presses ORDER BY timestamp DESC"):
            self.tree.insert("", "end", values=row)


root = tk.Tk()
app = PianoApp(root)
root.mainloop()