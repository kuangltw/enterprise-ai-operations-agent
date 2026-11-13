export type Tenant = { id: string; name: string; role: string };
export type CurrentTenant = Tenant & { permissions: string[] };
export type User = { id: string; email: string };
type ApiErrorBody = { error?: { code?: string; message?: string } };

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) { super(message); }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.method && init.method !== 'GET') headers.set('X-Session-Request', '1');
  if (init.body) headers.set('Content-Type', 'application/json');
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { ...init, headers, cache: 'no-store' });
  } catch {
    throw new ApiError(0, '無法連線至 API，請稍後再試。');
  }
  if (!response.ok) {
    let body: ApiErrorBody = {};
    try { body = await response.json() as ApiErrorBody; } catch { /* 非 JSON 錯誤仍保留狀態碼 */ }
    throw new ApiError(response.status, body.error?.message || `API 回應錯誤（${response.status}）`);
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export function login(email: string, password: string): Promise<void> {
  return request<void>('/auth/session', {
    method: 'POST', body: JSON.stringify({ email, password }),
  });
}

export const getMe = () => request<User>('/auth/me');
export async function getTenants(): Promise<Tenant[]> {
  const items: Tenant[] = [];
  let cursor: string | null = null;
  do {
    const path: string = cursor ? `/tenants?cursor=${encodeURIComponent(cursor)}` : '/tenants';
    const page: { items: Tenant[]; next_cursor: string | null } = await request(path);
    items.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);
  return items;
}
export const getCurrentTenant = (tenantId: string) =>
  request<CurrentTenant>('/tenants/current', { headers: { 'X-Tenant-ID': tenantId } });
export const logout = () => request<void>('/auth/logout', { method: 'POST' });
