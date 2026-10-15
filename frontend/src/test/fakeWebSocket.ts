/** Test double for the browser WebSocket: tests open, push, or drop sockets explicitly. */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = []

  readonly url: string
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null

  constructor(url: string | URL) {
    this.url = String(url)
    FakeWebSocket.instances.push(this)
  }

  static reset() {
    FakeWebSocket.instances = []
  }

  open() {
    this.onopen?.(new Event('open'))
  }

  receive(payload: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(payload) }))
  }

  /** Simulate the server or network dropping the connection. */
  drop() {
    this.onclose?.(new Event('close') as CloseEvent)
  }

  close() {
    // Client-initiated close: the hook has already stopped reconnecting before calling this.
  }
}
