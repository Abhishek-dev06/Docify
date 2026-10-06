export async function api<T>(path:string, init:RequestInit = {}):Promise<T> {
  const response = await fetch(`/api/v1${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error?.message || body.detail || `Request failed (${response.status}).`);
  return body as T;
}
export function imageUrl(base64:string) { return `data:image/png;base64,${base64}`; }
export function label(value:string) { return value.replaceAll('_',' ').replace(/^./, c=>c.toUpperCase()); }
