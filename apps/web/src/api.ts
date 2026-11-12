export type Tenant = { id: string; name: string; role: string };
export type User = { id: string; email: string };
type ApiErrorBody = { error?: { code?: string; message?: string } };

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) { super(message); }
}

async function request<T>(path: string, token?: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
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

export async function login(email: string, password: string): Promise<string> {
  const result = await request<{ access_token: string }>('/auth/login', undefined, {
    method: 'POST', body: JSON.stringify({ email, password }),
  });
  return result.access_token;
}

export const getMe = (token: string) => request<User>('/auth/me', token);
export async function getTenants(token: string): Promise<Tenant[]> {
  const items: Tenant[] = [];
  let cursor: string | null = null;
  do {
    const path: string = cursor ? `/tenants?cursor=${encodeURIComponent(cursor)}` : '/tenants';
    const page: { items: Tenant[]; next_cursor: string | null } = await request(path, token);
    items.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);
  return items;
}
export const getCurrentTenant = (token: string, tenantId: string) =>
  request<Tenant>('/tenants/current', token, { headers: { 'X-Tenant-ID': tenantId } });
export const logout = (token: string) => request<void>('/auth/logout', token, { method: 'POST' });
