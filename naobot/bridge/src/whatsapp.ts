/**
 * WhatsApp client wrapper using Baileys.
 * # 使用 Baileys 的 WhatsApp 客户端封装
 * 
 * Based on OpenClaw's working implementation.
 * # 基于 OpenClaw 的实现
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} from '@whiskeysockets/baileys';
// # 导入 Baileys 库

import { Boom } from '@hapi/boom';
// # 导入错误处理工具
import qrcode from 'qrcode-terminal';
// # 导入二维码生成工具
import pino from 'pino';
// # 导入日志工具

const VERSION = '0.1.0';

/**
 * Inbound message structure from WhatsApp.
 * # 来自 WhatsApp 的入站消息结构
 */
export interface InboundMessage {
  /** Unique message ID / 唯一消息 ID */
  id: string;
  /** Sender's JID (phone number) / 发送者的 JID (电话号码) */
  sender: string;
  /** Alternative phone number / 备用电话号码 */
  pn: string;
  /** Message content / 消息内容 */
  content: string;
  /** Unix timestamp / Unix 时间戳 */
  timestamp: number;
  /** Whether it's a group message / 是否为群组消息 */
  isGroup: boolean;
}

/**
 * WhatsApp client configuration options.
 * # WhatsApp 客户端配置选项
 */
export interface WhatsAppClientOptions {
  /** Authentication directory for session persistence / 用于会话持久化的认证目录 */
  authDir: string;
  /** Callback for incoming messages / 入站消息回调 */
  onMessage: (msg: InboundMessage) => void;
  /** Callback for QR code updates / 二维码更新回调 */
  onQR: (qr: string) => void;
  /** Callback for connection status changes / 连接状态变化回调 */
  onStatus: (status: string) => void;
}

/**
 * WhatsApp client wrapper using Baileys library.
 * # 使用 Baileys 库的 WhatsApp 客户端封装
 * 
 * Features:
 * - QR code authentication
 * - 自动重连
 * - Message forwarding to Python backend
 * - 消息转发到 Python 后端
 */
export class WhatsAppClient {
  private sock: any = null;
  // # Baileys Socket 实例
  private options: WhatsAppClientOptions;
  // # 客户端配置选项
  private reconnecting = false;
  // # 是否正在重连

  constructor(options: WhatsAppClientOptions) {
    this.options = options;
  }

