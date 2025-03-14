# 导入必要的库
import webbrowser  # 用于打开浏览器链接
import cv2  # OpenCV库，用于图像处理
import mss  # 用于屏幕截图
import numpy as np  # 用于数组操作
import pyautogui  # 用于获取鼠标位置和屏幕信息
from flask import Flask, Response, jsonify, render_template  # Flask框架，用于创建Web服务器
import time  # 时间模块，用于控制时间间隔
import socket  # 用于获取本机IP地址
import threading  # 用于多线程操作
import tkinter as tk  # Tkinter库，用于创建图形用户界面
from tkinter import ttk, messagebox  # Tkinter的扩展模块，用于创建更复杂的UI组件和消息框

# 创建Flask应用实例
app = Flask(__name__)

# 定义全局变量
REFRESH_INTERVAL = 0.25  # 视频帧刷新间隔（秒）
previous_frame = None  # 上一帧图像
last_sent_time = time.time()  # 上一次发送帧的时间
bgr_to_gray = cv2.COLOR_BGR2GRAY  # BGR到灰度的转换标志

# 全局变量用于控制服务状态和投屏人数
service_running = False  # 服务是否运行
server_ip = socket.gethostbyname(socket.gethostname())  # 获取本机IP地址

# 存储客户端连接数
clients = set()

# 定义生成视频帧的函数
def generate_frames():
    global previous_frame, last_sent_time  # 使用全局变量
    previous_frame = None
    last_sent_time = time.time()

    with mss.mss() as sct:  # 使用mss库创建屏幕截图对象
        monitor = sct.monitors[1]  # 获取第二个显示器（主显示器）
        screen_width = monitor["width"]  # 获取屏幕宽度
        screen_height = monitor["height"]  # 获取屏幕高度

        while True:  # 无限循环生成视频帧
            if not service_running:  # 如果服务未运行，暂停生成帧
                time.sleep(1)
                continue
            sct_img = sct.grab(monitor)  # 截取屏幕图像
            current_frame = cv2.cvtColor(np.array(sct_img), cv2.COLOR_BGRA2BGR)  # 将截图转换为BGR格式

            current_time = time.time()  # 当前时间
            force_send = current_time - last_sent_time >= REFRESH_INTERVAL  # 是否强制发送帧

            if previous_frame is None:  # 如果是第一帧
                previous_frame = current_frame  # 保存当前帧
                last_sent_time = current_time  # 更新发送时间

                # 将帧编码为JPEG格式并发送
                _, buffer = cv2.imencode('.jpg', current_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                continue

            # 将当前帧和上一帧转换为灰度图像
            prev_gray = cv2.cvtColor(previous_frame, bgr_to_gray)
            curr_gray = cv2.cvtColor(current_frame, bgr_to_gray)
            diff = cv2.absdiff(prev_gray, curr_gray)  # 计算两帧的差异

            # 对差异图像进行阈值处理
            _, threshold_diff = cv2.threshold(diff, thresh=25, maxval=255, type=cv2.THRESH_BINARY)

            # 计算变化强度
            change_intensity = cv2.countNonZero(threshold_diff)

            # 如果强制发送或变化强度超过阈值
            if force_send or change_intensity > 500:
                previous_frame = current_frame  # 更新上一帧
                last_sent_time = current_time  # 更新发送时间

                # 根据变化强度调整图像质量
                quality = 70
                if change_intensity > 150000:
                    quality = 10
                elif change_intensity > 90000:
                    quality = 50

                # 编码并发送帧
                _, buffer = cv2.imencode('.jpg', current_frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality, cv2.IMWRITE_JPEG_PROGRESSIVE, 1])
                frame_data = buffer.tobytes()
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
            else:
                # 如果不需要发送帧，计算剩余等待时间
                sleep_time = REFRESH_INTERVAL - (current_time - last_sent_time)
                if sleep_time > 0:
                    time.sleep(sleep_time * 0.95)  # 稍作延迟

# 定义视频流路由
@app.route('/video_feed')
def video_feed():
    response = Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
    return response

