#ifndef _LWIPOPTS_H
#define _LWIPOPTS_H

// -----------------------------------------------------
// 1. OS（FreeRTOS）と連携するための必須設定
// -----------------------------------------------------
#define NO_SYS                      0  // FreeRTOS OS 統合モード
#define SYS_LIGHTWEIGHT_PROT        1  // lwIP クリティカルセクションを FreeRTOS mutex で保護（必須）
#define LWIP_SOCKET                 1  // POSIX 風 socket() API を有効化
#define LWIP_NETCONN                1  // ネットコネクション API を有効化

// FreeRTOS スレッドのスタック・優先度
#define TCPIP_THREAD_PRIO           (configMAX_PRIORITIES - 2)
#define TCPIP_THREAD_STACKSIZE      2048
#define DEFAULT_THREAD_STACKSIZE    1024

// lwIP 内部キュー (メールボックス) サイズ
#define TCPIP_MBOX_SIZE             64
#define DEFAULT_ACCEPTMBOX_SIZE     8
#define DEFAULT_RAW_RECVMBOX_SIZE   16
#define DEFAULT_UDP_RECVMBOX_SIZE   16
#define DEFAULT_TCP_RECVMBOX_SIZE   16

// -----------------------------------------------------
// 2. コア機能の有効化設定（EPICS 通信用）
// -----------------------------------------------------
#define LWIP_ARP                    1
#define LWIP_ETHERNET               1
#define LWIP_ICMP                   1  // Ping 応答（デバッグに便利）
#define LWIP_RAW                    1

// EPICS Channel Access は UDP (検索) と TCP (データ) の両方を使用
#define LWIP_UDP                    1
#define LWIP_TCP                    1
#define TCP_MSS                     1460

// -----------------------------------------------------
// 3. メモリ・バッファ設定（Pico 2W の 520 KB RAM を活用）
// -----------------------------------------------------
#define MEM_ALIGNMENT               4
#define MEM_SIZE                    (20 * 1024)  // lwIP ヒープ 20 KB

#define PBUF_POOL_SIZE              24
#define MEMP_NUM_PBUF               16
#define MEMP_NUM_UDP_PCB            6
#define MEMP_NUM_TCP_PCB            10
#define MEMP_NUM_TCP_PCB_LISTEN     4
#define MEMP_NUM_TCPIP_MSG_INPKT    16
#define MEMP_NUM_TCPIP_MSG_API      16

// -----------------------------------------------------
// 4. チェックサム計算
// -----------------------------------------------------
#define CHECKSUM_GEN_IP             1
#define CHECKSUM_GEN_UDP            1
#define CHECKSUM_GEN_TCP            1
#define CHECKSUM_CHECK_IP           1
#define CHECKSUM_CHECK_UDP          1
#define CHECKSUM_CHECK_TCP          1

#endif /* _LWIPOPTS_H */
