const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export function apiUrl(path:string) {
  return `${API_BASE}/api/v1${path}`;
}

export async function api<T>(path:string, init:RequestInit = {}):Promise<T> {
  const response = await fetch(apiUrl(path), init);
  const contentType = response.headers?.get?.('content-type') || '';
  if (!contentType.includes('application/json')) {
    throw new Error(`API returned a non-JSON response (${response.status}). Check VITE_API_BASE_URL.`);
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error?.message || body.detail || `Request failed (${response.status}).`);
  return body as T;
}
export function imageUrl(base64:string) { return `data:image/png;base64,${base64}`; }
export function label(value:string) { return value.replaceAll('_',' ').replace(/^./, c=>c.toUpperCase()); }