# 定义获取鼠标位置的路由
@app.route('/mouse')
def get_mouse_position():
    if not service_running:  # 如果服务未运行，返回空列表
        return []
    x, y = pyautogui.position()  # 获取当前鼠标位置
    screen_width, screen_height = pyautogui.size()  # 获取屏幕尺寸
    return jsonify({
        'x': x,
        'y': y,
        'screen_width': screen_width,
        'screen_height': screen_height
    })

# 定义主页路由，返回HTML页面
@app.route('/')
def index():
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <title>PixelStreamer</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
        /* 页面样式 */
        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background-color: #f5f5f5;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
        }

        #video-container {
            position: relative;
            width: 100%;
            max-width: 1200px;
            aspect-ratio: 16 / 9;
            overflow: hidden;
            border: 2px solid #ccc;
            border-radius: 10px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        }

        #video-container img {
            width: 100%;
            height: 100%;
        }

        #mouse-pointer {
            position: absolute;
            width: 10px;
            height: 10px;
            background: red;
            border-radius: 50%;
            display: none;
            pointer-events: none;
            transition: left 0.15s linear, top 0.15s linear, width 0.15s ease, height 0.15s ease;
        }

        .controls {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0, 0, 0, 0.8);
            padding: 10px;
            border-radius: 20px;
            display: flex;
            justify-content: center;
            gap: 10px;
        }

        .control-btn {
            background: #4CAF50;
            color: white;
            border: none;
            padding: 10px 20px;
            text-align: center;
            text-decoration: none;
            display: inline-block;
            font-size: 16px;
            cursor: pointer;
            border-radius: 5px;
            transition: background-color 0.3s ease;
        }

        .control-btn:hover {
            background: #45a049;
        }

        .control-btn:active {
            transform: scale(0.98);
        }
    </style>
