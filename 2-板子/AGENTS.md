# AGENTS.md

## Project

16x16 full-color WS2812B LED matrix firmware for STM32F103C8 (Blue Pill).

## Toolchain

- **IDE**: Keil µVision 5 (ARM-ADS, ARM Compiler — NOT AC6/Clang)
- **DFP pack**: Keil.STM32F1xx_DFP.2.2.0
- **C standard**: C99 (`uC99=1`)
- **MCU**: Cortex-M3, 8 MHz HSE → 72 MHz SYSCLK, 64 KB flash (0x08000000), 20 KB SRAM (0x20000000)
- **Debugger**: ST-Link (UL2CM3.DLL)
- **Output**: `Objects/main.axf` (hex generation is OFF — enable `<CreateHexFile>1</CreateHexFile>` in .uvprojx if needed)

## Build

There is no CLI build. Open `main.uvprojx` in Keil µVision and build with F7 / the Build button. No Makefile, CMake, or CLI toolchain is present.

## Key files

- `main.uvprojx` — project definition (targets, groups, compiler/linker options)
- `main.uvoptx` — per-user debug/session options (not portable, safe to delete)
- `main.uvguix.lixuanyao` — per-user GUI layout (safe to delete)
- `DebugConfig/` — MCU debug register config
- `Objects/` — build artifacts (.axf, .o, .d, .crf, etc.)
- `Listings/` — map and listing files

## Source layout

- `ws2812b.c` / `ws2812b.h` — WS2812B driver (TIM2_CH2 + DMA1_Channel7 PWM on PA1)
- `main.c` — application entry point
- `led_layout.txt` — LED matrix physical wiring diagram

No include paths or preprocessor defines are configured yet. Add `ws2812b.c` to Source Group 1 in Keil, and set `STM32F10X_MD` define in C/C++ options. Only the DFP's `stm32f10x.h` is needed — no SPL or HAL library files required.

## WS2812B driver notes

- **Pin**: PA1 (TIM2_CH2, AF_PP). Wiring: PA1 → DIN of the first WS2812B.
- **PWM timing**: 72 MHz / 90 = 800 kHz. LO=30 counts (~420 ns), HI=60 counts (~830 ns).
- **DMA**: DMA1_Channel7, triggered by TIM2 capture/compare 2 event (CC2DE, NOT update event).
- **No output inversion**: CC2P is cleared. If your LED strip needs inverted signal, set CC2P.
- **Color order**: GRB (confirmed by hardware testing). `ws2812b_pixel(x, y, r, g, b)` handles conversion automatically.
- **Serpentine mapping**: 16x16 grid. Even columns (0,2,4...) go top→bottom, odd columns (1,3,5...) go bottom→top. Mapping is in `xy_map[][]` in ws2812b.c.
- **RAM budget** (~7 KB of 20 KB): DMA buffer = 256×24+2 = 6146 bytes, frame buffer = 768 bytes.
- **Frame buffer API**: `ws2812b_frame[x][y][3]` (R,G,B). Use `ws2812b_pixel()` to write, `ws2812b_flush()` to send via DMA.
- **Blocking**: `ws2812b_flush()` blocks until previous DMA completes, then starts new transfer.
- Uses direct register access only — no SPL/HAL dependency. Just `stm32f10x.h` from the DFP pack.
- Based on [DiMoonElec/ws2812b_stm32f103c8_demo](https://github.com/DiMoonElec/ws2812b_stm32f103c8_demo).

## Public API (ws2812b.h)

| Function | Description |
|----------|-------------|
| `ws2812b_init()` | Init GPIO, TIM2, DMA |
| `ws2812b_pixel(x, y, r, g, b)` | Set pixel in frame buffer (no send) |
| `ws2812b_write(data[256][3])` | Write full frame by physical position + flush |
| `ws2812b_flush()` | Send frame buffer via DMA (blocks until ready) |
| `ws2812b_ready()` | 1=idle, 0=DMA busy |
| `ws2812b_clear()` | Zero frame buffer |

Internal helpers in .c: `ws2812b_set(pixn, r, g, b)`. Public functions are thin wrappers over these.

### `ws2812b_write` data mapping

`data[i]` 按行优先排列（不是按灯带序号）：

```
data[0]  = (列0,行0) = 灯1     data[1]  = (列1,行0) = 灯32
data[2]  = (列2,行0) = 灯33    data[15] = (列15,行0)= 灯256
data[16] = (列0,行1) = 灯2     data[17] = (列1,行1) = 灯31
data[18] = (列2,行1) = 灯34    ...
...
data[row*16 + col] = 物理位置(列col, 行row)的灯
```

蛇形映射自动处理：偶数列从上到下，奇数列从下到上。

## Usage example

```c
#include "stm32f10x.h"
#include "ws2812b.h"

/* data[col*16+row] = 物理位置(列col, 行row)的灯 {r,g,b} */
static const uint8_t led_data[256][3] = {
    {255, 0, 0},   /* 灯1 红 */
    {0, 255, 0},   /* 灯2 绿 */
    /* ... */
};

int main(void)
{
    SystemInit();
    ws2812b_init();
    ws2812b_write(led_data);  // map serpentine + DMA send
    while (1);
}
```

## Keil project config (already set in .uvprojx)

- **Define**: `STM32F10X_MD`
- **Include**: `C:\Keil_v5\ARM\PACK\Keil\STM32F1xx_DFP\2.2.0\Device\Include` + `C:\Keil_v5\ARM\PACK\ARM\CMSIS\5.0.1\CMSIS\Include`
- **Source files**: main.c, ws2812b.c, system_stm32f10x.c, startup_stm32f10x_md.s

## UART Protocol (for host communication)

### Hardware
- **USART1**: PA9 (TX), PA10 (RX)
- **Baud rate**: 115200, 8N1
- **Logic level**: 3.3V (direct connection to STM32F103)

### Protocol
1. **Sync byte**: `0xAA` (decimal 170)
2. **Data**: 768 bytes (256 LEDs × 3 bytes per LED)
3. **Total frame**: 1 sync byte + 768 data bytes = 769 bytes

### Data format
- **Order**: Row-major (same as `ws2812b_write()` parameter)
- **Per LED**: 3 bytes {R, G, B} (0-255 each)
- **Index mapping**: `data[row*16 + col]` = LED at physical position (col, row)

### Example frame
```
[0xAA] [R0,0] [G0,0] [B0,0] [R1,0] [G1,0] [B1,0] ... [R15,15] [G15,15] [B15,15]
```

### Host implementation notes
1. Send sync byte `0xAA` to start a new frame
2. Send 768 bytes of RGB data in row-major order
3. Wait for next frame (no explicit acknowledgment)
4. If host sends data faster than MCU can process, excess frames are dropped
5. Timeout: 1 second; if frame not complete within timeout, MCU resets receiver

### Python example (pyserial)
```python
import serial
import time

# LED data: 256 LEDs, each with R, G, B values
led_data = [0] * 768  # Initialize all LEDs to off

# Example: Set LED at (0,0) to red
led_data[0] = 255  # R
led_data[1] = 0    # G
led_data[2] = 0    # B

# Send to MCU
with serial.Serial('COM3', 115200, timeout=1) as ser:
    ser.write(bytes([0xAA]))  # Sync byte
    ser.write(bytes(led_data))  # LED data
```
