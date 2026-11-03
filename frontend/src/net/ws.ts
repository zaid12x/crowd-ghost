// Binary frame decoder — mirrors backend/app/protocol.py
export interface Frame {
  tick: number;
  flags: number;
  agents: Float32Array; // n*4: x, y, vx, vy
  nAgents: number;
  rooms: Float32Array; // n*3: queue_len, rho, wait_est
  nRooms: number;
}

export function decodeFrame(buf: ArrayBuffer): Frame {
  const view = new DataView(buf);
  const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
  if (magic !== 'CGF1') throw new Error('bad magic: ' + magic);
  const tick = view.getUint32(4, true);
  const nAgents = view.getUint16(8, true);
  const nRooms = view.getUint16(10, true);
  const flags = view.getUint16(12, true);
  let offset = 16;
  const agents = new Float32Array(buf, offset, nAgents * 4).slice();
  offset += nAgents * 4 * 4;
  const rooms = new Float32Array(buf, offset, nRooms * 3).slice();
  return { tick, flags, agents, nAgents, rooms, nRooms };
}

export type FrameHandler = (f: Frame) => void;

export class GhostSocket {
  private ws: WebSocket | null = null;
  onFrame: FrameHandler | null = null;
  onStatus: ((s: string) => void) | null = null;

  connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${location.host}/ws`;
    this.onStatus?.(`connecting ${url}`);
    this.ws = new WebSocket(url);
    this.ws.binaryType = 'arraybuffer';
    this.ws.onopen = () => this.onStatus?.('connected');
    this.ws.onclose = () => {
      this.onStatus?.('disconnected — retrying in 1s');
      setTimeout(() => this.connect(), 1000);
    };
    this.ws.onerror = () => this.onStatus?.('error');
    this.ws.onmessage = (ev) => {
      if (ev.data instanceof ArrayBuffer && this.onFrame) {
        try { this.onFrame(decodeFrame(ev.data)); } catch (e) { console.error(e); }
      }
    };
  }

  send(obj: unknown) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
    }
  }
}