</head>
<body>
    <div id="video-container">
        <img src="/video_feed" alt="视频流">
        <div id="mouse-pointer"></div>
    </div>
    <div class="controls">
        <button class="control-btn" id="fullscreen-btn">全屏</button>
        <button class="control-btn" id="screenshot-btn">截图</button>
        <button class="control-btn" id="refresh-btn">刷新</button>
        <button class="control-btn" id="toggle-mouse-btn">显示鼠标</button>
    </div>
    <script>
        // 页面加载完成后执行的脚本
        document.addEventListener('DOMContentLoaded', function () {
            const videoImg = document.querySelector('img');  // 视频流图片
            const mousePointer = document.getElementById('mouse-pointer');  // 鼠标指针
            const fullscreenBtn = document.getElementById('fullscreen-btn');  // 全屏按钮
            const screenshotBtn = document.getElementById('screenshot-btn');  // 截图按钮
            const refreshBtn = document.getElementById('refresh-btn');  // 刷新按钮
            const toggleMouseBtn = document.getElementById('toggle-mouse-btn');  // 切换鼠标显示按钮

            let lastX = 0, lastY = 0;  // 上一次的鼠标位置
            let velocityX = 0, velocityY = 0;  // 鼠标移动速度
            const smoothingFactor = 0.6;  // 平滑因子，用于调整预测的灵敏度
            let isMouseVisible = false;  // 鼠标是否可见
            let isFetchingMouse = false;  // 是否正在获取鼠标位置
            let mouseInterval;  // 定时器

            // 更新鼠标位置的函数
            function updateMousePosition() {
                fetch('/mouse')  // 请求后端获取鼠标位置
                    .then(response => response.json())  // 解析响应为JSON
                    .then(data => {
                        const videoWidth = videoImg.clientWidth;  // 视频容器宽度
                        const videoHeight = videoImg.clientHeight;  // 视频容器高度
                        const scaleX = videoWidth / data.screen_width;  // 计算缩放比例
                        const scaleY = videoHeight / data.screen_height;

                        const x = data.x * scaleX;  // 转换鼠标X坐标
                        const y = data.y * scaleY;  // 转换鼠标Y坐标

                        // 计算速度
                        velocityX = (x - lastX) * smoothingFactor;
                        velocityY = (y - lastY) * smoothingFactor;

                        // 预测下一个位置
                        const predictedX = x + velocityX;
                        const predictedY = y + velocityY;

                        // 根据速度动态调整鼠标指针大小
                        const speed = Math.sqrt(velocityX * velocityX + velocityY * velocityY);  // 计算速度大小
                        const baseSize = 10;  // 基础大小
                        const maxSpeed = 100;  // 最大速度阈值
                        const maxSize = 30;  // 最大大小
                        const size = Math.min(baseSize + speed * (maxSize - baseSize) / maxSpeed, maxSize);

                        // 更新鼠标指针位置和大小
                        if (isMouseVisible) {
                            mousePointer.style.left = predictedX + 'px';
                            mousePointer.style.top = predictedY + 'px';
                            mousePointer.style.width = size + 'px';
                            mousePointer.style.height = size + 'px';
                            mousePointer.style.display = 'block';
                        }

                        // 更新上一次的位置
                        lastX = x;
                        lastY = y;
                    })
                    .catch(() => {
                        if (isMouseVisible) {
                            mousePointer.style.display = 'none';  // 如果获取失败，隐藏鼠标指针
                        }
                    });
            }

            // 开始获取鼠标位置
            function startMouseFetching() {
                if (!isFetchingMouse) {
                    mouseInterval = setInterval(updateMousePosition, 15);  // 每15ms更新一次鼠标位置
                    isFetchingMouse = true;
                }
            }

            // 停止获取鼠标位置
            function stopMouseFetching() {
                if (isFetchingMouse) {
                    clearInterval(mouseInterval);
                    isFetchingMouse = false;
                    mousePointer.style.display = 'none';  // 停止后隐藏鼠标指针
                }
            }

            // 全屏功能
            fullscreenBtn.addEventListener('click', function () {
                const videoContainer = document.getElementById('video-container');
                if (videoContainer.requestFullscreen) {
                    videoContainer.requestFullscreen();  // 调用全屏API
                } else if (videoContainer.mozRequestFullScreen) {
                    videoContainer.mozRequestFullScreen();
                } else if (videoContainer.webkitRequestFullscreen) {
                    videoContainer.webkitRequestFullscreen();
                } else if (videoContainer.msRequestFullscreen) {
                    videoContainer.msRequestFullscreen();
                }
            });

            // 截图功能
            screenshotBtn.addEventListener('click', function () {
                const video = document.querySelector('img');  // 获取视频流图片
                const canvas = document.createElement('canvas');  // 创建画布
                canvas.width = video.clientWidth;  // 设置画布大小
                canvas.height = video.clientHeight;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);  // 将视频流绘制到画布上
                canvas.toBlob(function (blob) {  // 将画布转换为图片
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'screenshot.png';  // 设置下载文件名
                    a.click();
                    URL.revokeObjectURL(url);  // 释放对象URL
                }, 'image/png');
            });

            // 刷新功能
            refreshBtn.addEventListener('click', function () {
                location.reload();  // 刷新页面
            });

            // 切换鼠标显示状态
            toggleMouseBtn.addEventListener('click', function () {
                isMouseVisible = !isMouseVisible;  // 切换显示状态
                if (isMouseVisible) {
                    toggleMouseBtn.textContent = '隐藏鼠标';  // 更新按钮文本
                    startMouseFetching();  // 开始获取鼠标位置
                } else {
                    toggleMouseBtn.textContent = '显示鼠标';
                    stopMouseFetching();  // 停止获取鼠标位置
                }
            });

            // 初始启动鼠标获取
            startMouseFetching();
        });
    </script>
