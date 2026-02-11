/**
 * Type definitions for the bridge module.
 * # 桥接模块的类型定义
 */

declare module 'nanobot-bridge' {
  /**
   * Inbound message from WhatsApp.
   * # 来自 WhatsApp 的入站消息
   */
  export interface InboundMessage {
    /** Message ID / 消息 ID */
    id: string;
    /** Sender's phone number (JID) / 发送者的电话号码 (JID) */
    sender: string;
    /** Alternative phone number / 备用电话号码 */
    pn: string;
    /** Message content / 消息内容 */
    content: string;
    /** Unix timestamp / Unix 时间戳 */
    timestamp: number;
    /** Whether this is a group message / 是否为群组消息 */
    isGroup: boolean;
  }

  /**
   * Bridge configuration options.
   * # 桥接配置选项
   */
  export interface BridgeConfig {
    /** WebSocket port / WebSocket 端口 */
    port: number;
    /** Authentication directory / 认证目录 */
    authDir: string;
  }

  /**
   * Bridge event types.
   * # 桥接事件类型
   */
  export type BridgeEventType = 'message' | 'status' | 'qr' | 'error';

  /**
   * Bridge message payload.
   * # 桥接消息载荷
   */
  export interface BridgeMessage<T = unknown> {
    /** Event type / 事件类型 */
    type: BridgeEventType;
    /** Event data / 事件数据 */
    data: T;
  }
}
