import os
import re
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import sqlite3
from datetime import datetime

# =====================
# Màu các ngón tay
# =====================
FINGER_COLORS = {1: "red", 2: "orange", 3: "yellow", 4: "green", 5: "blue"}

# =====================
# Ensure songs folder and default DB
# =====================
SONGS_FOLDER = "songs"
os.makedirs(SONGS_FOLDER, exist_ok=True)
DEFAULT_DB = os.path.join(SONGS_FOLDER, "default_song.db")

# =====================
# Database (module-level for compatibility with existing code)
# =====================
conn = sqlite3.connect(DEFAULT_DB)
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
    def __init__(self, parent, hand="A", finger=1, start_time=0, duration=1):
        super().__init__(parent)
        self.title("Nhập tay, ngón, thời gian")
        self.resizable(False, False)
        self.result = None

        tk.Label(self, text="Tay (A/B):").pack(padx=10, pady=2)
        self.entry_hand = tk.Entry(self)
        self.entry_hand.pack(padx=10, pady=2)
        self.entry_hand.insert(0, hand)

        tk.Label(self, text="Ngón tay (1-5):").pack(padx=10, pady=2)
        self.entry_finger = tk.Entry(self)
        self.entry_finger.pack(padx=10, pady=2)
        self.entry_finger.insert(0, finger)

        tk.Label(self, text="Thời điểm bắt đầu (s):").pack(padx=10, pady=2)
        self.entry_start = tk.Entry(self)
        self.entry_start.pack(padx=10, pady=2)
        self.entry_start.insert(0, start_time)

        tk.Label(self, text="Thời gian giữ (s):").pack(padx=10, pady=2)
        self.entry_duration = tk.Entry(self)
        self.entry_duration.pack(padx=10, pady=2)
        self.entry_duration.insert(0, duration)

        tk.Button(self, text="OK", command=self.on_ok).pack(pady=5)

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

def ensure_songs_folder():
    if not os.path.exists(SONGS_FOLDER):
        os.makedirs(SONGS_FOLDER)