</body>
</html>
    '''


def flask_app_runner():
    app.run(host='0.0.0.0', port=80, debug=False)


COLORS = {
    "primary": "#2c3e50",
    "secondary": "#3498db",
    "success": "#27ae60",
    "danger": "#e74c3c",
    "background": "#f5f6fa",
    "text": "#2c3e50"
}

FONTS = {
    "title": ("Segoe UI", 14, "bold"),
    "body": ("Segoe UI", 11),
    "small": ("Segoe UI", 9)
}


# 扩展Canvas方法用于绘制圆角矩形
def _create_round_rect(self, x1, y1, x2, y2, radius=20, **kwargs):
    points = [x1 + radius, y1,
              x2 - radius, y1,
              x2, y1,
              x2, y1 + radius,
              x2, y2 - radius,
              x2 - radius, y2,
              x1 + radius, y2,
              x1, y2,
              x1, y2 - radius,
              x1, y1 + radius,
              x1 + radius, y1]
    return self.create_polygon(points, **kwargs, smooth=True)


tk.Canvas.create_round_rect = _create_round_rect


def create_animated_button(parent, text, command):
    """创建带动画效果的圆角按钮"""
    canvas = tk.Canvas(parent, width=120, height=40,
                       bd=0, highlightthickness=0, relief="flat")

    # 绘制背景和文本
    canvas.bg_id = canvas.create_round_rect(0, 0, 120, 40, 20,
                                            fill=COLORS["secondary"], outline="")
    canvas.text_id = canvas.create_text(60, 20, text=text,
                                        font=FONTS["body"], fill="white")

    # 动画效果
    def on_enter(e):
        canvas.itemconfig(canvas.bg_id, fill=COLORS["success"])

    def on_leave(e):
        canvas.itemconfig(canvas.bg_id, fill=COLORS["secondary"])

    canvas.bind("<Enter>", on_enter)
    canvas.bind("<Leave>", on_leave)
    canvas.bind("<Button-1>", lambda e: command())

    return canvas


def toggle_service(button, status_label, status_icon):
    global service_running
    service_running = not service_running

    # 更新按钮文字
    new_text = "停止服务" if service_running else "启动服务"
    button.itemconfig(button.text_id, text=new_text)

    # 更新状态指示灯
    new_color = COLORS["success"] if service_running else COLORS["danger"]
    status_icon.itemconfig(status_icon.circle_id, fill=new_color)

    # 更新状态标签
    status_text = "运行中" if service_running else "已停止"
    status_label.config(text=status_text, fg=new_color)

    # 显示状态提示
    message = f"服务已启动，IP地址：{server_ip}" if service_running else "服务已停止"
    messagebox.showinfo("服务状态", message)


def create_gui():
    root = tk.Tk()
    root.title("PixelStreamer")
    root.configure(bg=COLORS["background"])

    # 窗口居中
    window_width = 480
    window_height = 300
    x_offset = (root.winfo_screenwidth() - window_width) // 2
    y_offset = (root.winfo_screenheight() - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x_offset}+{y_offset}")
    root.resizable(False, False)  # 禁止调整窗口尺寸
    # 主容器
    main_frame = tk.Frame(root, bg=COLORS["background"])
    main_frame.pack(expand=True, fill="both", padx=20, pady=20)

    # 状态显示面板
    status_frame = tk.Frame(main_frame, bg=COLORS["background"])
    status_frame.pack(pady=15)

    # 状态指示灯
    status_icon = tk.Canvas(status_frame, width=24, height=24,
                            bg=COLORS["background"], highlightthickness=0)
    status_icon.circle_id = status_icon.create_oval(2, 2, 22, 22,
                                                    fill=COLORS["danger"], outline="")
    status_icon.pack(side="left")

    # 状态标签
    status_label = tk.Label(status_frame, text="服务未运行",
                            font=FONTS["body"], bg=COLORS["background"],
                            fg=COLORS["text"])
    status_label.pack(side="left", padx=10)

    # IP地址显示
    ip_label = tk.Label(main_frame, text=f"服务IP: {server_ip}",
                        font=FONTS["body"], bg=COLORS["background"],
                        fg=COLORS["text"])
    ip_label.pack(pady=10)

    # 控制按钮
    button = create_animated_button(
        main_frame,
        "启动服务",
        command=lambda: toggle_service(button, status_label, status_icon)
    )
    button.pack(pady=20)

    # GitHub链接
    github_link = tk.Label(root, text="GitHub仓库", font=FONTS["small"],
                           fg=COLORS["secondary"], cursor="hand2",
                           bg=COLORS["background"])
    github_link.pack(side="bottom", pady=5)
    github_link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/MGJ520/PixelStreamer"))

    root.mainloop()


if __name__ == '__main__':
    # 创建并启动Flask应用线程
    flask_thread = threading.Thread(target=flask_app_runner, daemon=True)
    flask_thread.start()
    # 创建并运行GUI
    create_gui()
