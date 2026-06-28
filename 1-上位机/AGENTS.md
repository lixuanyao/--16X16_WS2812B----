# AGENTS.md - WS2812B LED矩阵控制器

## 项目概览
单文件 Python GUI 应用，通过串口控制 STM32 驱动的 16x16 WS2812B LED 矩阵。

## 运行命令
```bash
pip install pyserial          # 唯一依赖
python ws2812b_control.py     # 或双击 run.bat
```

## 环境陷阱
- 本机有**两个 Python**：`C:\Users\lixuanyao\scoop\apps\python313\current\python.exe`（scoop, `run.bat` 使用）和 `C:\Users\lixuanyao\AppData\Local\Programs\Python\Python314\python.exe`（VSCode 可能默认选中）
- 需要确保**当前 Python 解释器**已安装 pyserial，否则 `import serial` 报错
- 如果 VSCode 报 `ModuleNotFoundError: No module named 'serial'`，按 `Ctrl+Shift+P` → `Python: Select Interpreter` 切换到 scoop 的 3.13

## 架构
- `ws2812b_control.py`：唯一源文件，包含 `WS2812BController` 类（tkinter GUI + 串口逻辑）
- 无虚拟环境、无测试、无 CI、无 git
- 串口协议：1 字节同步头 `0xAA` + 768 字节 RGB（256 LED × 3），行优先排列
- 串口数据预览区：底部暗色终端风格面板，TX 青色 / RX 蓝色 / INFO 绿色
- 接收线程 `rx_loop()` 用 `root.after(0, ...)` 安全更新 GUI

## 注意事项
- 是 GUI 程序，`mainloop()` 不会自行退出，测试运行时需设 timeout
- 串口功能依赖实际硬件或虚拟串口，无串口时仅 GUI 可操作但发送会弹警告
- `send_data()` 中亮度是**等比缩放** (`r * brightness // 255`)，不是截断
