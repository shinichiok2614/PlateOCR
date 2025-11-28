import cv2
import tkinter as tk
from tkinter import filedialog, messagebox
from threading import Thread
import os

# =======================
# Biến toàn cục
# =======================
video_path = ""
cap = None
playing = False
video_width = 0
video_height = 0
scale_ratio = 1.0

# Khung crop: x, y, w, h
rect = [50, 50, 200, 150]
dragging = False
resizing = False
resize_dir = None  # 'tl','tr','bl','br','t','b','l','r'
mouse_offset = (0, 0)
min_size = 30  # chiều rộng/chiều cao tối thiểu
corner_size = 10
edge_size = 8

# =======================
# Mouse callback
# =======================
def mouse_callback(event, x, y, flags, param):
    global rect, dragging, resizing, resize_dir, mouse_offset
    x = int(x / scale_ratio)
    y = int(y / scale_ratio)
    rx, ry, rw, rh = rect

    # Góc
    corners = {
        'tl': (rx, ry),
        'tr': (rx+rw, ry),
        'bl': (rx, ry+rh),
        'br': (rx+rw, ry+rh)
    }

    # Cạnh: trên, dưới, trái, phải
    edges = {
        't': ((rx+edge_size, ry), (rx+rw-edge_size, ry)),
        'b': ((rx+edge_size, ry+rh), (rx+rw-edge_size, ry+rh)),
        'l': ((rx, ry+edge_size), (rx, ry+rh-edge_size)),
        'r': ((rx+rw, ry+edge_size), (rx+rw, ry+rh-edge_size))
    }

    if event == cv2.EVENT_LBUTTONDOWN:
        # Kiểm tra góc trước
        for key, (cx, cy) in corners.items():
            if abs(x - cx) <= corner_size and abs(y - cy) <= corner_size:
                resizing = True
                resize_dir = key
                return
        # Kiểm tra cạnh
        for key, ((x1, y1), (x2, y2)) in edges.items():
            if key in ['t','b'] and y1-edge_size <= y <= y1+edge_size and x1 <= x <= x2:
                resizing = True
                resize_dir = key
                return
            if key in ['l','r'] and x1-edge_size <= x <= x1+edge_size and y1 <= y <= y2:
                resizing = True
                resize_dir = key
                return
        # Kiểm tra kéo trong khung
        if rx <= x <= rx+rw and ry <= y <= ry+rh:
            dragging = True
            mouse_offset = (x - rx, y - ry)

    elif event == cv2.EVENT_LBUTTONUP:
        dragging = False
        resizing = False
        resize_dir = None

    elif event == cv2.EVENT_MOUSEMOVE:
        if dragging:
            new_x = max(0, min(video_width - rw, x - mouse_offset[0]))
            new_y = max(0, min(video_height - rh, y - mouse_offset[1]))
            rect[0] = new_x
            rect[1] = new_y
        elif resizing:
            # Resize các góc
            if resize_dir == 'tl':
                new_x = max(0, min(rx+rw-min_size, x))
                new_y = max(0, min(ry+rh-min_size, y))
                rect[2] = rw + (rx - new_x)
                rect[3] = rh + (ry - new_y)
                rect[0] = new_x
                rect[1] = new_y
            elif resize_dir == 'tr':
                new_x = min(video_width, max(rx+min_size, x))
                new_y = max(0, min(ry+rh-min_size, y))
                rect[2] = new_x - rx
                rect[3] = rh + (ry - new_y)
                rect[1] = new_y
            elif resize_dir == 'bl':
                new_x = max(0, min(rx+rw-min_size, x))
                new_y = min(video_height, max(ry+min_size, y))
                rect[2] = rw + (rx - new_x)
                rect[3] = new_y - ry
                rect[0] = new_x
            elif resize_dir == 'br':
                new_x = min(video_width, max(rx+min_size, x))
                new_y = min(video_height, max(ry+min_size, y))
                rect[2] = new_x - rx
                rect[3] = new_y - ry
            # Resize cạnh
            elif resize_dir == 't':
                new_y = max(0, min(ry+rh-min_size, y))
                rect[3] = rh + (ry - new_y)
                rect[1] = new_y
            elif resize_dir == 'b':
                new_y = min(video_height, max(ry+min_size, y))
                rect[3] = new_y - ry
            elif resize_dir == 'l':
                new_x = max(0, min(rx+rw-min_size, x))
                rect[2] = rw + (rx - new_x)
                rect[0] = new_x
            elif resize_dir == 'r':
                new_x = min(video_width, max(rx+min_size, x))
                rect[2] = new_x - rx

