/**
 * WebSocket server for Python-Node.js bridge communication.
 * # 用于 Python-Node.js 桥接通信的 WebSocket 服务器
 */

import { WebSocketServer, WebSocket } from 'ws';
// # 导入 WebSocket 相关模块
import { WhatsAppClient, InboundMessage } from './whatsapp.js';

// Send command interface from Python
// # 来自 Python 的发送命令接口
interface SendCommand {
  type: 'send';
  to: string;
  text: string;
}

// Bridge message interface
// # 桥接消息接口
interface BridgeMessage {
  type: 'message' | 'status' | 'qr' | 'error';
  [key: string]: unknown;
}

/**
 * Bridge server that handles WebSocket connections between
 * Python backend and WhatsApp client.
 * # 桥接服务器，处理 Python 后端和 WhatsApp 客户端之间的 WebSocket 连接
 */
export class BridgeServer {
  private wss: WebSocketServer | null = null;
  // # WebSocket 服务器实例
  private wa: WhatsAppClient | null = null;
  // # WhatsApp 客户端实例
  private clients: Set<WebSocket> = new Set();
  // # 已连接的 Python 客户端集合

  constructor(private port: number, private authDir: string) {}
  // # 构造函数

  /**
   * Start the bridge server and WhatsApp client.
   * # 启动桥接服务器和 WhatsApp 客户端
   */
  async start(): Promise<void> {
    // Create WebSocket server
    // # 创建 WebSocket 服务器
    this.wss = new WebSocketServer({ port: this.port });
    console.log(`🌉 Bridge server listening on ws://localhost:${this.port}`);

    // Initialize WhatsApp client
    // # 初始化 WhatsApp 客户端
    this.wa = new WhatsAppClient({
      authDir: this.authDir,
      onMessage: (msg) => this.broadcast({ type: 'message', ...msg }),
      // # 消息回调 - 广播到所有 Python 客户端
      onQR: (qr) => this.broadcast({ type: 'qr', qr }),
      // # 二维码回调 - 广播二维码
      onStatus: (status) => this.broadcast({ type: 'status', status }),
      // # 状态回调 - 广播连接状态
    });

    // Handle WebSocket connections
    // # 处理 WebSocket 连接
    this.wss.on('connection', (ws) => {
      console.log('🔗 Python client connected');
      // # Python 客户端连接
      this.clients.add(ws);

      ws.on('message', async (data) => {
        try {
          const cmd = JSON.parse(data.toString()) as SendCommand;
          await this.handleCommand(cmd);
          ws.send(JSON.stringify({ type: 'sent', to: cmd.to }));
        } catch (error) {
          console.error('Error handling command:', error);
          ws.send(JSON.stringify({ type: 'error', error: String(error) }));
        }
      });

      ws.on('close', () => {
        console.log('🔌 Python client disconnected');
        // # Python 客户端断开连接
        this.clients.delete(ws);
      });

      ws.on('error', (error) => {
        console.error('WebSocket error:', error);
        this.clients.delete(ws);
      });
    });

    // Connect to WhatsApp
    // # 连接到 WhatsApp
    await this.wa.connect();
  }

  /**
   * Handle command from Python client.
   * # 处理来自 Python 客户端的命令
   */
  private async handleCommand(cmd: SendCommand): Promise<void> {
    if (cmd.type === 'send' && this.wa) {
      // # 发送消息命令
      await this.wa.sendMessage(cmd.to, cmd.text);
    }
  }

  /**
   * Broadcast message to all connected Python clients.
   * # 向所有连接的 Python 客户端广播消息
   */
  private broadcast(msg: BridgeMessage): void {
    const data = JSON.stringify(msg);
    for (const client of this.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(data);
      }
    }
  }

  /**
   * Stop the bridge server.
   * # 停止桥接服务器
   */
  async stop(): Promise<void> {
    // Close all client connections
    // # 关闭所有客户端连接
    for (const client of this.clients) {
      client.close();
    }
    this.clients.clear();

    // Close WebSocket server
    // # 关闭 WebSocket 服务器
    if (this.wss) {
      this.wss.close();
      this.wss = null;
    }

    // Disconnect WhatsApp
    // # 断开 WhatsApp 连接
    if (this.wa) {
      await this.wa.disconnect();
      this.wa = null;
    }
  }
}
