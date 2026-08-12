"use client"

import { useEffect, useRef } from 'react';

type RealtimeEvent = {
  resource: string;
  action: 'created' | 'updated' | 'deleted';
};

type EventHandler = (event: RealtimeEvent) => void;

let socket: WebSocket | null = null;
let listeners: Set<EventHandler> = new Set();
let reconnectTimer: NodeJS.Timeout | null = null;
let isConnecting = false;

const connect = () => {
  if (socket || isConnecting) return;

  isConnecting = true;
  console.log("Realtime: Connecting...");

  const wsUrl = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1")
    .replace("http", "ws") + "/ws";

  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    console.log("Realtime: Connected.");
    isConnecting = false;
    if (reconnectTimer) {
      clearInterval(reconnectTimer);
      reconnectTimer = null;
    }
  };

  socket.onmessage = (event) => {
    try {
      const parsedEvent: RealtimeEvent = JSON.parse(event.data);
      listeners.forEach(listener => listener(parsedEvent));
    } catch (error) {
      console.error("Realtime: Error parsing message", error);
    }
  };

  socket.onclose = () => {
    console.log("Realtime: Disconnected.");
    socket = null;
    isConnecting = false;
    if (!reconnectTimer) {
      reconnectTimer = setInterval(() => {
        console.log("Realtime: Attempting to reconnect...");
        connect();
      }, 5000);
    }
  };

  socket.onerror = (error) => {
    console.error("Realtime: WebSocket error", error);
    socket?.close();
  };
};

export const useRealtime = (handler: EventHandler) => {
  useEffect(() => {
    connect();
    listeners.add(handler);

    return () => {
      listeners.delete(handler);
      // Note: We don't close the socket here to maintain a single connection
      // across the app. A more advanced implementation might use reference counting.
    };
  }, [handler]);
};