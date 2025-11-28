import tkinter as tk
from tkinter import filedialog, messagebox
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip

# pip install moviepy==1.0.3

def select_videos():
    files = filedialog.askopenfilenames(
        title="Chọn 2 video để ghép",
        filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv")]
    )
    if len(files) != 2:
        messagebox.showerror("Lỗi", "Vui lòng chọn đúng 2 video.")
        return
    merge_videos(files[0], files[1])

def merge_videos(video1_path, video2_path):
    try:
        clip1 = VideoFileClip(video1_path)
        clip2 = VideoFileClip(video2_path)

        # Resize clip2 nếu khác kích thước clip1
        if clip1.size != clip2.size:
            clip2 = clip2.resize(clip1.size)

        # Đặt thời điểm bắt đầu cho clip
        clip1 = clip1.set_start(0)
        clip2 = clip2.set_start(clip1.duration)

        # Tạo CompositeVideoClip
        final_clip = CompositeVideoClip([clip1, clip2])
        final_clip.duration = clip1.duration + clip2.duration

        # Chọn nơi lưu
        save_path = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("MP4 files", "*.mp4")],
            title="Lưu video ghép"
        )
        if save_path:
            final_clip.write_videofile(save_path, codec="libx264", audio_codec="aac")
            messagebox.showinfo("Thành công", f"Video đã được lưu tại:\n{save_path}")
    except Exception as e:
        messagebox.showerror("Lỗi", str(e))

root = tk.Tk()
root.title("Ghép 2 Video bằng CompositeVideoClip")
root.geometry("400x150")

btn_select = tk.Button(
    root,
    text="Chọn 2 video và ghép",
    command=select_videos,
    font=("Arial", 12)
)
btn_select.pack(expand=True, fill="both", padx=20, pady=30)

root.mainloop()
