import tkinter as tk
from tkinter import messagebox
import sqlite3
from datetime import datetime

# =====================
# Màu các ngón tay
# =====================
FINGER_COLORS = {1: "red", 2: "orange", 3: "yellow", 4: "green", 5: "blue"}

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
# Dialog nhập tay/ngón/start/duration
# =====================
class KeyPressDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Nhập tay, ngón, thời gian")
        self.resizable(False, False)
        self.result = None

        tk.Label(self, text="Tay (A/B):").pack(padx=10, pady=2, anchor="w")
        self.entry_hand = tk.Entry(self)
        self.entry_hand.pack(padx=10, pady=2)
        self.entry_hand.focus_set()

        tk.Label(self, text="Ngón tay (1-5):").pack(padx=10, pady=2, anchor="w")
        self.entry_finger = tk.Entry(self)
        self.entry_finger.pack(padx=10, pady=2)

        tk.Label(self, text="Thời điểm bắt đầu (s):").pack(padx=10, pady=2, anchor="w")
        self.entry_start = tk.Entry(self)
        self.entry_start.pack(padx=10, pady=2)
        self.entry_start.insert(0, "0")

        tk.Label(self, text="Thời gian giữ (s):").pack(padx=10, pady=2, anchor="w")
        self.entry_duration = tk.Entry(self)
        self.entry_duration.pack(padx=10, pady=2)
        self.entry_duration.insert(0, "0.5")

        btn = tk.Button(self, text="OK", command=self.on_ok)
        btn.pack(pady=8)

        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def on_ok(self):
        try:
            hand = self.entry_hand.get().strip().upper()
            finger = int(self.entry_finger.get())
            start_time = float(self.entry_start.get())
            duration = float(self.entry_duration.get())
            if hand not in ("A", "B") or not (1 <= finger <= 5):
                raise ValueError
            self.result = (hand, finger, start_time, duration)
        except Exception:
            self.result = None
        self.destroy()


