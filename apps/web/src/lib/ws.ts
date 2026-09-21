export type WsStatus = 'connecting' | 'open' | 'closed';

export interface WsMessage {
  type: string;
  [key: string]: unknown;
}

export type WsHandler = (message: WsMessage) => void;

interface LiveSocketOptions {
  getToken: () => Promise<string | undefined>;
  onStatus: (status: WsStatus) => void;
  onHeartbeat: (receivedAt: number) => void;
}

const MAX_BACKOFF_MS = 30_000;

function liveUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/live`;
}

export class LiveSocket {
  private ws: WebSocket | null = null;
  private attempt = 0;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private stopped = true;
  private generation = 0;
  private readonly topics = new Map<string, number>();
  private readonly handlers = new Set<WsHandler>();
  private readonly options: LiveSocketOptions;

  constructor(options: LiveSocketOptions) {
    this.options = options;
  }

  start(): void {
    this.stopped = false;
    this.generation += 1;
    void this.connect(this.generation);
  }

  stop(): void {
    this.stopped = true;
    this.generation += 1;
    clearTimeout(this.timer);
    const ws = this.ws;
    this.ws = null;
    ws?.close();
  }

  subscribe(topics: string[], handler: WsHandler): () => void {
    this.handlers.add(handler);
    const added = topics.filter((topic) => {
      const count = this.topics.get(topic) ?? 0;
      this.topics.set(topic, count + 1);
      return count === 0;
    });
    this.send('subscribe', added);
    return () => {
      this.handlers.delete(handler);
      const removed = topics.filter((topic) => {
        const count = (this.topics.get(topic) ?? 1) - 1;
        if (count <= 0) this.topics.delete(topic);
        else this.topics.set(topic, count);
        return count <= 0;
      });
      this.send('unsubscribe', removed);
    };
  }

  private send(type: 'subscribe' | 'unsubscribe', topics: string[]): void {
    if (topics.length && this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type, topics }));
  }

  private async connect(generation: number): Promise<void> {
    this.options.onStatus('connecting');
    let token: string | undefined;
    try {
      token = await this.options.getToken();
    } catch {
      this.scheduleReconnect();
      return;
    }
    if (generation !== this.generation) return;
    const ws = new WebSocket(token ? `${liveUrl()}?token=${encodeURIComponent(token)}` : liveUrl());
    this.ws = ws;
    ws.onopen = () => {
      this.attempt = 0;
      this.options.onStatus('open');
      this.send('subscribe', [...this.topics.keys()]);
    };
    ws.onmessage = (event: MessageEvent<string>) => this.dispatch(event.data);
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.options.onStatus('closed');
      this.scheduleReconnect();
    };
  }

  private dispatch(raw: string): void {
    let message: WsMessage;
    try {
      message = JSON.parse(raw) as WsMessage;
    } catch {
      return;
    }
    if (message.type === 'heartbeat') this.options.onHeartbeat(Date.now());
    else this.handlers.forEach((handler) => handler(message));
  }

  private scheduleReconnect(): void {
    if (this.stopped) return;
    const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** this.attempt);
    this.attempt += 1;
    clearTimeout(this.timer);
    const generation = this.generation;
    this.timer = setTimeout(() => void this.connect(generation), delay);
  }
}
