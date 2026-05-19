import { useEffect, useRef, useState, useCallback } from "react";

// Native WebSocket hook with auto-reconnect. NOT socket.io — the backend
// speaks raw WebSocket, so anything else would silently fail the handshake.
//
// Returns { events, lastEvent, status, send } where status ∈
//   "connecting" | "open" | "closed" | "error"
//
// Reconnect delays climb 1s → 2s → 5s → 10s → 30s (then plateau).
const BACKOFF = [1000, 2000, 5000, 10000, 30000];

export function useWebSocket(path = "/ws", { maxEvents = 200 } = {}) {
  const [events, setEvents] = useState([]);
  const [lastEvent, setLastEvent] = useState(null);
  const [status, setStatus] = useState("connecting");
  const wsRef = useRef(null);
  const attemptRef = useRef(0);
  const reconnectTimer = useRef(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${window.location.host}${path}`;
    setStatus("connecting");
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (err) {
      setStatus("error");
      scheduleReconnect();
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      attemptRef.current = 0;
      setStatus("open");
    };

    ws.onmessage = (e) => {
      let parsed;
      try {
        parsed = JSON.parse(e.data);
      } catch {
        parsed = { type: "RAW", raw: e.data };
      }
      const stamped = { ...parsed, _receivedAt: new Date().toISOString() };
      setLastEvent(stamped);
      setEvents((prev) => {
        const next = [...prev, stamped];
        return next.length > maxEvents ? next.slice(-maxEvents) : next;
      });
    };

    ws.onclose = () => {
      setStatus("closed");
      scheduleReconnect();
    };

    ws.onerror = () => {
      setStatus("error");
      // onclose will fire after onerror and trigger the retry.
    };
  }, [path, maxEvents]);

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;
    const delay = BACKOFF[Math.min(attemptRef.current, BACKOFF.length - 1)];
    attemptRef.current += 1;
    clearTimeout(reconnectTimer.current);
    reconnectTimer.current = setTimeout(connect, delay);
  }, [connect]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  const send = useCallback((data) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(typeof data === "string" ? data : JSON.stringify(data));
    }
  }, []);

  const clear = useCallback(() => {
    setEvents([]);
    setLastEvent(null);
  }, []);

  return { events, lastEvent, status, send, clear };
}
