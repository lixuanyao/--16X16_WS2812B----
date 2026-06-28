#include "stm32f10x.h"
#include "ws2812b.h"
#include <stdio.h>

#pragma import(__use_no_semihosting)

void _sys_exit(int x)
{
    while (1);
}

static volatile uint32_t tick;

// 串口同步协议定义
#define SYNC_BYTE 0xAA // 同步字节
#define DATA_LENGTH (WS2812B_NUM_LEDS * 3) // 768字节
#define UART_TIMEOUT_MS 1000 // 接收超时时间（毫秒）

// 串口接收状态机
typedef enum {
    UART_STATE_IDLE,      // 等待同步字节
    UART_STATE_RECEIVING  // 正在接收数据
} UART_State;

// 串口接收缓冲区
static uint8_t uart_rx_buf[DATA_LENGTH];
static volatile uint16_t uart_rx_index = 0;
static volatile uint8_t uart_rx_complete = 0;
static volatile UART_State uart_state = UART_STATE_IDLE;

void SysTick_Handler(void)
{
    tick++;
}

static void delay_ms(uint32_t ms)
{
    uint32_t start = tick;
    while ((tick - start) < ms);
}

// USART1初始化函数
void USART1_Init(uint32_t baudrate)
{
    // 使能时钟
    RCC->APB2ENR |= RCC_APB2ENR_USART1EN | RCC_APB2ENR_IOPAEN | RCC_APB2ENR_AFIOEN;
    
    // 配置PA9(TX)为复用推挽输出，PA10(RX)为浮空输入
    GPIOA->CRH &= ~(GPIO_CRH_CNF9 | GPIO_CRH_MODE9 | GPIO_CRH_CNF10 | GPIO_CRH_MODE10);
    GPIOA->CRH |= GPIO_CRH_CNF9_1 | GPIO_CRH_MODE9_1; // PA9: AF推挽输出，50MHz
    GPIOA->CRH |= GPIO_CRH_CNF10_0; // PA10: 浮空输入
    
    // 配置USART1
    USART1->BRR = SystemCoreClock / baudrate; // 波特率设置
    USART1->CR1 = USART_CR1_TE | USART_CR1_RE | USART_CR1_UE;
}

// 重定向printf到USART1
int fputc(int ch, FILE *f)
{
    // 等待发送数据寄存器空
    while (!(USART1->SR & USART_SR_TXE));
    USART1->DR = (uint8_t)ch;
    return ch;
}



int main(void)
{
    SystemInit();
    SysTick_Config(72000);  /* 1ms tick @ 72MHz */
    __enable_irq();
    ws2812b_init();
    USART1_Init(115200); // 初始化串口，波特率115200
    // 等待初始化完成（flag_rdy被置1）
    while (!ws2812b_ready());
    
    // 启动白闪
    for (int i = 0; i < WS2812B_NUM_LEDS; i++)
        ws2812b_pixel(i % WS2812B_COLS, i / WS2812B_COLS, 0xff, 0xff, 0xff);
    ws2812b_flush();
    while (!ws2812b_ready());
    delay_ms(500);
    ws2812b_clear();
    ws2812b_flush();
    while (!ws2812b_ready());
    
    uint32_t last_rx_tick = tick;
    while (1) {
        while (USART1->SR & USART_SR_RXNE) {
            uint8_t data = (uint8_t)USART1->DR;
            
            if (uart_state == UART_STATE_IDLE) {
                if (data == SYNC_BYTE) {
                    uart_rx_index = 0;
                    uart_state = UART_STATE_RECEIVING;
                    last_rx_tick = tick;
                }
            } else {
                if (uart_rx_index < DATA_LENGTH) {
                    uart_rx_buf[uart_rx_index++] = data;
                    if (uart_rx_index >= DATA_LENGTH) {
                        uart_rx_complete = 1;
                        uart_state = UART_STATE_IDLE;
                    }
                } else {
                    uart_state = UART_STATE_IDLE;
                }
            }
        }
        
        if (uart_rx_complete) {
            uart_rx_complete = 0;
            ws2812b_write((const uint8_t (*)[3])uart_rx_buf);
            while (!ws2812b_ready());
        }
        else {
            if (uart_state == UART_STATE_RECEIVING && 
                (tick - last_rx_tick) > UART_TIMEOUT_MS) {
                uart_state = UART_STATE_IDLE;
                uart_rx_index = 0;
            }
        }
    }
}
