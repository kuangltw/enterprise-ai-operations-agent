import { expect, test } from '@playwright/test';

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`缺少 E2E 設定：${name}`);
  return value;
}

const email = required('E2E_USER_EMAIL');
const otherEmail = required('E2E_OTHER_EMAIL');
const password = required('E2E_USER_PASSWORD');
const tenantA = required('E2E_TENANT_A_ID');
const tenantB = required('E2E_TENANT_B_ID');
const tenantC = required('E2E_TENANT_C_ID');

test('未登入時只顯示登入畫面', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '登入工作空間' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '功能概覽' })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('heading', { name: '登入工作空間' })).toBeVisible();
});

test('錯誤密碼不得進入工作空間', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('密碼').fill(`${password}-wrong`);
  await page.getByRole('button', { name: '登入' }).click();
  await expect(page.getByRole('alert')).toContainText('帳號或密碼錯誤');
  await expect(page.getByRole('heading', { name: '工作空間', exact: true })).toHaveCount(0);
});

test('登入後切換所屬租戶並登出', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('密碼').fill(password);
  await page.getByRole('button', { name: '登入', exact: true }).click();
  await expect(page.getByRole('heading', { name: '工作空間', exact: true })).toBeVisible();
  const tenants = page.getByLabel('選擇租戶');
  await expect(tenants.locator('option')).toHaveCount(3);
  await tenants.selectOption(tenantA);
  await expect(page.getByText('目前角色：staff')).toBeVisible();
  await expect(page.getByRole('heading', { name: '功能概覽' })).toBeVisible();
  await tenants.selectOption(tenantB);
  await expect(page.getByText('目前角色：viewer')).toBeVisible();
  await expect(tenants.locator(`option[value="${tenantC}"]`)).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('heading', { name: '工作空間', exact: true })).toBeVisible();
  await expect(page.getByText(email, { exact: true })).toBeVisible();
  await expect(tenants).toHaveValue(tenantB);
  await expect(page.getByText('目前角色：viewer')).toBeVisible();
  await expect(page.getByRole('heading', { name: '功能概覽' })).toBeVisible();
  await page.getByRole('button', { name: '登出' }).click();
  await expect(page.getByRole('heading', { name: '登入工作空間' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '功能概覽' })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('heading', { name: '登入工作空間' })).toBeVisible();
});

test('重新載入收到工作階段失效時才顯示登入畫面', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('密碼').fill(password);
  await page.getByRole('button', { name: '登入', exact: true }).click();
  await expect(page.getByRole('heading', { name: '工作空間', exact: true })).toBeVisible();
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 503 }));
  await page.reload();
  await expect(page.getByRole('button', { name: '重試' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '登入工作空間' })).toHaveCount(0);
  await page.unroute('**/api/v1/auth/me');
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 401 }));
  await page.getByRole('button', { name: '重試' }).click();
  await expect(page.getByRole('heading', { name: '登入工作空間' })).toBeVisible();
});

test('跨租戶要求由 API 拒絕', async ({ request }) => {
  const login = await request.post('/api/v1/auth/login', {
    data: { email: otherEmail, password },
  });
  expect(login.status()).toBe(200);
  const token: string = (await login.json()).access_token;
  const headers = { Authorization: `Bearer ${token}` };
  const tenants = await request.get('/api/v1/tenants', { headers });
  expect(tenants.status()).toBe(200);
  expect((await tenants.json()).items.map((item: { id: string }) => item.id)).toEqual([tenantB]);
  expect((await request.get(`/api/v1/tenants/${tenantA}`, { headers })).status()).toBe(404);
  expect((await request.get('/api/v1/tenants/current', {
    headers: { ...headers, 'X-Tenant-ID': tenantA },
  })).status()).toBe(404);
  expect((await request.get(`/api/v1/tenants/${tenantC}`, { headers })).status()).toBe(404);
  expect((await request.post('/api/v1/auth/logout', { headers })).status()).toBe(204);
  expect((await request.get('/api/v1/auth/me', { headers })).status()).toBe(401);
});
