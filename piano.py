import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import sqlite3

# -----------------------------
# Database setup
# -----------------------------
conn = sqlite3.connect("piano_keys.db")
cur = conn.cursor()
cur.execute("""
            CREATE TABLE IF NOT EXISTS key_presses
            (
                timestamp
                DATETIME
                DEFAULT
                CURRENT_TIMESTAMP,
                key_id
                TEXT,
                hand
                TEXT,
                finger
                INTEGER
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

        self.active_fingers = {}  # (hand, finger) -> key_id

        self.frame = tk.Frame(root)
        self.frame.pack()

        self.keys = []
        self.create_piano()

    def create_piano(self):
        # 7 cycles * 12 notes = 84 keys
        total_cycles = 7
        white_notes = 7
        black_notes = 5

        screen_w = self.root.winfo_screenwidth()
        # Fit piano into screen width
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

        canvas = tk.Canvas(self.frame, width=screen_w, height=white_height)
        canvas.pack()

        key_index = 0
        for c in range(total_cycles):
            cycle_offset = c * white_notes * white_width

            # White keys
            for i in range(white_notes):
                x1 = cycle_offset + i * white_width
                x2 = x1 + white_width
                rect = canvas.create_rectangle(x1, 0, x2, white_height, fill="white", outline="black")
                key_id = f"W{c}-{i}"
                self.keys.append((rect, key_id))
                canvas.tag_bind(rect, "<Button-1>", lambda e, k=key_id: self.press_key(k))

            # Black keys pattern per octave: positions (1,2,4,5,6)
            black_positions = [1, 2, 4, 5, 6]
            for bp in black_positions:
                x1 = cycle_offset + bp * white_width - black_width // 2
                x2 = x1 + black_width
                rect = canvas.create_rectangle(x1, 0, x2, black_height, fill="black", outline="black")
                key_id = f"B{c}-{bp}"
                self.keys.append((rect, key_id))
                canvas.tag_bind(rect, "<Button-1>", lambda e, k=key_id: self.press_key(k))

    def press_key(self, key_id):
        # Ask hand
        hand = tk.simpledialog.askstring("Hand", "Nhập tay (A = trái, B = phải):")
        if hand not in ("A", "B"):
            messagebox.showerror("Lỗi", "Tay phải là A hoặc B")
            return

        # Ask finger
        finger = tk.simpledialog.askinteger("Finger", "Nhập ngón (1-5):")
        if finger not in (1, 2, 3, 4, 5):
            messagebox.showerror("Lỗi", "Ngón phải từ 1 đến 5")
            return

        # Check constraint: each finger presses only 1 key at a time
        if (hand, finger) in self.active_fingers:
            messagebox.showerror("Lỗi", f"Ngón {finger} tay {hand} đang bấm phím khác!")
            return

        self.active_fingers[(hand, finger)] = key_id
        self.save_to_db(key_id, hand, finger)
        messagebox.showinfo("OK", f"Đã ghi: {key_id} - Tay {hand} - Ngón {finger}")

    def save_to_db(self, key_id, hand, finger):
        cur.execute("INSERT INTO key_presses (key_id, hand, finger) VALUES (?,?,?)", (key_id, hand, finger))
        conn.commit()


root = tk.Tk()
app = PianoApp(root)
root.mainloop()