# =====================
# PianoApp full
# =====================
class PianoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Piano Key Press Recorder")
        self.root.state("zoomed")

        # selected keys before save
        self.selected_keys = {}

        # chord_counter: lấy max chord_id hiện có (nếu có)
        cur.execute("SELECT MAX(chord_id) FROM key_presses")
        row = cur.fetchone()
        self.chord_counter = row[0] if row and row[0] is not None else 0
        self.current_chord_id = self.chord_counter

        # UI
        self.main_frame = tk.Frame(root)
        self.main_frame.pack(fill="both", expand=True)

        btn_frame = tk.Frame(self.main_frame)
        btn_frame.pack(fill="x", padx=6, pady=4)
        tk.Button(btn_frame, text="Lưu hợp âm (Chord)", command=self.save_chord).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Thêm ghi chú", command=self.add_note_for_selected_chord).pack(side="left", padx=4)

        # History canvas + scrollbar
        self.visual_frame = tk.Frame(self.main_frame)
        self.visual_frame.pack(fill="both", expand=True)
        self.history_canvas = tk.Canvas(self.visual_frame, bg="lightgray", height=500)
        self.v_scroll = tk.Scrollbar(self.visual_frame, orient="vertical", command=self.history_canvas.yview)
        self.history_canvas.configure(yscrollcommand=self.v_scroll.set)
        self.v_scroll.pack(side="right", fill="y")
        self.history_canvas.pack(side="left", fill="both", expand=True)

        # bind right-click; use Button-3 (Windows) — for mac you may add Button-2 if needed
        self.history_canvas.bind("<Button-3>", self.on_right_click_history)

        # Piano canvas (top)
        self.canvas = None
        self.key_rects = {}
        self.create_piano_canvas()

        # Model for history display (list of chords in display order: newest first)
        # each item: {"chord_id":..., "keys":{key_id:(hand,finger,start,duration)}, "notes":[str,...], "is_from_db":bool}
        self.chords_data = []
        # list of regions for right-click lookup: {"index": idx, "y1":, "y2":}
        self.chord_regions = []

        # drawing start position (top margin)
        self.history_top_margin = 20
        self.history_x_margin = 8

        # load from DB and render
        self.load_history()

    # ---------------------
    # Create main piano (click to add key into selected_keys)
    # ---------------------
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

    def press_key(self, key_id):
        dialog = KeyPressDialog(self.root)
        if dialog.result:
            hand, finger, start_time, duration = dialog.result
            # mỗi ngón chỉ bấm 1 phím tại 1 thời điểm: override nếu trùng ngón trong selected_keys
            # (nếu cần khác, có thể kiểm tra)
            self.selected_keys[key_id] = (hand, finger, start_time, duration)
            color = FINGER_COLORS.get(finger, "gray")
            self.canvas.itemconfig(self.key_rects[key_id], fill=color)

    def reset_key_color(self, key_id):
        if key_id.startswith("W"):
            self.canvas.itemconfig(self.key_rects[key_id], fill="white")
        else:
            self.canvas.itemconfig(self.key_rects[key_id], fill="black")

    # ---------------------
    # Save chord -> persist to DB and reload
    # ---------------------
    def save_chord(self):
        if not self.selected_keys:
            messagebox.showwarning("Không có phím", "Bạn chưa chọn phím nào")
            return

        self.chord_counter += 1
        chord_id = self.chord_counter
        self.current_chord_id = chord_id

        cur.execute("BEGIN")
        for k, (hand, finger, start_time, duration) in self.selected_keys.items():
            cur.execute(
                "INSERT INTO key_presses (key_id, hand, finger, chord_id, start_time, duration) VALUES (?,?,?,?,?,?)",
                (k, hand, finger, chord_id, start_time, duration),
            )
        conn.commit()

        # highlight tạm thời
        for k, (hand, finger, start_time, duration) in self.selected_keys.items():
            color = FINGER_COLORS.get(finger, "gray")
            self.canvas.itemconfig(self.key_rects[k], fill=color)
        self.root.after(500, lambda keys=list(self.selected_keys.keys()): [self.reset_key_color(k) for k in keys])

        self.selected_keys.clear()

        # reload model + redraw
        self.load_history()

    # ---------------------
    # Add note to current chord (persist)
    # ---------------------
    def add_note_for_selected_chord(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Ghi chú")
        dialog.geometry("320x120")
        tk.Label(dialog, text="Nhập lời bài hát:").pack(padx=8, pady=6, anchor="w")
        entry = tk.Entry(dialog)
        entry.pack(padx=8, pady=4, fill="x")
        entry.focus_set()

        def on_ok():
            text = entry.get().strip()
            if text:
                chord_id = self.current_chord_id
                if chord_id is None:
                    # nếu chưa có chord hiện tại, tạo chord mới tự động
                    self.chord_counter += 1
                    chord_id = self.chord_counter
                    self.current_chord_id = chord_id
                cur.execute("INSERT INTO key_presses (note_text, chord_id) VALUES (?,?)", (text, chord_id))
                conn.commit()
                self.load_history()
            dialog.destroy()

        tk.Button(dialog, text="OK", command=on_ok).pack(pady=6)
        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)

    # ---------------------
    # Load data from DB -> build self.chords_data -> redraw history
    # ---------------------
    def load_history(self):
        # fetch ordered by chord_id ascending, timestamp ascending
        rows = list(
            cur.execute(
                "SELECT key_id, hand, finger, start_time, duration, chord_id, note_text, timestamp FROM key_presses ORDER BY chord_id, timestamp"
            )
        )

        chord_map = {}
        notes_map = {}
        order = []
        for row in rows:
            key_id, hand, finger, start_time, duration, chord_id, note_text, ts = row
            if chord_id not in order:
                order.append(chord_id)
            if note_text:
                notes_map.setdefault(chord_id, []).append((note_text, ts))
            else:
                chord_map.setdefault(chord_id, {})[key_id] = (hand, finger, start_time, duration)

        # build chords_data as list newest-first (so we draw in that order top->down)
        self.chords_data = []
        for cid in reversed(order):
            keys = chord_map.get(cid, {})
            notes = [n for (n,_) in notes_map.get(cid, [])]
            self.chords_data.append({"chord_id": cid, "keys": keys, "notes": notes, "is_from_db": True})

        # redraw
        self.redraw_history()

    # ---------------------
    # Redraw the entire history canvas from model
    # ---------------------
    def redraw_history(self):
        self.history_canvas.delete("all")
        self.chord_regions.clear()

        # start drawing from top margin downward
        self.history_y = self.history_top_margin

        for idx, chord in enumerate(self.chords_data):
            keys = chord.get("keys", {})
            notes = chord.get("notes", [])
            chord_height = self.draw_chord_on_history(keys, record_region=True, record_index=idx)
            # draw notes below the chord_top (inside that chord region), stacked if multiple
            # draw_chord_on_history already created region and moved history_y by chord_height
            # we draw notes at chord region's top + 4 px
            # find last region appended for this idx
            region = self.chord_regions[-1] if self.chord_regions else None
            if region and region["index"] == idx:
                y_text = region["y1"] + 4
                for note_text in notes:
                    self.history_canvas.create_text(self.history_x_margin, y_text, anchor="w",
                                                    text=note_text, fill="purple", font=("Arial", 12, "italic"))
                    y_text += 16

        # update scrollregion
        bbox = self.history_canvas.bbox("all")
        if bbox:
            self.history_canvas.config(scrollregion=bbox)

    # ---------------------
    # Right-click: show menu for chord at click
    # ---------------------
    def on_right_click_history(self, event):
        # event coordinates -> canvas coords (account for scroll)
        cy = self.history_canvas.canvasy(event.y)
        clicked = None
        for region in self.chord_regions:
            if region["y1"] <= cy <= region["y2"]:
                clicked = region
                break
        if not clicked:
            return
        idx = clicked["index"]

        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Thêm bản ghi trống phía sau", command=lambda: self.insert_empty_after(idx))
        menu.add_command(label="Xóa bản ghi này", command=lambda: self.delete_chord(idx))
        try:
            menu.post(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ---------------------
    # Insert empty chord after index (UI-only)
    # ---------------------
    def insert_empty_after(self, idx):
        insert_pos = idx + 1
        empty = {"chord_id": None, "keys": {}, "notes": [], "is_from_db": False}
        self.chords_data.insert(insert_pos, empty)
        self.redraw_history()
        # NOTE: currently UI-only. If you want to persist to DB:
        # - create a new chord_id (e.g. self.chord_counter += 1)
        # - insert a marker row into key_presses with that chord_id (or leave empty and only note_text)
        # - then call self.load_history()

    # ---------------------
    # Delete chord at index (UI-only)
    # ---------------------
    def delete_chord(self, idx):
        if 0 <= idx < len(self.chords_data):
            if not messagebox.askyesno("Xóa", "Bạn có chắc muốn xóa bản ghi này (chỉ trên giao diện)?"):
                return
            # If this chord is from DB and you want to delete DB rows, handle here:
            # chord = self.chords_data[idx]
            # if chord.get("is_from_db") and chord.get("chord_id") is not None:
            #     cur.execute("DELETE FROM key_presses WHERE chord_id=?", (chord['chord_id'],))
            #     conn.commit()
            del self.chords_data[idx]
            self.redraw_history()

    # ---------------------
    # draw one chord region on history canvas
    # keys_dict: {key_id: (hand,finger,start,duration)}
    # returns chord_height; if record_region True, appends region {index,y1,y2}
    # ---------------------
    def draw_chord_on_history(self, keys_dict, record_region=False, record_index=None):
        screen_w = self.root.winfo_screenwidth()
        total_cycles = 7
        white_notes = 7
        white_width = screen_w // (total_cycles * white_notes)

        # visual sizes
        white_height = 20
        black_height = 15
        black_width = int(white_width * 0.6)

        # time -> pixel scale
        scale_time = 50

        # max end time in this chord (start + duration)
        max_end = max((start + duration for (_h, _f, start, duration) in keys_dict.values()), default=0)

        top_padding = 6
        chord_height = white_height + max_end * scale_time + top_padding

        # chord top = current history_y
        chord_top = self.history_y
        base_y = chord_top + max_end * scale_time  # baseline where keys sit

        # draw cycles
        for c in range(total_cycles):
            cycle_offset = c * white_notes * white_width

            # white keys
            for i in range(white_notes):
                key_id = f"W{c}-{i}"
                x1 = cycle_offset + i * white_width
                x2 = x1 + white_width

                # background white key at baseline
                self.history_canvas.create_rectangle(x1, base_y, x2, base_y + white_height, fill="white", outline="black")

                if key_id in keys_dict:
                    hand, finger, start, duration = keys_dict[key_id]
                    color = FINGER_COLORS.get(finger, "gray")

                    # pressed color over white key
                    self.history_canvas.create_rectangle(x1, base_y, x2, base_y + white_height, fill=color, outline="black")

                    # bar for start->start+duration (top->down)
                    bar_bottom = base_y - start * scale_time
                    bar_top = bar_bottom - duration * scale_time

                    # clip inside chord_top..base_y
                    if bar_top < chord_top:
                        bar_top = chord_top
                    if bar_bottom > base_y:
                        bar_bottom = base_y
                    self.history_canvas.create_rectangle(x1, bar_top, x2, bar_bottom, fill=color, outline="black")

            # black keys
            black_positions = [1, 2, 4, 5, 6]
            for bp in black_positions:
                key_id = f"B{c}-{bp}"
                x1 = cycle_offset + bp * white_width - black_width // 2
                x2 = x1 + black_width

                self.history_canvas.create_rectangle(x1, base_y, x2, base_y + black_height, fill="black", outline="black")

                if key_id in keys_dict:
                    hand, finger, start, duration = keys_dict[key_id]
                    color = FINGER_COLORS.get(finger, "gray")
                    self.history_canvas.create_rectangle(x1, base_y, x2, base_y + black_height, fill=color, outline="black")

                    bar_bottom = base_y - start * scale_time
                    bar_top = bar_bottom - duration * scale_time
                    if bar_top < chord_top:
                        bar_top = chord_top
                    if bar_bottom > base_y:
                        bar_bottom = base_y
                    self.history_canvas.create_rectangle(x1, bar_top, x2, bar_bottom, fill=color, outline="black")

        # record region bounds (for clicking)
        region_y1 = chord_top
        region_y2 = base_y + white_height  # bottom of key area

        if record_region and record_index is not None:
            # append region
            self.chord_regions.append({"index": record_index, "y1": region_y1, "y2": region_y2})

        # advance history_y downward for next chord
        self.history_y += chord_height
        return chord_height


# =================================
# Run app
# =================================
if __name__ == "__main__":
    root = tk.Tk()
    app = PianoApp(root)
    root.mainloop()
