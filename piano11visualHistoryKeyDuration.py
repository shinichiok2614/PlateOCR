import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime

# =====================
# Màu các ngón tay
# =====================
FINGER_COLORS = {1:"red", 2:"orange", 3:"yellow", 4:"green", 5:"blue"}

# =====================
# Database
# =====================
conn = sqlite3.connect("piano_keys.db")
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS key_presses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id TEXT,
    hand TEXT,
    finger INTEGER,
    chord_id REAL DEFAULT 0,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    start_time REAL DEFAULT 0,
    duration REAL DEFAULT 0.5,
    note_text TEXT
)
""")
conn.commit()

# =====================
# Custom dialog
# =====================
class KeyPressDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Nhập tay, ngón, thời gian")
        self.resizable(False, False)
        self.result = None

        tk.Label(self, text="Tay (A/B):").pack(padx=10, pady=2)
        self.entry_hand = tk.Entry(self)
        self.entry_hand.pack(padx=10, pady=2)
        self.entry_hand.focus_set()

        tk.Label(self, text="Ngón tay (1-5):").pack(padx=10, pady=2)
        self.entry_finger = tk.Entry(self)
        self.entry_finger.pack(padx=10, pady=2)

        tk.Label(self, text="Thời điểm bắt đầu (s):").pack(padx=10, pady=2)
        self.entry_start = tk.Entry(self)
        self.entry_start.pack(padx=10, pady=2)
        self.entry_start.insert(0,"0")

        tk.Label(self, text="Thời gian giữ (s):").pack(padx=10, pady=2)
        self.entry_duration = tk.Entry(self)
        self.entry_duration.pack(padx=10, pady=2)
        self.entry_duration.insert(0,"0.5")

        tk.Button(self, text="OK", command=self.on_ok).pack(pady=5)

        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def on_ok(self):
        try:
            hand = self.entry_hand.get().upper()
            finger = int(self.entry_finger.get())
            start_time = float(self.entry_start.get())
            duration = float(self.entry_duration.get())
            if hand not in ('A','B') or not (1 <= finger <=5):
                raise ValueError
            self.result = (hand, finger, start_time, duration)
        except:
            self.result = None
        self.destroy()

# =====================
# PianoApp
# =====================
class PianoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Piano Key Press Recorder")
        self.root.state('zoomed')

        self.selected_keys = {}
        cur.execute("SELECT MAX(chord_id) FROM key_presses")
        row = cur.fetchone()
        self.chord_counter = row[0] if row and row[0] is not None else 0
        self.current_chord_id = self.chord_counter

        self.main_frame = tk.Frame(root)
        self.main_frame.pack(fill="both", expand=True)

        # Buttons
        self.btn_save_chord = tk.Button(self.main_frame, text="Lưu hợp âm (Chord)", command=self.save_chord)
        self.btn_save_chord.pack()
        self.btn_add_note = tk.Button(self.main_frame, text="Thêm ghi chú", command=self.add_note_for_selected_chord)
        self.btn_add_note.pack()

        # History Canvas
        self.visual_frame = tk.Frame(self.main_frame)
        self.visual_frame.pack(fill="both", expand=True)
        self.history_canvas = tk.Canvas(self.visual_frame, bg="lightgray", height=300)
        self.v_scroll = tk.Scrollbar(self.visual_frame, orient="vertical", command=self.history_canvas.yview)
        self.history_canvas.configure(yscrollcommand=self.v_scroll.set)
        self.v_scroll.pack(side="right", fill="y")
        self.history_canvas.pack(side="left", fill="both", expand=True)

        # Piano canvas
        self.canvas = None
        self.key_rects = {}
        self.history_y = 0

        self.create_piano_canvas()
        self.load_history()

    # =====================
    # Piano Canvas
    # =====================
    def create_piano_canvas(self):
        screen_w = self.root.winfo_screenwidth()
        total_cycles = 7
        white_notes = 7
        white_width = screen_w // (total_cycles*white_notes)
        white_height = 150
        black_width = int(white_width*0.6)
        black_height = 90

        self.canvas = tk.Canvas(self.main_frame, width=screen_w, height=white_height)
        self.canvas.pack(fill="x")

        for c in range(total_cycles):
            cycle_offset = c*white_notes*white_width
            for i in range(white_notes):
                x1 = cycle_offset + i*white_width
                x2 = x1 + white_width
                rect = self.canvas.create_rectangle(x1, 0, x2, white_height, fill="white", outline="black")
                key_id = f"W{c}-{i}"
                self.key_rects[key_id] = rect
                self.canvas.tag_bind(rect, "<Button-1>", lambda e, k=key_id: self.press_key(k))
            black_positions=[1,2,4,5,6]
            for bp in black_positions:
                x1 = cycle_offset+bp*white_width-black_width//2
                x2 = x1+black_width
                rect = self.canvas.create_rectangle(x1,0,x2,black_height,fill="black", outline="black")
                key_id = f"B{c}-{bp}"
                self.key_rects[key_id]=rect
                self.canvas.tag_bind(rect, "<Button-1>", lambda e, k=key_id: self.press_key(k))

    def press_key(self, key_id):
        dialog = KeyPressDialog(self.root)
        if dialog.result:
            hand, finger, start_time, duration = dialog.result
            self.selected_keys[key_id] = (hand, finger, start_time, duration)
            color = FINGER_COLORS.get(finger,"gray")
            self.canvas.itemconfig(self.key_rects[key_id], fill=color)

    def reset_key_color(self,key_id):
        if key_id.startswith("W"):
            self.canvas.itemconfig(self.key_rects[key_id], fill="white")
        else:
            self.canvas.itemconfig(self.key_rects[key_id], fill="black")

    # =====================
    # Save chord
    # =====================
    def save_chord(self):
        if not self.selected_keys:
            messagebox.showwarning("Không có phím","Bạn chưa chọn phím nào")
            return

        self.chord_counter += 1
        chord_id = self.chord_counter
        self.current_chord_id = chord_id

        cur.execute("BEGIN")
        for k,(hand,finger,start_time,duration) in self.selected_keys.items():
            cur.execute("INSERT INTO key_presses (key_id, hand, finger, chord_id, start_time, duration) VALUES (?,?,?,?,?,?)",
                        (k, hand, finger, chord_id, start_time, duration))
        conn.commit()

        self.draw_chord_on_history(self.selected_keys)

        for k,(hand,finger,start_time,duration) in self.selected_keys.items():
            color = FINGER_COLORS.get(finger,"gray")
            self.canvas.itemconfig(self.key_rects[k], fill=color)
        self.root.after(500, lambda keys=list(self.selected_keys.keys()): [self.reset_key_color(k) for k in keys])

        self.selected_keys.clear()
        self.load_history()

    # =====================
    # Add note for chord
    # =====================
    def add_note_for_selected_chord(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Ghi chú")
        dialog.geometry("300x100")
        tk.Label(dialog, text="Nhập lời bài hát:").pack()
        entry = tk.Entry(dialog)
        entry.pack()
        entry.focus_set()

        def on_ok():
            text = entry.get()
            if text:
                chord_id = self.current_chord_id
                cur.execute("INSERT INTO key_presses (note_text, chord_id) VALUES (?,?)", (text,chord_id))
                conn.commit()
                self.load_history()
            dialog.destroy()

        tk.Button(dialog,text="OK",command=on_ok).pack(pady=5)
        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)

    # =====================
    # Load history
    # =====================
    def load_history(self):
        self.history_canvas.delete("all")
        self.history_y = 0

        rows = list(cur.execute("SELECT key_id, hand, finger, start_time, duration, chord_id, note_text FROM key_presses ORDER BY chord_id"))
        chord_dict = {}
        note_dict = {}
        for row in rows:
            key_id, hand, finger, start_time, duration, chord_id, note_text = row
            if note_text:
                note_dict.setdefault(chord_id, []).append(note_text)
            else:
                chord_dict.setdefault(chord_id,{})[key_id]=(hand,finger,start_time,duration)

        for chord_id in sorted(set(list(chord_dict.keys())+list(note_dict.keys()))):
            keys = chord_dict.get(chord_id,{})
            notes = note_dict.get(chord_id,[])
            self.draw_chord_on_history(keys)
            for note_text in notes:
                y = self.history_y
                self.history_canvas.create_text(10, y+15, anchor="w", text=note_text, fill="purple", font=("Arial",12,"italic"))
                self.history_y += 25

        self.history_canvas.config(scrollregion=self.history_canvas.bbox("all"))

    # =====================
    # Draw chord on history piano canvas
    # =====================
    def draw_chord_on_history(self, keys_dict):
        screen_w = self.root.winfo_screenwidth()
        total_cycles = 7
        white_notes = 7
        white_width = screen_w // (total_cycles*white_notes)
        white_height = 20
        black_width = int(white_width*0.6)
        black_height = 15

        scale_start = 50   # pixels / giây cho start_time
        scale_duration = 50 # pixels / giây cho duration

        base_key_height = white_height

        # tính chord_height = base + max (start_time + duration)
        max_time = max((start_time + duration for hand, finger, start_time, duration in keys_dict.values()), default=0)
        chord_height = base_key_height + max_time * scale_duration + 5

        y_offset = self.history_y

        for c in range(total_cycles):
            cycle_offset = c*white_notes*white_width
            # phím trắng
            for i in range(white_notes):
                key_id = f"W{c}-{i}"
                x1 = cycle_offset + i*white_width
                x2 = x1 + white_width
                if key_id in keys_dict:
                    hand, finger, start_time, duration = keys_dict[key_id]
                    color = FINGER_COLORS.get(finger,"gray")
                    # phím chính
                    self.history_canvas.create_rectangle(x1,y_offset,x2,y_offset+white_height,fill=color,outline="black")
                    # thanh start_time + duration
                    y_start = y_offset - start_time*scale_start - duration*scale_duration
                    y_end = y_offset - start_time*scale_start
                    self.history_canvas.create_rectangle(x1,y_start,x2,y_end,fill=color,outline="black")
                else:
                    self.history_canvas.create_rectangle(x1,y_offset,x2,y_offset+white_height,fill="white",outline="black")
            # phím đen
            black_positions=[1,2,4,5,6]
            for bp in black_positions:
                key_id = f"B{c}-{bp}"
                x1=cycle_offset+bp*white_width-black_width//2
                x2=x1+black_width
                if key_id in keys_dict:
                    hand, finger, start_time, duration = keys_dict[key_id]
                    color = FINGER_COLORS.get(finger,"gray")
                    self.history_canvas.create_rectangle(x1,y_offset,x2,y_offset+black_height,fill=color,outline="black")
                    y_start = y_offset - start_time*scale_start - duration*scale_duration
                    y_end = y_offset - start_time*scale_start
                    self.history_canvas.create_rectangle(x1,y_start,x2,y_end,fill=color,outline="black")
                else:
                    self.history_canvas.create_rectangle(x1,y_offset,x2,y_offset+black_height,fill="black",outline="black")
        # self.history_y += white_height + black_height + 5
        self.history_y += chord_height

# =====================
# Run app
# =====================
root = tk.Tk()
app = PianoApp(root)
root.mainloop()
