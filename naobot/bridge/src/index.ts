#!/usr/bin/env node
/**
 * nanobot WhatsApp Bridge
 * # nanobot WhatsApp 桥接模块
 * 
 * This bridge connects WhatsApp Web to nanobot's Python backend
 * via WebSocket. It handles authentication, message forwarding,
 * and reconnection logic.
 * # 此桥接模块通过 WebSocket 将 WhatsApp Web 连接到 nanobot 的 Python 后端
 * # 处理认证、消息转发和重连逻辑
 * 
 * Usage:
 *   npm run build && npm start
 *   
 * Or with custom settings:
 *   BRIDGE_PORT=3001 AUTH_DIR=~/.nanobot/whatsapp npm start
 * # 使用方法：
 * #   npm run build && npm start
 * # 
 * # 或使用自定义设置：
 * #   BRIDGE_PORT=3001 AUTH_DIR=~/.nanobot/whatsapp npm start
 */

// Polyfill crypto for Baileys in ESM
// # 为 ESM 环境中的 Baileys 填充 crypto 模块
import { webcrypto } from 'crypto';
if (!globalThis.crypto) {
  (globalThis as any).crypto = webcrypto;
}

import { BridgeServer } from './server.js';
// # 导入桥接服务器类
import { homedir } from 'os';
import { join } from 'path';

const PORT = parseInt(process.env.BRIDGE_PORT || '3001', 10);
// # 桥接服务器端口，默认 3001
const AUTH_DIR = process.env.AUTH_DIR || join(homedir(), '.nanobot', 'whatsapp-auth');
// # WhatsApp 认证目录，默认 ~/.nanobot/whatsapp-auth

console.log('🐈 nanobot WhatsApp Bridge');
console.log('========================\n');

const server = new BridgeServer(PORT, AUTH_DIR);

// Handle graceful shutdown
// # 处理优雅关闭
process.on('SIGINT', async () => {
  console.log('\n\nShutting down...');
  await server.stop();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await server.stop();
  process.exit(0);
});

// Start the server
// # 启动服务器
server.start().catch((error) => {
  console.error('Failed to start bridge:', error);
  process.exit(1);
});

// Type declaration for qrcode-terminal module
// # qrcode-terminal 模块的类型声明
declare module 'qrcode-terminal' {
  export function generate(text: string, options?: { small?: boolean }): void;
}