  /**
   * Connect to WhatsApp Web.
   * # 连接到 WhatsApp Web
   */
  async connect(): Promise<void> {
    const logger = pino({ level: 'silent' });
    // # 创建静默日志记录器

    // Load authentication state from file
    // # 从文件加载认证状态
    const { state, saveCreds } = await useMultiFileAuthState(this.options.authDir);
    
    // Fetch latest Baileys version
    // # 获取最新 Baileys 版本
    const { version } = await fetchLatestBaileysVersion();
    console.log(`Using Baileys version: ${version.join('.')}`);

    // Create socket following OpenClaw's pattern
    // # 按照 OpenClaw 的模式创建 Socket
    this.sock = makeWASocket({
      // Authentication credentials
      // # 认证凭证
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, logger),
      },
      // Baileys version
      // # Baileys 版本
      version,
      // Logger instance
      // # 日志记录器实例
      logger,
      // Don't print QR code in terminal (we handle it)
      // # 不在终端打印二维码（我们自行处理）
      printQRInTerminal: false,
      // Browser identification
      // # 浏览器标识
      browser: ['nanobot', 'cli', VERSION],
      // Don't sync full history for faster connection
      // # 不同步完整历史以加快连接速度
      syncFullHistory: false,
      // Don't mark as online on connect
      // # 连接时不标记为在线
      markOnlineOnConnect: false,
    });

    // Handle WebSocket errors
    // # 处理 WebSocket 错误
    if (this.sock.ws && typeof this.sock.ws.on === 'function') {
      this.sock.ws.on('error', (err: Error) => {
        console.error('WebSocket error:', err.message);
      });
    }

    // Handle connection updates
    // # 处理连接更新
    this.sock.ev.on('connection.update', async (update: any) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        // Display QR code in terminal
        // # 在终端显示二维码
        console.log('\n📱 Scan this QR code with WhatsApp (Linked Devices):\n');
        qrcode.generate(qr, { small: true });
        this.options.onQR(qr);
      }

      if (connection === 'close') {
        // Connection closed
        // # 连接关闭
        const statusCode = (lastDisconnect?.error as Boom)?.output?.statusCode;
        const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

        console.log(`Connection closed. Status: ${statusCode}, Will reconnect: ${shouldReconnect}`);
        this.options.onStatus('disconnected');

        if (shouldReconnect && !this.reconnecting) {
          // Auto reconnect
          // # 自动重连
          this.reconnecting = true;
          console.log('Reconnecting in 5 seconds...');
          setTimeout(() => {
            this.reconnecting = false;
            this.connect();
          }, 5000);
        }
      } else if (connection === 'open') {
        // Connected successfully
        // # 连接成功
        console.log('✅ Connected to WhatsApp');
        this.options.onStatus('connected');
      }
    });

    // Save credentials on update
    // # 更新时保存凭证
    this.sock.ev.on('creds.update', saveCreds);

    // Handle incoming messages
    // # 处理入站消息
    this.sock.ev.on('messages.upsert', async ({ messages, type }: { messages: any[]; type: string }) => {
      if (type !== 'notify') return;

      for (const msg of messages) {
        // Skip own messages
        // # 跳过自己的消息
        if (msg.key.fromMe) continue;

        // Skip status updates
        // # 跳过状态更新
        if (msg.key.remoteJid === 'status@broadcast') continue;

        // Extract message content
        // # 提取消息内容
        const content = this.extractMessageContent(msg);
        if (!content) continue;

        const isGroup = msg.key.remoteJid?.endsWith('@g.us') || false;

        // Forward to Python backend
        // # 转发到 Python 后端
        this.options.onMessage({
          id: msg.key.id || '',
          sender: msg.key.remoteJid || '',
          pn: msg.key.remoteJidAlt || '',
          content,
          timestamp: msg.messageTimestamp as number,
          isGroup,
        });
      }
    });
  }

  /**
   * Extract text content from various message types.
   * # 从各种消息类型中提取文本内容
   */
  private extractMessageContent(msg: any): string | null {
    const message = msg.message;
    if (!message) return null;

    // Text message
    // # 文本消息
    if (message.conversation) {
      return message.conversation;
    }

    // Extended text (reply, link preview)
    // # 扩展文本（回复、链接预览）
    if (message.extendedTextMessage?.text) {
      return message.extendedTextMessage.text;
    }

    // Image with caption
    // # 带标题的图片
    if (message.imageMessage?.caption) {
      return `[Image] ${message.imageMessage.caption}`;
    }

    // Video with caption
    // # 带标题的视频
    if (message.videoMessage?.caption) {
      return `[Video] ${message.videoMessage.caption}`;
    }

    // Document with caption
    // # 带标题的文档
    if (message.documentMessage?.caption) {
      return `[Document] ${message.documentMessage.caption}`;
    }

    // Voice/Audio message
    // # 语音/音频消息
    if (message.audioMessage) {
      return `[Voice Message]`;
    }

    return null;
  }

  /**
   * Send a text message.
   * # 发送文本消息
   */
  async sendMessage(to: string, text: string): Promise<void> {
    if (!this.sock) {
      throw new Error('Not connected');
    }

    await this.sock.sendMessage(to, { text });
  }

  /**
   * Disconnect from WhatsApp.
   * # 断开与 WhatsApp 的连接
   */
  async disconnect(): Promise<void> {
    if (this.sock) {
      this.sock.end(undefined);
      this.sock = null;
    }
  }
}
