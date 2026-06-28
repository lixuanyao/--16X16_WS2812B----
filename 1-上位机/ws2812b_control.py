#!/usr/bin/env python3
"""
WS2812B 16x16 LED矩阵上位机控制软件
通过串口控制STM32驱动的WS2812B矩阵
"""

import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
import serial
import serial.tools.list_ports
import threading
import time

class WS2812BController:
    def __init__(self, root):
        self.root = root
        self.root.title("WS2812B 16x16 LED矩阵控制器")
        self.root.resizable(False, False)
        
        # LED矩阵参数
        self.COLS = 16
        self.ROWS = 16
        self.LED_SIZE = 25  # 每个LED方块像素大小
        
        # 串口相关
        self.serial_port = None
        self.is_connected = False
        self.rx_running = False
        self.rx_thread = None
        
        # LED数据缓冲区 [row][col] = (r, g, b)
        self.led_data = [[(0, 0, 0) for _ in range(self.COLS)] for _ in range(self.ROWS)]
        
        # 当前画笔颜色
        self.current_color = (255, 0, 0)
        
        # 绘制模式
        self.draw_mode = False
        
        # 创建界面
        self.create_widgets()
        
        # 刷新串口列表
        self.refresh_ports()
    
    def create_widgets(self):
        """创建所有GUI组件"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # === 左侧：LED矩阵显示 ===
        matrix_frame = ttk.LabelFrame(main_frame, text="LED矩阵 (16x16)", padding="5")
        matrix_frame.grid(row=0, column=0, padx=(0, 10), sticky=(tk.N, tk.S))
        
        # 创建Canvas显示LED矩阵
        canvas_width = self.COLS * self.LED_SIZE + 1
        canvas_height = self.ROWS * self.LED_SIZE + 1
        self.canvas = tk.Canvas(matrix_frame, width=canvas_width, height=canvas_height, bg="black")
        self.canvas.grid(row=0, column=0)
        
        # 绘制LED网格
        self.led_rects = [[None for _ in range(self.COLS)] for _ in range(self.ROWS)]
        for row in range(self.ROWS):
            for col in range(self.COLS):
                x1 = col * self.LED_SIZE + 1
                y1 = row * self.LED_SIZE + 1
                x2 = x1 + self.LED_SIZE - 2
                y2 = y1 + self.LED_SIZE - 2
                rect = self.canvas.create_rectangle(x1, y1, x2, y2, fill="gray", outline="darkgray")
                self.led_rects[row][col] = rect
        
        # 绑定鼠标事件
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        
        # === 右侧：控制面板 ===
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 串口设置
        serial_frame = ttk.LabelFrame(control_frame, text="串口设置", padding="5")
        serial_frame.grid(row=0, column=0, pady=(0, 10), sticky=(tk.W, tk.E))
        
        ttk.Label(serial_frame, text="端口:").grid(row=0, column=0, sticky=tk.W)
        self.port_combo = ttk.Combobox(serial_frame, width=15, state="readonly")
        self.port_combo.grid(row=0, column=1, padx=(5, 0))
        
        ttk.Label(serial_frame, text="波特率:").grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.baud_combo = ttk.Combobox(serial_frame, width=15, state="readonly", 
                                        values=["9600", "19200", "38400", "57600", "115200"])
        self.baud_combo.set("115200")
        self.baud_combo.grid(row=1, column=1, padx=(5, 0), pady=(5, 0))
        
        btn_frame = ttk.Frame(serial_frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0))
        
        self.refresh_btn = ttk.Button(btn_frame, text="刷新", command=self.refresh_ports, width=6)
        self.refresh_btn.grid(row=0, column=0, padx=(0, 5))
        
        self.connect_btn = ttk.Button(btn_frame, text="连接", command=self.toggle_connection, width=6)
        self.connect_btn.grid(row=0, column=1)
        
        self.status_label = ttk.Label(serial_frame, text="● 未连接", foreground="red")
        self.status_label.grid(row=3, column=0, columnspan=2, pady=(5, 0))
        
        # 颜色选择
        color_frame = ttk.LabelFrame(control_frame, text="画笔颜色", padding="5")
        color_frame.grid(row=1, column=0, pady=(0, 10), sticky=(tk.W, tk.E))
        
        self.color_preview = tk.Canvas(color_frame, width=60, height=30, bg="red", relief="solid", bd=1)
        self.color_preview.grid(row=0, column=0, padx=(0, 10))
        
        self.color_btn = ttk.Button(color_frame, text="选择颜色", command=self.choose_color)
        self.color_btn.grid(row=0, column=1)
        
        # 快捷颜色
        quick_color_frame = ttk.Frame(color_frame)
        quick_color_frame.grid(row=1, column=0, columnspan=2, pady=(10, 0))
        
        quick_colors = [
            ("红", (255, 0, 0)), ("绿", (0, 255, 0)), ("蓝", (0, 0, 255)),
            ("黄", (255, 255, 0)), ("青", (0, 255, 255)), ("紫", (255, 0, 255)),
            ("白", (255, 255, 255)), ("灭", (0, 0, 0))
        ]
        
        for i, (name, color) in enumerate(quick_colors):
            btn = ttk.Button(quick_color_frame, text=name, width=4,
                           command=lambda c=color: self.set_quick_color(c))
            btn.grid(row=i // 4, column=i % 4, padx=2, pady=2)
        
        # 亮度控制
        brightness_frame = ttk.LabelFrame(control_frame, text="亮度限制", padding="5")
        brightness_frame.grid(row=2, column=0, pady=(0, 10), sticky=(tk.W, tk.E))
        
        self.brightness_var = tk.IntVar(value=50)
        self.brightness_scale = ttk.Scale(brightness_frame, from_=1, to=255, 
                                           variable=self.brightness_var, orient=tk.HORIZONTAL)
        self.brightness_scale.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        self.brightness_label = ttk.Label(brightness_frame, text="50")
        self.brightness_label.grid(row=0, column=1, padx=(5, 0))
        
        self.brightness_var.trace_add("write", self.update_brightness_label)
        
        # 操作按钮
        action_frame = ttk.LabelFrame(control_frame, text="操作", padding="5")
        action_frame.grid(row=3, column=0, pady=(0, 10), sticky=(tk.W, tk.E))
        
        self.send_btn = ttk.Button(action_frame, text="发送到LED", command=self.send_data, state="disabled")
        self.send_btn.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        
        self.clear_btn = ttk.Button(action_frame, text="清屏", command=self.clear_matrix)
        self.clear_btn.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        self.fill_btn = ttk.Button(action_frame, text="填充颜色", command=self.fill_matrix)
        self.fill_btn.grid(row=1, column=1, sticky=(tk.W, tk.E))
        
        # 预设图案
        preset_frame = ttk.LabelFrame(control_frame, text="预设图案", padding="5")
        preset_frame.grid(row=4, column=0, pady=(0, 10), sticky=(tk.W, tk.E))
        
        presets = ["渐变", "棋盘", "边框", "十字", "笑脸"]
        for i, name in enumerate(presets):
            btn = ttk.Button(preset_frame, text=name, width=6,
                           command=lambda n=name: self.load_preset(n))
            btn.grid(row=i // 3, column=i % 3, padx=2, pady=2)
        
        # 坐标显示
        coord_frame = ttk.Frame(control_frame)
        coord_frame.grid(row=5, column=0, sticky=(tk.W, tk.E))
        
        self.coord_label = ttk.Label(coord_frame, text="坐标: --")
        self.coord_label.grid(row=0, column=0)
        
        # === 底部：串口数据预览 ===
        monitor_frame = ttk.LabelFrame(self.root, text="串口数据预览", padding="5")
        monitor_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.monitor_text = tk.Text(monitor_frame, width=90, height=8, bg="#1e1e1e", fg="#d4d4d4",
                                     insertbackground="white", state="disabled", wrap=tk.WORD)
        self.monitor_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        monitor_scroll = ttk.Scrollbar(monitor_frame, orient=tk.VERTICAL, command=self.monitor_text.yview)
        monitor_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.monitor_text.config(yscrollcommand=monitor_scroll.set)
        
        # 配置颜色标签
        self.monitor_text.tag_config("tx", foreground="#4ec9b0")  # 发送-青色
        self.monitor_text.tag_config("rx", foreground="#569cd6")  # 接收-蓝色
        self.monitor_text.tag_config("info", foreground="#6a9955")  # 信息-绿色
    
    def refresh_ports(self):
        """刷新可用串口列表"""
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo["values"] = ports
        if ports:
            self.port_combo.set(ports[0])
    
    def toggle_connection(self):
        """连接/断开串口"""
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        """连接串口"""
        port = self.port_combo.get()
        baud = int(self.baud_combo.get())
        
        if not port:
            messagebox.showwarning("警告", "请选择串口!")
            return
        
        try:
            self.serial_port = serial.Serial(port, baud, timeout=0.1)
            self.is_connected = True
            self.connect_btn.config(text="断开")
            self.status_label.config(text="● 已连接", foreground="green")
            self.send_btn.config(state="normal")
            self.log_monitor(f"连接 {port} @ {baud}bps", "info")
            self.start_rx_thread()
        except Exception as e:
            messagebox.showerror("错误", f"连接失败: {e}")
    
    def disconnect(self):
        """断开串口"""
        self.stop_rx_thread()
        if self.serial_port:
            self.serial_port.close()
            self.serial_port = None
        self.is_connected = False
        self.connect_btn.config(text="连接")
        self.status_label.config(text="● 未连接", foreground="red")
        self.send_btn.config(state="disabled")
        self.log_monitor("已断开", "info")
    
    def log_monitor(self, text, tag=None):
        """向串口预览区追加日志"""
        self.monitor_text.config(state="normal")
        self.monitor_text.insert(tk.END, text + "\n", tag)
        self.monitor_text.see(tk.END)
        self.monitor_text.config(state="disabled")
    
    def start_rx_thread(self):
        """启动接收线程"""
        self.rx_running = True
        self.rx_thread = threading.Thread(target=self.rx_loop, daemon=True)
        self.rx_thread.start()
    
    def stop_rx_thread(self):
        """停止接收线程"""
        self.rx_running = False
        if self.rx_thread and self.rx_thread.is_alive():
            self.rx_thread.join(timeout=0.5)
        self.rx_thread = None
    
    def rx_loop(self):
        """接收线程循环"""
        while self.rx_running:
            try:
                if self.serial_port and self.serial_port.is_open and self.serial_port.in_waiting:
                    raw = self.serial_port.read(self.serial_port.in_waiting)
                    if raw:
                        hex_str = raw.hex(' ').upper()
                        self.root.after(0, lambda h=hex_str: self.log_monitor(f"[RX] {h}", "rx"))
            except Exception:
                pass
            time.sleep(0.05)
    
    def choose_color(self):
        """打开颜色选择器"""
        color = colorchooser.askcolor(title="选择画笔颜色")
        if color[0]:
            r, g, b = int(color[0][0]), int(color[0][1]), int(color[0][2])
            self.current_color = (r, g, b)
            self.color_preview.config(bg=color[1])
    
    def set_quick_color(self, color):
        """设置快捷颜色"""
        self.current_color = color
        hex_color = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
        self.color_preview.config(bg=hex_color)
    
    def update_brightness_label(self, *args):
        """更新亮度标签"""
        self.brightness_label.config(text=str(self.brightness_var.get()))
    
    def on_canvas_click(self, event):
        """鼠标点击LED"""
        self.draw_mode = True
        self.draw_led(event)
    
    def on_canvas_drag(self, event):
        """鼠标拖动绘制"""
        if self.draw_mode:
            self.draw_led(event)
    
    def on_canvas_release(self, event):
        """鼠标释放"""
        self.draw_mode = False
    
    def draw_led(self, event):
        """绘制单个LED"""
        col = event.x // self.LED_SIZE
        row = event.y // self.LED_SIZE
        
        if 0 <= row < self.ROWS and 0 <= col < self.COLS:
            self.led_data[row][col] = self.current_color
            self.update_led_display(row, col)
            
            # 显示坐标
            self.coord_label.config(text=f"坐标: ({col}, {row})")
    
    def update_led_display(self, row, col):
        """更新单个LED显示"""
        r, g, b = self.led_data[row][col]
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        self.canvas.itemconfig(self.led_rects[row][col], fill=hex_color)
    
    def update_all_display(self):
        """更新整个矩阵显示"""
        for row in range(self.ROWS):
            for col in range(self.COLS):
                self.update_led_display(row, col)
    
    def clear_matrix(self):
        """清屏"""
        self.led_data = [[(0, 0, 0) for _ in range(self.COLS)] for _ in range(self.ROWS)]
        self.update_all_display()
    
    def fill_matrix(self):
        """填充当前颜色"""
        for row in range(self.ROWS):
            for col in range(self.COLS):
                self.led_data[row][col] = self.current_color
        self.update_all_display()
    
    def load_preset(self, name):
        """加载预设图案"""
        self.clear_matrix()
        
        if name == "渐变":
            for row in range(self.ROWS):
                for col in range(self.COLS):
                    r = int(col * 255 / 15)
                    g = int(row * 255 / 15)
                    b = 128
                    self.led_data[row][col] = (r, g, b)
        
        elif name == "棋盘":
            for row in range(self.ROWS):
                for col in range(self.COLS):
                    if (row + col) % 2 == 0:
                        self.led_data[row][col] = (255, 255, 255)
                    else:
                        self.led_data[row][col] = (0, 0, 0)
        
        elif name == "边框":
            for row in range(self.ROWS):
                for col in range(self.COLS):
                    if row == 0 or row == 15 or col == 0 or col == 15:
                        self.led_data[row][col] = (0, 255, 0)
        
        elif name == "十字":
            for row in range(self.ROWS):
                for col in range(self.COLS):
                    if row == 7 or row == 8 or col == 7 or col == 8:
                        self.led_data[row][col] = (255, 165, 0)
        
        elif name == "笑脸":
            # 简单笑脸图案
            eyes = [(5, 4), (5, 11)]
            mouth = [(10, 4), (10, 5), (10, 10), (10, 11),
                     (11, 5), (11, 6), (11, 7), (11, 8), (11, 9)]
            
            for r, c in eyes:
                self.led_data[r][c] = (255, 255, 0)
                self.led_data[r+1][c] = (255, 255, 0)
            
            for r, c in mouth:
                self.led_data[r][c] = (255, 255, 0)
        
        self.update_all_display()
    
    def send_data(self):
        """发送数据到STM32"""
        if not self.is_connected:
            messagebox.showwarning("警告", "请先连接串口!")
            return
        
        # 构建数据包
        brightness = self.brightness_var.get()
        data = bytearray()
        data.append(0xAA)  # 同步字节
        
        # 按行优先顺序添加RGB数据
        for row in range(self.ROWS):
            for col in range(self.COLS):
                r, g, b = self.led_data[row][col]
                # 限制亮度
                r = r * brightness // 255
                g = g * brightness // 255
                b = b * brightness // 255
                data.extend([r, g, b])
        
        # 发送数据
        try:
            self.serial_port.write(data)
            self.log_monitor(f"[TX] {data.hex(' ').upper()}", "tx")
            self.status_label.config(text="● 已发送", foreground="blue")
            # 1秒后恢复状态显示
            self.root.after(1000, lambda: self.status_label.config(
                text="● 已连接" if self.is_connected else "● 未连接",
                foreground="green" if self.is_connected else "red"))
        except Exception as e:
            messagebox.showerror("错误", f"发送失败: {e}")
            self.disconnect()
    
    def on_closing(self):
        """窗口关闭事件"""
        self.stop_rx_thread()
        self.disconnect()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = WS2812BController(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