# =======================
# Chọn video
# =======================
def select_video():
    global video_path, cap, playing, video_width, video_height, scale_ratio
    video_path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.avi *.mov")])
    if video_path:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            messagebox.showerror("Error", "Không mở được video!")
            return

        video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Lấy kích thước màn hình
        screen_width = root.winfo_screenwidth() - 100
        screen_height = root.winfo_screenheight() - 150
        ratio_w = screen_width / video_width
        ratio_h = screen_height / video_height
        scale_ratio = min(ratio_w, ratio_h, 1.0)

        playing = True
        Thread(target=play_video).start()

# =======================
# Play video
# =======================
def play_video():
    global cap, playing, scale_ratio, rect
    cv2.namedWindow("Video Preview")
    cv2.setMouseCallback("Video Preview", mouse_callback)

    while playing and cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        display_frame = frame.copy()
        rx, ry, rw, rh = rect
        cv2.rectangle(display_frame, (rx, ry), (rx+rw, ry+rh), (0, 255, 0), 2)

        # Vẽ các góc đỏ
        for (cx, cy) in [(rx, ry), (rx+rw, ry), (rx, ry+rh), (rx+rw, ry+rh)]:
            cv2.rectangle(display_frame, (cx-5, cy-5), (cx+5, cy+5), (0,0,255), -1)

        # Vẽ các cạnh xanh dương
        cv2.line(display_frame, (rx+edge_size, ry), (rx+rw-edge_size, ry), (255,0,0), 2)
        cv2.line(display_frame, (rx+edge_size, ry+rh), (rx+rw-edge_size, ry+rh), (255,0,0), 2)
        cv2.line(display_frame, (rx, ry+edge_size), (rx, ry+rh-edge_size), (255,0,0), 2)
        cv2.line(display_frame, (rx+rw, ry+edge_size), (rx+rw, ry+rh-edge_size), (255,0,0), 2)

        # Resize frame để vừa màn hình
        disp_w = int(frame.shape[1] * scale_ratio)
        disp_h = int(frame.shape[0] * scale_ratio)
        display_frame_resized = cv2.resize(display_frame, (disp_w, disp_h))

        cv2.imshow("Video Preview", display_frame_resized)
        if cv2.waitKey(30) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    playing = False

# =======================
# Crop & Save video
# =======================
def crop_and_save():
    global video_path, rect, video_width, video_height
    if not video_path:
        messagebox.showwarning("Warning", "Chưa chọn video!")
        return

    cap = cv2.VideoCapture(video_path)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    fps = cap.get(cv2.CAP_PROP_FPS)

    rx, ry, rw, rh = rect
    rx = max(0, min(rx, video_width - rw))
    ry = max(0, min(ry, video_height - rh))
    output_path = os.path.splitext(video_path)[0] + "_crop.mp4"
    out = cv2.VideoWriter(output_path, fourcc, fps, (rw, rh))

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        cropped_frame = frame[ry:ry+rh, rx:rx+rw]
        out.write(cropped_frame)

    cap.release()
    out.release()
    messagebox.showinfo("Done", f"Video đã lưu: {output_path}")

# =======================
# GUI Tkinter
# =======================
root = tk.Tk()
root.title("Video Crop Tool")
root.geometry("300x150")

btn_select = tk.Button(root, text="Chọn Video", command=select_video)
btn_select.pack(pady=10)

btn_crop = tk.Button(root, text="Crop & Save", command=crop_and_save)
btn_crop.pack(pady=10)

root.mainloop()
