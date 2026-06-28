# WS2812B 16x16 LED矩阵控制器(纯AI写的代码)

PC端通过串口控制 STM32F103C8 驱动的 16×16 WS2812B 全彩 LED 矩阵。

## 目录结构

| 目录 | 说明 |
|------|------|
| `1-上位机/` | Python GUI 上位机（tkinter + pyserial） |
| `2-板子/`   | STM32 固件（Keil MDK, C99） |

## 快速开始

**上位机**
```bash
cd 1-上位机
pip install pyserial
python ws2812b_control.py
```

**固件**  
用 Keil µVision 5 打开 `2-板子/main.uvprojx`，编译烧录至 STM32F103C8。

## 串口协议

- 波特率 115200, 8N1
- 同步字节 `0xAA` + 768 字节 RGB 数据（行优先排列）
- 数据映射：`data[row*16 + col]` 对应物理位置 (col, row)

## 硬件

- MCU: STM32F103C8（Blue Pill）
- LED: WS2812B 16×16 矩阵
- 信号引脚: PA1（TIM2_CH2 PWM+DMA）
- 串口: PA9(TX) / PA10(RX)
