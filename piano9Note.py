import tkinter as tk
from tkinter import ttk
import sqlite3
from datetime import datetime

# Màu các ngón tay
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
    note_text TEXT
)
""")
conn.commit()

# =====================
# Custom dialog
# =====================
class HandFingerDialog(tk.Toplevel):
    def __init__(self, parent, title, label_text):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result = None

        tk.Label(self, text=label_text).pack(padx=10, pady=5)
        self.entry = tk.Entry(self)
        self.entry.pack(padx=10, pady=5)
        self.entry.focus_set()
        self.entry.bind("<Return>", self.on_ok)

        tk.Button(self, text="OK", command=self.on_ok).pack(pady=5)

        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def on_ok(self, event=None):
        self.result = self.entry.get()
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

        self.btn_save_chord = tk.Button(self.main_frame, text="Lưu hợp âm (Chord)", command=self.save_chord)
        self.btn_save_chord.pack()
        self.btn_add_note = tk.Button(self.main_frame, text="Thêm ghi chú", command=self.add_note_for_selected_chord)
        self.btn_add_note.pack()

        self.history_frame = tk.Frame(self.main_frame)
        self.history_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(self.history_frame, columns=("key","hand","finger","time","chord_id"), show="headings")
        for col in ("key","hand","finger","time","chord_id"):
            self.tree.heading(col, text=col.capitalize())
        self.tree.pack(fill="both", expand=True)

        self.visual_frame = tk.Frame(self.main_frame)
        self.visual_frame.pack(fill="both", expand=True)

        self.history_canvas = tk.Canvas(self.visual_frame, bg="lightgray")
        self.v_scroll = tk.Scrollbar(self.visual_frame, orient="vertical", command=self.history_canvas.yview)
        self.history_canvas.configure(yscrollcommand=self.v_scroll.set)

        self.v_scroll.pack(side="right", fill="y")
        self.history_canvas.pack(side="left", fill="both", expand=True)

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
        hand_dialog = HandFingerDialog(self.root, "Hand", "Nhập tay (A = trái, B = phải):")
        hand = hand_dialog.result
        if not hand or hand.upper() not in ('A','B'):
            return
        hand = hand.upper()

        finger_dialog = HandFingerDialog(self.root, "Finger", "Nhập ngón tay (1-5):")
        try:
            finger = int(finger_dialog.result)
        except:
            return
        if finger not in range(1,6):
            return

        self.selected_keys[key_id]=(hand,finger)
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
            tk.messagebox.showwarning("Không có phím","Bạn chưa chọn phím nào")
            return

        self.chord_counter += 1
        chord_id = self.chord_counter
        self.current_chord_id = chord_id

        cur.execute("BEGIN")
        for k,(hand,finger) in self.selected_keys.items():
            cur.execute("INSERT INTO key_presses (key_id, hand, finger, chord_id) VALUES (?,?,?,?)", (k,hand,finger,chord_id))
        conn.commit()

        ts = cur.execute("SELECT timestamp FROM key_presses WHERE chord_id=? ORDER BY timestamp DESC LIMIT 1", (chord_id,)).fetchone()[0]

        for k,(hand,finger) in self.selected_keys.items():
            self.tree.insert("",0,values=(k,hand,finger,ts,chord_id))

        self.draw_chord_on_history(self.selected_keys)

        for k,(hand,finger) in self.selected_keys.items():
            color = FINGER_COLORS.get(finger,"gray")
            self.canvas.itemconfig(self.key_rects[k], fill=color)
        self.root.after(500, lambda keys=list(self.selected_keys.keys()): [self.reset_key_color(k) for k in keys])

        self.selected_keys.clear()

    # =====================
    # Add note for current chord
    # =====================
    def add_note_for_selected_chord(self):
        dialog = HandFingerDialog(self.root,"Ghi chú","Nhập lời bài hát:")
        text = dialog.result
        if not text:
            return

        chord_id = self.current_chord_id

        cur.execute("INSERT INTO key_presses (note_text, chord_id) VALUES (?,?)", (text,chord_id))
        conn.commit()

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.tree.insert("","end",values=(text,"","",ts,chord_id))
        y = self.history_y
        self.history_canvas.create_text(10, y+15, anchor="w", text=text, fill="purple", font=("Arial",12,"italic"))
        self.history_y += 25
        self.history_canvas.config(scrollregion=self.history_canvas.bbox("all"))

    # =====================
    # Load history
    # =====================
    def load_history(self):
        self.tree.delete(*self.tree.get_children())
        self.history_canvas.delete("all")
        self.history_y = 0

        # Lấy dữ liệu, sắp xếp theo chord_id và timestamp
        rows = list(cur.execute(
            "SELECT key_id, hand, finger, timestamp, chord_id, note_text FROM key_presses ORDER BY chord_id, timestamp"
        ))

        # Gom dữ liệu theo chord_id
        keys_by_chord = {}
        notes_by_chord = {}
        for row in rows:
            key_id, hand, finger, ts, chord_id, note_text = row
            if note_text:
                notes_by_chord.setdefault(chord_id, []).append((note_text, ts))
            else:
                keys_by_chord.setdefault(chord_id, {})[key_id]=(hand,finger)
            self.tree.insert("","end",values=(key_id or note_text, hand or "", finger or "", ts, chord_id))

        # Vẽ chord và ghi chú cùng lúc
        for chord_id in sorted(set(list(keys_by_chord.keys()) + list(notes_by_chord.keys()))):
            keys = keys_by_chord.get(chord_id, {})
            notes = notes_by_chord.get(chord_id, [])
            self.draw_chord_on_history(keys)
            for note_text, ts in notes:
                y = self.history_y
                self.history_canvas.create_text(10, y+15, anchor="w", text=note_text, fill="purple", font=("Arial",12,"italic"))
                self.history_y += 25

    # =====================
    # Draw chord on canvas
    # =====================
    def draw_chord_on_history(self, keys_dict):
        screen_w = self.root.winfo_screenwidth()
        total_cycles = 7
        white_notes = 7
        white_width = screen_w // (total_cycles*white_notes)
        white_height = 30
        black_width = int(white_width*0.6)
        black_height = 20

        y_offset = self.history_y

        for c in range(total_cycles):
            cycle_offset = c*white_notes*white_width
            for i in range(white_notes):
                key_id = f"W{c}-{i}"
                finger = keys_dict.get(key_id,(None,0))[1]
                color = FINGER_COLORS.get(finger,"white") if finger else "white"
                self.history_canvas.create_rectangle(cycle_offset+i*white_width,y_offset,cycle_offset+(i+1)*white_width,y_offset+white_height,fill=color,outline="black")
            black_positions=[1,2,4,5,6]
            for bp in black_positions:
                key_id = f"B{c}-{bp}"
                finger = keys_dict.get(key_id,(None,0))[1]
                color = FINGER_COLORS.get(finger,"black") if finger else "black"
                x1=cycle_offset+bp*white_width-black_width//2
                x2=x1+black_width
                self.history_canvas.create_rectangle(x1,y_offset,x2,y_offset+black_height,fill=color,outline="black")

        self.history_y = y_offset + white_height + 5
        self.history_canvas.config(scrollregion=self.history_canvas.bbox("all"))

# =====================
# Run app
# =====================
root = tk.Tk()
app = PianoApp(root)
root.mainloop()
