import tkinter as tk
from tkinter import filedialog, messagebox
import cv2
from PIL import Image, ImageTk
from moviepy.video.io.VideoFileClip import VideoFileClip
import threading

# pip install moviepy==2.2.1

class VideoCutter:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Cutter with Timeline")

        # Variables
        self.video_path = ""
        self.cap = None
        self.total_frames = 0
        self.fps = 25
        self.current_frame = 0
        self.playing = False

        # Widgets
        tk.Button(root, text="Chọn Video", command=self.load_video).pack()
        self.canvas = tk.Canvas(root, width=640, height=360)
        self.canvas.pack()

        tk.Label(root, text="Start Time (s)").pack()
        self.start_slider = tk.Scale(root, from_=0, to=100, orient="horizontal", length=600, command=self.update_start)
        self.start_slider.pack()

        tk.Label(root, text="End Time (s)").pack()
        self.end_slider = tk.Scale(root, from_=0, to=100, orient="horizontal", length=600, command=self.update_end)
        self.end_slider.pack()

        tk.Button(root, text="Cắt Video", command=self.cut_video).pack(pady=5)

        self.start_time = 0
        self.end_time = 0

    def load_video(self):
        path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4;*.avi;*.mov")])
        if not path:
            return
        self.video_path = path
        self.cap = cv2.VideoCapture(self.video_path)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.duration = self.total_frames / self.fps

        self.start_slider.config(to=int(self.duration))
        self.start_slider.set(0)

        self.end_slider.config(to=int(self.duration))
        self.end_slider.set(int(self.duration))

        self.start_time = 0
        self.end_time = self.duration

        self.playing = True
        threading.Thread(target=self.play_video, daemon=True).start()

    def play_video(self):
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        while self.cap.isOpened() and self.playing:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
            ret, frame = self.cap.read()
            if not ret:
                break
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Tính scale để vừa canvas, giữ tỉ lệ
            h, w, _ = frame.shape
            scale_w = canvas_width / w
            scale_h = canvas_height / h
            scale = min(scale_w, scale_h)  # chọn tỉ lệ nhỏ hơn để vừa canvas

            new_w = int(w * scale)
            new_h = int(h * scale)
            frame_resized = cv2.resize(frame, (new_w, new_h))

            img = Image.fromarray(frame_resized)
            imgtk = ImageTk.PhotoImage(image=img)

            # Clear canvas trước khi vẽ
            self.canvas.delete("all")
            # Vẽ frame, căn giữa
            self.canvas.create_image((canvas_width - new_w) // 2, (canvas_height - new_h) // 2, anchor="nw",
                                     image=imgtk)
            self.canvas.imgtk = imgtk

            # Cập nhật frame tiếp theo
            delay = int(1000 / self.fps)
            self.root.update()
            self.current_frame += 1
            if self.current_frame >= self.total_frames:
                self.current_frame = 0

    def update_start(self, val):
        self.start_time = int(val)
        self.current_frame = int(self.start_time * self.fps)

    def update_end(self, val):
        self.end_time = int(val)
        if self.current_frame > self.end_time * self.fps:
            self.current_frame = int(self.start_time * self.fps)

    def cut_video(self):
        if not self.video_path:
            messagebox.showerror("Error", "No video selected")
            return
        save_path = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4 files","*.mp4")])
        if not save_path:
            return
        clip = VideoFileClip(self.video_path).subclip(self.start_time, self.end_time)
        clip.write_videofile(save_path, codec="libx264", audio_codec="aac")
        messagebox.showinfo("Done", f"Saved to {save_path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoCutter(root)
    root.mainloop()