# =====================
# PianoApp full (keeps structure of your code, adds DB selection/create)
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

        # top controls: save, add note, select db, create new db
        btn_frame = tk.Frame(self.main_frame)
        btn_frame.pack(fill="x", padx=6, pady=4)
        tk.Button(btn_frame, text="Lưu hợp âm (Chord)", command=self.save_chord).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Thêm ghi chú", command=self.add_note_for_selected_chord).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Chọn bài (DB)", command=self.select_db).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Tạo bài mới", command=self.create_new_db).pack(side="left", padx=4)

        self.db_label = tk.Label(btn_frame, text="DB: (chưa mở)", fg="blue")
        self.db_label.pack(side="left", padx=10)

        # History canvas + scrollbar
        self.visual_frame = tk.Frame(self.main_frame)
        self.visual_frame.pack(fill="both", expand=True)
        self.history_canvas = tk.Canvas(self.visual_frame, bg="lightgray", height=500)
        self.v_scroll = tk.Scrollbar(self.visual_frame, orient="vertical", command=self.history_canvas.yview)
        self.history_canvas.configure(yscrollcommand=self.v_scroll.set)
        self.v_scroll.pack(side="right", fill="y")
        self.history_canvas.pack(side="left", fill="both", expand=True)

        # bind right-click; use Button-3 (Windows)
        self.history_canvas.bind("<Button-3>", self.on_right_click_history)

        # Piano canvas (top)
        self.canvas = None
        self.key_rects = {}
        self.create_piano_canvas()

        # Model for history display (list of chords in display order: newest first)
        self.chords_data = []
        self.chord_regions = []

        # drawing start position (top margin)
        self.history_top_margin = 20
        self.history_x_margin = 8

        self.selected_region_idx = None  # index của bản ghi được chọn bằng chuột phải

        self.editing_chord_idx = None  # None nếu không đang edit
        self.editing_selected_keys = {}  # lưu các phím đang edit cho chord này

        # current DB path
        self.current_db_path = DEFAULT_DB

        # load from DB and render
        self.load_history()

    def select_db(self):
        ensure_songs_folder()
        db_path = filedialog.askopenfilename(
            initialdir=SONGS_FOLDER,
            title="Chọn file DB",
            filetypes=[("SQLite DB files", "*.db")],
        )
        if not db_path:
            return
        try:
            global conn, cur
            if conn:
                conn.close()
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            # load lại history
            self.load_history()
            messagebox.showinfo("Đã chọn bài", f"Đang sử dụng DB: {os.path.basename(db_path)}")
            self.current_db_name = os.path.basename(db_path)
            self.db_label.config(text=f"DB: {self.current_db_name}")

        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở DB:\n{e}")

    def create_new_db(self):
        ensure_songs_folder()
        name = tk.simpledialog.askstring("Tạo bài mới", "Nhập tên bài (chỉ a-z, A-Z, 0-9, không dấu cách):")
        if not name:
            return
        import re
        if not re.match(r"^[A-Za-z0-9_]+$", name):
            messagebox.showerror("Lỗi tên", "Tên bài không hợp lệ!")
            return
        db_path = os.path.join(SONGS_FOLDER, f"{name}.db")
        if os.path.exists(db_path):
            messagebox.showerror("Lỗi", "File DB đã tồn tại!")
            return
        try:
            global conn, cur
            if conn:
                conn.close()
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            # tạo bảng như mặc định
            cur.execute("""
                        CREATE TABLE IF NOT EXISTS key_presses
                        (
                            id
                            INTEGER
                            PRIMARY
                            KEY
                            AUTOINCREMENT,
                            key_id
                            TEXT,
                            hand
                            TEXT,
                            finger
                            INTEGER,
                            chord_id
                            REAL
                            DEFAULT
                            0,
                            timestamp
                            DATETIME
                            DEFAULT
                            CURRENT_TIMESTAMP,
                            start_time
                            REAL
                            DEFAULT
                            0,
                            duration
                            REAL
                            DEFAULT
                            0.5,
                            note_text
                            TEXT
                        )
                        """)
            conn.commit()
            # load lại history (trống)
            self.load_history()
            messagebox.showinfo("Tạo bài", f"Đã tạo DB mới: {name}.db")
            self.current_db_name = name + ".db"
            self.db_label.config(text=f"DB: {self.current_db_name}")

        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể tạo DB mới:\n{e}")
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
                self.canvas.tag_bind(rect, "<Button-1>", lambda e, k=key_id: self.quick_press_key(k))
                self.canvas.tag_bind(rect, "<Double-Button-1>", lambda e, k=key_id: self.edit_key_dialog(k))
                self.canvas.tag_bind(rect, "<Button-3>", lambda e,k=key_id: self.delete_key_from_chord(k))


            black_positions = [1, 2, 4, 5, 6]
            for bp in black_positions:
                x1 = cycle_offset + bp * white_width - black_width // 2
                x2 = x1 + black_width
                rect = self.canvas.create_rectangle(x1, 0, x2, black_height, fill="black", outline="black")
                key_id = f"B{c}-{bp}"
                self.key_rects[key_id] = rect
                self.canvas.tag_bind(rect, "<Button-1>", lambda e, k=key_id: self.quick_press_key(k))
                self.canvas.tag_bind(rect, "<Double-Button-1>", lambda e, k=key_id: self.edit_key_dialog(k))
                self.canvas.tag_bind(rect, "<Button-3>", lambda e,k=key_id: self.delete_key_from_chord(k))


    def quick_press_key(self, key_id):
        hand = "A"
        finger = 1
        start_time = 0
        duration = 1

        # nếu đang edit chord
        if self.editing_chord_idx is not None:
            self.editing_selected_keys[key_id] = (hand, finger, start_time, duration)
        else:
            self.selected_keys[key_id] = (hand, finger, start_time, duration)

        color = FINGER_COLORS.get(finger, "gray")
        self.canvas.itemconfig(self.key_rects[key_id], fill=color)

    def edit_key_dialog(self, key_id):
        # Lấy dữ liệu cũ của phím
        if self.editing_chord_idx is not None:
            old = self.editing_selected_keys.get(key_id, ("A", 1, 0, 1))
        else:
            old = self.selected_keys.get(key_id, ("A", 1, 0, 1))

        old_hand, old_finger, old_start, old_duration = old

        # mở dialog với dữ liệu cũ
        dialog = KeyPressDialog(
            self.root,
            hand=old_hand,
            finger=old_finger,
            start_time=old_start,
            duration=old_duration
        )

        if dialog.result:
            hand, finger, start_time, duration = dialog.result

            if self.editing_chord_idx is not None:
                self.editing_selected_keys[key_id] = (hand, finger, start_time, duration)
            else:
                self.selected_keys[key_id] = (hand, finger, start_time, duration)

            color = FINGER_COLORS.get(finger, "gray")
            self.canvas.itemconfig(self.key_rects[key_id], fill=color)

    def delete_key_from_chord(self, key_id):
        # Xóa nốt nhấn nhầm
        if self.editing_chord_idx is not None:
            if key_id in self.editing_selected_keys:
                del self.editing_selected_keys[key_id]
                self.reset_key_color(key_id)
        else:
            if key_id in self.selected_keys:
                del self.selected_keys[key_id]
                self.reset_key_color(key_id)

    def press_key(self, key_id):
        dialog = KeyPressDialog(self.root)
        if dialog.result:
            hand, finger, start_time, duration = dialog.result

            if self.editing_chord_idx is not None:
                # đang edit chord
                self.editing_selected_keys[key_id] = (hand, finger, start_time, duration)
            else:
                # bình thường
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
                    self.history_canvas.tag_bind(t, "<Button-3>",
                                                 lambda e, note=note, idx=idx: self.delete_note_from_chord(idx, note))
                    y_text += 16

        # update scrollregion
        bbox = self.history_canvas.bbox("all")
        if bbox:
            self.history_canvas.config(scrollregion=bbox)

    # ---------------------
    # Right-click: show menu for chord at click
    # ---------------------
    def highlight_chord(self, idx):
        # dùng vùng chord_regions
        for region in self.chord_regions:
            if region["index"] == idx:
                # vẽ hình chữ nhật bán trong suốt phía sau
                self.history_canvas.create_rectangle(
                    0, region["y1"], self.history_canvas.winfo_width(), region["y2"],
                    fill="yellow", stipple="gray50", tags=f"highlight_{idx}"
                )
                break

    def unhighlight_chord(self, idx):
        self.history_canvas.delete(f"highlight_{idx}")

    def on_right_click_history(self, event):
        cy = self.history_canvas.canvasy(event.y)
        clicked = None
        for region in self.chord_regions:
            if region["y1"] <= cy <= region["y2"]:
                clicked = region
                break
        if not clicked:
            return
        idx = clicked["index"]

        # --- Xóa dấu hiệu cũ ---
        if self.selected_region_idx is not None:
            self.unhighlight_chord(self.selected_region_idx)

        # --- Lưu và highlight bản ghi hiện tại ---
        self.selected_region_idx = idx
        self.highlight_chord(idx)

        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Thêm bản ghi trống phía sau", command=lambda: self.insert_empty_after(idx))
        menu.add_command(label="Chỉnh sửa bản ghi", command=lambda: self.load_chord_to_piano(clicked["index"]))
        menu.add_command(label="Nhân đôi bản ghi", command=lambda: self.duplicate_chord(idx))
        menu.add_command(label="Xóa bản ghi này", command=lambda: self.delete_chord(idx))
        try:
            menu.post(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def load_chord_to_piano(self, chord_idx):
        chord = self.chords_data[chord_idx]
        keys = chord.get("keys", {})

        # Set trạng thái edit
        self.editing_chord_idx = chord_idx
        self.editing_selected_keys = keys.copy()  # clone để chỉnh sửa

        # Reset piano canvas
        for k in self.key_rects:
            if k.startswith("W"):
                self.canvas.itemconfig(self.key_rects[k], fill="white")
            else:
                self.canvas.itemconfig(self.key_rects[k], fill="black")

        # Highlight các phím đang chọn
        for k, (hand, finger, start, duration) in self.editing_selected_keys.items():
            color = FINGER_COLORS.get(finger, "gray")
            self.canvas.itemconfig(self.key_rects[k], fill=color)

        # Thêm nút lưu chord hiện tại (overwrite)
        if not hasattr(self, "btn_save_edit"):
            self.btn_save_edit = tk.Button(self.main_frame, text="Lưu bản ghi chỉnh sửa",
                                           command=self.save_edited_chord)
            self.btn_save_edit.pack(pady=5)

    def press_key(self, key_id):
        dialog = KeyPressDialog(self.root)
        if dialog.result:
            hand, finger, start_time, duration = dialog.result

            if self.editing_chord_idx is not None:
                # đang edit chord
                self.editing_selected_keys[key_id] = (hand, finger, start_time, duration)
            else:
                # bình thường
                self.selected_keys[key_id] = (hand, finger, start_time, duration)

            color = FINGER_COLORS.get(finger, "gray")
            self.canvas.itemconfig(self.key_rects[key_id], fill=color)

    def save_edited_chord(self):
        if self.editing_chord_idx is None:
            return

        chord = self.chords_data[self.editing_chord_idx]
        chord_id = chord.get("chord_id")

        # Xóa phím cũ trong DB (nếu có)
        if chord_id is not None:
            cur.execute("DELETE FROM key_presses WHERE chord_id=? AND key_id IS NOT NULL", (chord_id,))
            conn.commit()

        # Lưu các phím mới
        for k, (hand, finger, start, duration) in self.editing_selected_keys.items():
            if chord_id is not None:
                cur.execute(
                    "INSERT INTO key_presses (key_id, hand, finger, chord_id, start_time, duration) VALUES (?,?,?,?,?,?)",
                    (k, hand, finger, chord_id, start, duration)
                )
        conn.commit()

        # Cập nhật model
        chord["keys"] = self.editing_selected_keys.copy()

        # Reset piano canvas
        for k in self.key_rects:
            if k.startswith("W"):
                self.canvas.itemconfig(self.key_rects[k], fill="white")
            else:
                self.canvas.itemconfig(self.key_rects[k], fill="black")

        # Xóa nút lưu edit
        if hasattr(self, "btn_save_edit"):
            self.btn_save_edit.destroy()
            del self.btn_save_edit

        self.editing_chord_idx = None
        self.editing_selected_keys = {}

        # redraw history
        self.redraw_history()

    # ---------------------
    # Insert empty chord after index (UI-only)
    # ---------------------
    def insert_empty_after(self, idx):
        # Lấy chord_id của bản ghi hiện tại
        self.chords_data.sort(key=lambda x: x["chord_id"])

        current_chord_id = self.chords_data[idx]["chord_id"]

        # Lấy chord_id của bản ghi tiếp theo (nếu có)
        if idx + 1 < len(self.chords_data):
            next_chord_id = self.chords_data[idx + 1]["chord_id"]
            # chord_id mới nằm giữa 2 chord_id
            new_chord_id = (current_chord_id + next_chord_id) / 2
        else:
            # Nếu bản ghi hiện tại là cuối cùng, tạo chord_id mới lớn hơn tất cả
            self.chord_counter += 1
            new_chord_id = self.chord_counter

        # chèn bản ghi "trống" vào DB với chord_id này
        cur.execute("INSERT INTO key_presses (chord_id) VALUES (?)", (new_chord_id,))
        conn.commit()

        # thêm vào model
        empty = {"chord_id": new_chord_id, "keys": {}, "notes": [], "is_from_db": True}
        self.chords_data.insert(idx + 1, empty)
        self.chords_data.sort(key=lambda x: x["chord_id"])

        # vẽ lại history mà không cần load lại DB
        self.load_history()

    # ---------------------
    # Delete chord at index (UI-only)
    # ---------------------
    def delete_chord(self, idx):
        if 0 <= idx < len(self.chords_data):
            if not messagebox.askyesno("Xóa", "Bạn có chắc muốn xóa bản ghi này?"):
                return
            chord = self.chords_data[idx]
            chord_id = chord.get("chord_id")
            if chord_id is not None:
                cur.execute("DELETE FROM key_presses WHERE chord_id=?", (chord_id,))
                conn.commit()
            del self.chords_data[idx]
            self.load_history()  # reload từ DB

    def duplicate_chord(self, idx):
        # self.chords_data.sort(key=lambda x: x["chord_id"])
        original = self.chords_data[idx]

        current_chord_id = self.chords_data[idx]["chord_id"]
        # Lấy chord_id của bản ghi tiếp theo (nếu có)
        if idx + 1 < len(self.chords_data):
            next_chord_id = self.chords_data[idx + 1]["chord_id"]
            # chord_id mới nằm giữa 2 chord_id
            new_chord_id = (current_chord_id + next_chord_id) / 2
        else:
            # Nếu bản ghi hiện tại là cuối cùng, tạo chord_id mới lớn hơn tất cả
            self.chord_counter += 1
            new_chord_id = self.chord_counter

        # Chèn phím từ bản gốc
        for k, (hand, finger, start, duration) in original.get("keys", {}).items():
            cur.execute(
                "INSERT INTO key_presses (key_id, hand, finger, chord_id, start_time, duration) VALUES (?,?,?,?,?,?)",
                (k, hand, finger, new_chord_id, start, duration)
            )

        # Chèn ghi chú
        for note in original.get("notes", []):
            cur.execute(
                "INSERT INTO key_presses (note_text, chord_id) VALUES (?,?)",
                (note, new_chord_id)
            )

        conn.commit()

        # Thêm vào model
        new_chord = {
            "chord_id": new_chord_id,
            "keys": original.get("keys", {}).copy(),
            "notes": original.get("notes", []).copy(),
            "is_from_db": True
        }
        self.chords_data.insert(idx + 1, new_chord)
        self.chords_data.sort(key=lambda x: x["chord_id"])
        self.load_history()

    # ---------------------
    # draw one chord region on history canvas
    # keys_dict: {key_id: (hand,finger,start,duration)}
    # returns chord_height; if record_region True, appends region {index,y1,y2}
    # ---------------------

    def delete_note_from_chord(self, idx, note_text):
        cid = self.chords_data[idx]["chord_id"]
        self.cur.execute("DELETE FROM key_presses WHERE chord_id=? AND note_text=?",(cid,note_text))
        self.conn.commit()
        self.load_history()

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
