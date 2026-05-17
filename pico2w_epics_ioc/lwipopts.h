#ifndef _LWIPOPTS_H
#define _LWIPOPTS_H

// -----------------------------------------------------
// 1. OS（FreeRTOS）と連携するための必須設定
// -----------------------------------------------------
#define NO_SYS                      0  // 0にすることで、FreeRTOSなどのOS（マルチタスク）対応モードになります
#define LWIP_SOCKET                 1  // main.c で socket() 関数（POSIX風）を使うために必要
#define LWIP_NETCONN                1  // ネットコネクションAPIを有効化

// FreeRTOSのセマフォやタスク管理の仕組みをlwIPにバインドする設定
#define TCPIP_THREAD_PRIO           3  // lwIP自体のタスク優先度（FreeRTOSのconfigMAX_PRIORITIES未満にする）
#define TCPIP_THREAD_STACKSIZE      1024
#define DEFAULT_THREAD_STACKSIZE    1024

// -----------------------------------------------------
// 2. コア機能の有効化設定（EPICS通信用）
// -----------------------------------------------------
#define LWIP_ARP                    1  // MACアドレス解決（必須）
#define LWIP_ETHERNET               1  // イーサネット（必須）
#define LWIP_ICMP                   1  // Pingに応答できるようにする（デバッグに超便利）
#define LWIP_RAW                    1

// EPICS Channel Access は UDP と TCP の両方を使用します
#define LWIP_UDP                    1  // サーチ要求（caget時の探索）に必須
#define LWIP_TCP                    1  // 実際のPVデータの購読（camonitorなど）に必須
#define TCP_MSS                     1460 // 最大セグメントサイズ

// -----------------------------------------------------
// 3. メモリ・バッファ設定（Pico 2 Wの520KBのRAMを活かしてリッチに確保）
// -----------------------------------------------------
#define MEM_ALIGNMENT               4  // 32bitマイコン（RP2350）に最適化
#define MEM_SIZE                    (16 * 1024) // lwIPが自由に使えるヒープ領域（16KB）

// パケットバッファ（PBUF）の数
#define PBUF_POOL_SIZE              24 // 少し多めに確保して、EPICSの大量のサーチパケットの取りこぼしを防ぐ
#define MEMP_NUM_PBUF               16
#define MEMP_NUM_UDP_PCB            6
#define MEMP_NUM_TCP_PCB            10
#define MEMP_NUM_TCP_PCB_LISTEN     5

// 💡 EPICSは1つのポート（5064）に対してブロードキャストやマルチキャストを多用するため、
// バッファを絞りすぎるとパケットがドロップして、PCからPVが見えなくなる原因になります。

// -----------------------------------------------------
// 4. チェックサム計算のハードウェアオフロード（Pico 2 Wの最適化）
// -----------------------------------------------------
// Pico 2 W（RP2350）側で自動でパケットのチェックサムを計算させ、CPU負荷を下げます
#define CHECKSUM_GEN_IP             1
#define CHECKSUM_GEN_UDP            1
#define CHECKSUM_GEN_TCP            1
#define CHECKSUM_CHECK_IP           1
#define CHECKSUM_CHECK_UDP          1
#define CHECKSUM_CHECK_TCP          1

#endif /* _LWIPOPTS_H */
