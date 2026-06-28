/**
 * @file    ws2812b.h
 * @brief   WS2812B 16x16 全彩 LED 矩阵驱动（TIM2 + DMA，PA1 输出）
 *
 * 硬件连接：PA1 → DIN
 * 灯珠排列：16x16 蛇形走线
 *   - 偶数列 (0,2,4...): y=0 顶部, y=15 底部
 *   - 奇数列 (1,3,5...): y=0 底部, y=15 顶部
 *
 * 用法：
 *   1. ws2812b_init();
 *   2. ws2812b_pixel(x, y, r, g, b);  // 写缓冲区
 *   3. ws2812b_flush();                // DMA 发送
 *   4. while(!ws2812b_ready());        // 等待完成
 *   5. 回到第 2 步
 *
 * 基于 DiMoonElec/ws2812b_stm32f103c8_demo 移植
 */

#ifndef __WS2812B_H__
#define __WS2812B_H__

#include <stdint.h>

#define WS2812B_NUM_LEDS   256
#define WS2812B_COLS       16
#define WS2812B_ROWS       16

/**
 * @brief  初始化驱动（GPIO、TIM2、DMA）
 */
void ws2812b_init(void);

/**
 * @brief  清空 DMA 缓冲区（全灭）
 */
void ws2812b_clear(void);

/**
 * @brief  设置单颗灯颜色（写 DMA 缓冲区，不发送）
 * @param  x  列 0~15
 * @param  y  行 0~15
 * @param  r  红 0~255
 * @param  g  绿 0~255
 * @param  b  蓝 0~255
 */
void ws2812b_pixel(uint8_t x, uint8_t y, uint8_t r, uint8_t g, uint8_t b);

/**
 * @brief  按物理位置写入整帧数据并发送
 * @param  data  data[256][3]，按行优先排列：
 *               data[row*16+col] 对应物理位置 (列col, 行row)
 *               蛇形映射自动处理：偶数列从上到下，奇数列从下到上
 */
void ws2812b_write(const uint8_t data[][3]);

/**
 * @brief  刷新：将缓冲区数据通过 DMA 发送
 * @note   如果上一次 DMA 未完成则静默跳过，用 ws2812b_ready() 查询
 */
void ws2812b_flush(void);

/**
 * @brief  查询是否空闲可刷新
 * @retval 1=空闲, 0=发送中
 */
int  ws2812b_ready(void);

#endif
