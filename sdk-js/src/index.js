export function connectAssistantWS(baseUrl, path = "/ws/assistant") {
  const url = new URL(path, baseUrl);
  return new WebSocket(url);
}
