/**
 * @file    ws2812b.c
 * @brief   WS2812B 驱动实现 — TIM2 CH2 PWM + DMA1 CH7
 *
 * 原理：用 PWM 占空比编码 WS2812B 数据位
 *   - 0-bit: 占空比 1/3 (0.4µs 高, 0.85µs 低)
 *   - 1-bit: 占空比 2/3 (0.85µs 高, 0.4µs 低)
 *   - 帧尾两个零字节保证 >50µs 复位信号
 *
 * DMA 通道映射（STM32F103）：
 *   TIM2_CH2 (PA1) → DMA1_Channel7, 使用 CC2DE 触发
 *
 * 基于 DiMoonElec/ws2812b_stm32f103c8_demo 移植
 */

#include "stm32f10x.h"
#include "ws2812b.h"

/* ---- 时序参数（72MHz 定时器时钟） ---- */
#define TIMER_AAR   0x0059          /* ARR=89, PWM周期=90/72MHz=1.25µs */
#define VAL_0       (TIMER_AAR / 3) /* 0-bit: 占空比 1/3 ≈ 0.42µs 高 */
#define VAL_1       ((TIMER_AAR / 3) * 2) /* 1-bit: 占空比 2/3 ≈ 0.83µs 高 */

/* ---- 帧缓冲区：每颗灯24字节(GRB各8bit) + 尾部2字节复位 ---- */
#define DATA_LEN    ((WS2812B_NUM_LEDS * 24) + 2)

static uint8_t led_array[DATA_LEN];  /* DMA 源缓冲区 */
static int flag_rdy = 0;             /* 发送完成标志 */

static void bus_retcode(void);

/**
 * @brief  初始化 WS2812B 硬件
 *
 * 配置内容：
 *   - GPIO: PA1 推挽输出 10MHz
 *   - TIM2: CH2 PWM 模式1, ARR=89 (1.25µs), CC2DE 触发 DMA
 *   - DMA1 CH7: 8-bit 内存→16-bit 外设, 地址递增
 *   - NVIC: 使能 TIM2 和 DMA1_CH7 中断
 */
void ws2812b_init(void)
{
    flag_rdy = 0;

    /* 使能外设时钟 */
    RCC->APB2ENR |= RCC_APB2ENR_IOPAEN;  /* GPIOA */
    RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;  /* TIM2  */
    RCC->AHBENR  |= RCC_AHBENR_DMA1EN;   /* DMA1  */

    /* PA1: AF推挽 10MHz (CNF=10, MODE=11) */
    GPIOA->CRL &= ~(GPIO_CRL_CNF1);
    GPIOA->CRL |= GPIO_CRL_CNF1_1 | GPIO_CRL_MODE1_1 | GPIO_CRL_MODE1_0;

    /* TIM2 CH2 配置 */
    TIM2->CCER  |= TIM_CCER_CC2E;          /* 使能 CH2 输出 */
    TIM2->CCER  &= ~(TIM_CCER_CC2P);       /* 有效电平=高 */
    TIM2->CCMR1 &= ~(TIM_CCMR1_OC2M);     /* 清 OC2M */
    TIM2->CCMR1 |= TIM_CCMR1_OC2M_2;      /* 先设为强制无效 */
    TIM2->CCMR1 &= ~(TIM_CCMR1_OC2M_2);   /* 再清零 */
    TIM2->CCMR1 |= TIM_CCMR1_OC2M_2       /* PWM模式1: OC2M=110 */
                 |  TIM_CCMR1_OC2M_1
                 |  TIM_CCMR1_OC2PE;       /* 预装载使能 */
    TIM2->CR1   |= TIM_CR1_ARPE;           /* ARR 预装载 */
    TIM2->DIER  |= TIM_DIER_CC2DE;         /* CC2 事件触发 DMA */

    /* DMA1 CH7: 内存→CCR2, 8-bit→16-bit */
    DMA1_Channel7->CPAR = (uint32_t)(&TIM2->CCR2);
    DMA1_Channel7->CMAR = (uint32_t)(led_array);
    DMA1_Channel7->CCR  = DMA_CCR7_PSIZE_0  /* 外设 16-bit */
                        | DMA_CCR7_MINC      /* 内存地址递增 */
                        | DMA_CCR7_DIR;      /* 内存→外设 */

    /* 使能中断 */
    NVIC_EnableIRQ(TIM2_IRQn);
    NVIC_EnableIRQ(DMA1_Channel7_IRQn);

    ws2812b_clear();
    bus_retcode();
}

/**
 * @brief  清空 DMA 缓冲区（全灭）
 */
void ws2812b_clear(void)
{
    int i;
    for (i = 0; i < DATA_LEN - 2; i++)
        led_array[i] = VAL_0;       /* 数据位全 0 */
    led_array[DATA_LEN - 2] = 0;    /* 复位高字节 */
    led_array[DATA_LEN - 1] = 0;    /* 复位低字节 */
}

/**
 * @brief  按线性序号设置灯颜色（GRB 顺序写入 DMA 缓冲区）
 */
