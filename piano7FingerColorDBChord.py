import tkinter as tk
from tkinter import messagebox, ttk, simpledialog
import sqlite3

# Mapping ngón tay sang màu
FINGER_COLORS = {
    1: "red",    # ngón cái
    2: "orange",
    3: "yellow",
    4: "green",
    5: "blue"
}

# =====================
# Khởi tạo cơ sở dữ liệu hoàn chỉnh
# =====================
conn = sqlite3.connect("piano_keys.db")
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS key_presses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id TEXT,
    hand TEXT,
    finger INTEGER,
    chord_id INTEGER DEFAULT 0,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

class PianoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Piano Key Press Recorder")
        self.root.state('zoomed')  # full screen

        self.selected_keys = {}  # key_id: (hand, finger)
        self.chord_counter = 0

        self.main_frame = tk.Frame(root)
        self.main_frame.pack(fill="both", expand=True)

        self.btn = tk.Button(self.main_frame, text="Lưu hợp âm (Chord)", command=self.save_chord)
        self.btn.pack()

        # Lịch sử phím dạng bảng dữ liệu
        self.history_frame = tk.Frame(self.main_frame)
        self.history_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(self.history_frame, columns=("key","hand","finger","time","chord_id"), show="headings")
        for col in ("key","hand","finger","time","chord_id"):
            self.tree.heading(col, text=col.capitalize())
        self.tree.pack(fill="both", expand=True)

        # Lịch sử phím dạng piano với thanh trượt
        self.visual_frame = tk.Frame(self.main_frame)
        self.visual_frame.pack(fill="both", expand=True)

        self.history_canvas = tk.Canvas(self.visual_frame, bg="lightgray")
        self.v_scroll = tk.Scrollbar(self.visual_frame, orient="vertical", command=self.history_canvas.yview)
        self.history_canvas.configure(yscrollcommand=self.v_scroll.set)

        self.v_scroll.pack(side="right", fill="y")
        self.history_canvas.pack(side="left", fill="both", expand=True)

        self.canvas = None
        self.key_rects = {}

        self.create_piano_canvas()
        self.load_history()

    # =====================
    # Tạo piano
    # =====================
    def create_piano_canvas(self):
        screen_w = self.root.winfo_screenwidth()
        total_cycles = 7
        white_notes = 7
        white_width = screen_w // (total_cycles * white_notes)
        white_height = 150
        black_width = int(white_width * 0.6)
        black_height = 90

        self.canvas = tk.Canvas(self.main_frame, width=screen_w, height=white_height)
        self.canvas.pack(fill="x")

        for c in range(total_cycles):
            cycle_offset = c * white_notes * white_width
            for i in range(white_notes):
                x1 = cycle_offset + i * white_width
                x2 = x1 + white_width
                rect = self.canvas.create_rectangle(x1, 0, x2, white_height, fill="white", outline="black")
                key_id = f"W{c}-{i}"
                self.key_rects[key_id] = rect
                self.canvas.tag_bind(rect, "<Button-1>", lambda e, k=key_id: self.press_key(k))
            black_positions = [1, 2, 4, 5, 6]
            for bp in black_positions:
                x1 = cycle_offset + bp * white_width - black_width // 2
                x2 = x1 + black_width
                rect = self.canvas.create_rectangle(x1, 0, x2, black_height, fill="black", outline="black")
                key_id = f"B{c}-{bp}"
                self.key_rects[key_id] = rect
                self.canvas.tag_bind(rect, "<Button-1>", lambda e, k=key_id: self.press_key(k))

    # =====================
    # Nhấn phím
    # =====================
    def press_key(self, key_id):
        hand = simpledialog.askstring("Hand", "Nhập tay (A = trái, B = phải):", parent=self.root)
        if not hand or hand.upper() not in ('A', 'B'):
            return
        hand = hand.upper()

        finger = simpledialog.askinteger("Finger", "Nhập ngón tay (1-5):", minvalue=1, maxvalue=5, parent=self.root)
        if not finger or finger not in range(1,6):
            return

        self.selected_keys[key_id] = (hand, finger)
        color = FINGER_COLORS.get(finger, "gray")
        self.canvas.itemconfig(self.key_rects[key_id], fill=color)

    def reset_key_color(self, key_id):
        if key_id.startswith("W"):
            self.canvas.itemconfig(self.key_rects[key_id], fill="white")
        else:
            self.canvas.itemconfig(self.key_rects[key_id], fill="black")

    # =====================
    # Lưu chord
    # =====================
    def save_chord(self):
        if not self.selected_keys:
            messagebox.showwarning("Không có phím", "Bạn chưa chọn phím nào")
            return

        self.chord_counter += 1
        chord_id = self.chord_counter

        cur.execute("BEGIN")
        for k, (hand, finger) in self.selected_keys.items():
            cur.execute("INSERT INTO key_presses (key_id, hand, finger, chord_id) VALUES (?,?,?,?)", (k, hand, finger, chord_id))
        conn.commit()

        ts = cur.execute("SELECT timestamp FROM key_presses WHERE chord_id=? ORDER BY timestamp DESC LIMIT 1", (chord_id,)).fetchone()[0]

        for k, (hand, finger) in self.selected_keys.items():
            self.tree.insert("", 0, values=(k, hand, finger, ts, chord_id))

        self.draw_chord_on_history(self.selected_keys)

        for k, (hand, finger) in self.selected_keys.items():
            color = FINGER_COLORS.get(finger, "gray")
            self.canvas.itemconfig(self.key_rects[k], fill=color)
        self.root.after(500, lambda keys=list(self.selected_keys.keys()): [self.reset_key_color(k) for k in keys])

        self.selected_keys.clear()

    # =====================
    # Load lịch sử
    # =====================
    def load_history(self):
        self.tree.delete(*self.tree.get_children())
        self.history_canvas.delete("all")
        self.history_y = 0

        keys_by_chord = {}

        for row in cur.execute("SELECT key_id, hand, finger, timestamp, chord_id FROM key_presses ORDER BY chord_id, timestamp"):
            key_id, hand, finger, ts, chord_id = row

            if chord_id not in keys_by_chord:
                keys_by_chord[chord_id] = {}
            keys_by_chord[chord_id][key_id] = (hand, finger)

            self.tree.insert("", "end", values=(key_id, hand, finger, ts, chord_id))

        for keys in keys_by_chord.values():
            self.draw_chord_on_history(keys)

    # =====================
    # Vẽ chord trên canvas lịch sử
    # =====================
    def draw_chord_on_history(self, keys_dict):
        screen_w = self.root.winfo_screenwidth()
        total_cycles = 7
        white_notes = 7
        white_width = screen_w // (total_cycles * white_notes)
        white_height = 30
        black_width = int(white_width * 0.6)
        black_height = 20

        y_offset = getattr(self, 'history_y', 0)

        for c in range(total_cycles):
            cycle_offset = c * white_notes * white_width
            for i in range(white_notes):
                key_id = f"W{c}-{i}"
                finger = keys_dict.get(key_id, (None, 0))[1]
                color = FINGER_COLORS.get(finger, "white") if finger else "white"
                self.history_canvas.create_rectangle(cycle_offset + i*white_width, y_offset,
                                                     cycle_offset + (i+1)*white_width, y_offset + white_height,
                                                     fill=color, outline="black")
            black_positions = [1, 2, 4, 5, 6]
            for bp in black_positions:
                key_id = f"B{c}-{bp}"
                finger = keys_dict.get(key_id, (None, 0))[1]
                color = FINGER_COLORS.get(finger, "black") if finger else "black"
                x1 = cycle_offset + bp*white_width - black_width//2
                x2 = x1 + black_width
                self.history_canvas.create_rectangle(x1, y_offset, x2, y_offset + black_height, fill=color, outline="black")

        self.history_y = y_offset + white_height + 5
        self.history_canvas.config(scrollregion=self.history_canvas.bbox("all"))


# =====================
# Khởi chạy ứng dụng
# =====================
root = tk.Tk()
app = PianoApp(root)
root.mainloop()