static int ws2812b_set(int pixn, uint8_t r, uint8_t g, uint8_t b)
{
    int offset = pixn * 24;
    int i;
    uint8_t tmp;

    if (pixn > (WS2812B_NUM_LEDS - 1))
        return 1;

    /* G 分量 (bit23~bit16) */
    tmp = g;
    for (i = 0; i < 8; i++) {
        led_array[offset + i] = (tmp & 0x80) ? VAL_1 : VAL_0;
        tmp <<= 1;
    }

    /* R 分量 (bit15~bit8) */
    tmp = r;
    for (i = 0; i < 8; i++) {
        led_array[offset + i + 8] = (tmp & 0x80) ? VAL_1 : VAL_0;
        tmp <<= 1;
    }

    /* B 分量 (bit7~bit0) */
    tmp = b;
    for (i = 0; i < 8; i++) {
        led_array[offset + i + 16] = (tmp & 0x80) ? VAL_1 : VAL_0;
        tmp <<= 1;
    }

    return 0;
}

/**
 * @brief  按坐标设置灯颜色（蛇形映射→线性序号）
 */
void ws2812b_pixel(uint8_t x, uint8_t y, uint8_t r, uint8_t g, uint8_t b)
{
    int pixn;
    if (x >= WS2812B_COLS || y >= WS2812B_ROWS)
        return;
    /* 偶数列: y=0在顶, 奇数列: y=0在底 */
    if (x & 1)
        pixn = x * WS2812B_ROWS + (WS2812B_ROWS - 1 - y);
    else
        pixn = x * WS2812B_ROWS + y;
    ws2812b_set(pixn, r, g, b);
}

/**
 * @brief  启动 DMA 发送
 *
 * 流程：停止DMA → 设定长度 → 启动定时器 → 清标志 → 开DMA
 * 完成后由 DMA1_CH7 中断触发复位信号，再由 TIM2 中断置位 flag_rdy
 */
void ws2812b_flush(void)
{
    if (flag_rdy) {
        flag_rdy = 0;
        DMA1_Channel7->CCR &= ~(DMA_CCR7_EN);
        DMA1_Channel7->CNDTR = sizeof(led_array);
        TIM2->ARR  = TIMER_AAR;
        TIM2->CCR2 = 0x0000;
        TIM2->CNT  = 0;
        TIM2->CR1 |= TIM_CR1_CEN;
        DMA1->IFCR = DMA_IFCR_CTEIF7 | DMA_IFCR_CHTIF7
                   | DMA_IFCR_CTCIF7 | DMA_IFCR_CGIF7;
        DMA1_Channel7->CCR |= DMA_CCR7_TCIE;
        DMA1_Channel7->CCR |= DMA_CCR7_EN;
    }
}

int ws2812b_ready(void)
{
    return flag_rdy;
}

/**
 * @brief  按物理位置写入整帧数据并发送
 * @param  data  data[256][3]，按行优先排列：
 *               data[0]  = (列0,行0) = 灯1    data[1]  = (列1,行0) = 灯32
 *               data[2]  = (列2,行0) = 灯33   data[15] = (列15,行0)= 灯256
 *               data[16] = (列0,行1) = 灯2    data[17] = (列1,行1) = 灯31
 *               data[row*16 + col] = 物理位置(列col, 行row)的灯
 */
void ws2812b_write(const uint8_t data[][3])
{
    int i;
    for (i = 0; i < WS2812B_NUM_LEDS; i++) {
        int row = i / WS2812B_COLS;
        int col = i % WS2812B_COLS;
        int pixn;
        if (col & 1)
            pixn = col * WS2812B_ROWS + (WS2812B_ROWS - 1 - row);
        else
            pixn = col * WS2812B_ROWS + row;
        ws2812b_set(pixn, data[i][0], data[i][1], data[i][2]);
    }
    ws2812b_flush();
}

/**
 * @brief  启动总线复位信号（>50µs 低电平）
 *
 * DMA 传输结束后调用，用定时器中断保证复位时间
 */
static void bus_retcode(void)
{
    TIM2->CR1  &= ~(TIM_CR1_CEN);
    TIM2->ARR   = TIMER_AAR * 45;   /* 45 × 1.25µs = 56.25µs > 50µs */
    TIM2->CNT   = 0;
    TIM2->CCR2  = 0x0000;
    TIM2->SR   &= ~(TIM_SR_UIF);
    TIM2->DIER |= TIM_DIER_UIE;     /* 更新中断 */
    TIM2->CR1  |= TIM_CR1_CEN;
}

/**
 * @brief  DMA1 CH7 中断 — 数据发送完成，启动复位
 */
void DMA1_Channel7_IRQHandler(void)
{
    DMA1_Channel7->CCR &= ~(DMA_CCR7_EN);
    DMA1->IFCR = DMA_IFCR_CTEIF7 | DMA_IFCR_CHTIF7
               | DMA_IFCR_CTCIF7 | DMA_IFCR_CGIF7;
    bus_retcode();
}

/**
 * @brief  TIM2 中断 — 复位完成，标记就绪
 */
void TIM2_IRQHandler(void)
{
    TIM2->SR = 0;
    TIM2->CR1  &= ~(TIM_CR1_CEN);
    TIM2->DIER &= ~(TIM_DIER_UIE);
    flag_rdy = 1;
}
