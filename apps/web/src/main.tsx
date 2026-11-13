import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ApiError, getCurrentTenant, getMe, getTenants, login, logout, type CurrentTenant, type Tenant, type User } from './api';
import './style.css';

const modules = [
  ['SOP 知識問答', 'RAG（檢索增強生成）與引用來源'],
  ['庫存與銷售分析', 'Agent + ERP Tool（工具）'],
  ['採購建議與人工核准', 'Approval（人工核准）與冪等寫入'],
  ['執行監控', 'Trace（追蹤）、Metrics（指標）'],
];

// 僅保存分頁的租戶選擇；恢復時仍須由後端核對目前成員資格。
function tenantPreference(userId: string, tenantId?: string): string | null {
  const key = `workspace.tenant.${userId}`;
  try {
    if (tenantId === undefined) return sessionStorage.getItem(key);
    if (tenantId) sessionStorage.setItem(key, tenantId);
    else sessionStorage.removeItem(key);
  } catch { /* 瀏覽器限制儲存時仍可登入及切換租戶。 */ }
  return null;
}

async function restoreWorkspace() {
  const user = await getMe();
  const tenants = await getTenants();
  const tenantId = tenantPreference(user.id);
  let selected = null;
  if (tenantId && tenants.some(tenant => tenant.id === tenantId)) {
    try { selected = await getCurrentTenant(tenantId); }
    catch (cause) {
      // 成員資格可能在列表與目前租戶請求之間變更。
      if (!(cause instanceof ApiError) || ![403, 404].includes(cause.status)) throw cause;
    }
  }
  if (tenantId && !selected) tenantPreference(user.id, '');
  return { user, tenants, selected };
}

function App() {
  const [restoring, setRestoring] = useState(true);
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const [user, setUser] = useState<User | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selected, setSelected] = useState<CurrentTenant | null>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    restoreWorkspace().then(workspace => {
      if (!active) return;
      setUser(workspace.user);
      setTenants(workspace.tenants);
      setSelected(workspace.selected);
      setRestoring(false);
    }).catch(cause => {
      if (!active) return;
      if (cause instanceof ApiError && cause.status === 401) setRestoring(false);
      else setError(cause instanceof Error ? cause.message : '無法恢復工作階段。');
    });
    return () => { active = false; };
  }, [restoreAttempt]);

  function clearSession() {
    if (user) tenantPreference(user.id, '');
    setUser(null); setTenants([]); setSelected(null); setPassword('');
  }

  function retryRestore() {
    setError('');
    setRestoring(true);
    setRestoreAttempt(attempt => attempt + 1);
  }

  function showError(cause: unknown) {
    if (cause instanceof ApiError && cause.status === 401) clearSession();
    setError(cause instanceof Error ? cause.message : '發生未預期錯誤。');
  }

  async function submitLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      await login(email.trim(), password);
      setPassword('');
      retryRestore();
    } catch (cause) { showError(cause); }
    finally { setBusy(false); }
  }

  async function selectTenant(id: string) {
    setSelected(null); setError('');
    if (!user) return;
    tenantPreference(user.id, '');
    if (!id) return;
    setBusy(true);
    try {
      setSelected(await getCurrentTenant(id));
      tenantPreference(user.id, id);
    }
    catch (cause) { showError(cause); }
    finally { setBusy(false); }
  }

  async function submitLogout() {
    setBusy(true); setError('');
    try {
      await logout();
      clearSession();
    }
    catch (cause) { showError(cause); }
    finally { setBusy(false); }
  }

  return <main>
    <header className="masthead">
      <span className="eyebrow">M1 · 身分與授權基礎</span>
      <h1>Enterprise AI Operations Agent</h1>
      <p>企業 AI 營運代理系統</p>
    </header>

    {restoring ? <section className="panel" aria-label="工作階段">
      {error ? <button type="button" onClick={retryRestore}>重試</button>
        : <p role="status">正在確認工作階段…</p>}
    </section> : !user ? <section className="panel login-panel" aria-labelledby="login-title">
      <div><p className="eyebrow">安全登入</p><h2 id="login-title">登入工作空間</h2>
        <p className="muted">使用管理員建立的帳號登入。</p></div>
      <form onSubmit={submitLogin}>
        <label htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="username" value={email}
          onChange={event => setEmail(event.target.value)} required maxLength={255} />
        <label htmlFor="password">密碼</label>
        <input id="password" type="password" autoComplete="current-password" value={password}
          onChange={event => setPassword(event.target.value)} required />
        <button disabled={busy} type="submit">{busy ? '登入中…' : '登入'}</button>
      </form>
    </section> : <section className="panel workspace" aria-labelledby="workspace-title">
      <div className="workspace-top"><div><p className="eyebrow">已驗證身分</p>
        <h2 id="workspace-title">工作空間</h2><p className="muted">{user?.email}</p></div>
        <button className="secondary" disabled={busy} onClick={submitLogout}>登出</button></div>
      <label htmlFor="tenant">選擇租戶</label>
      <select id="tenant" disabled={busy} value={selected?.id || ''}
        onChange={event => void selectTenant(event.target.value)}>
        <option value="">請選擇租戶</option>
        {tenants.map(tenant => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)}
      </select>
      {tenants.length === 0 && <p className="muted">目前沒有可存取的啟用租戶。</p>}
      {selected ? <div className="tenant-summary"><span className="status-dot" aria-hidden="true" />
        <div><strong>{selected.name}</strong><p>目前角色：{selected.role}</p></div></div>
        : <p className="muted">選擇租戶後，才會顯示受保護的工作區內容。</p>}
    </section>}

    {error && <p className="error" role="alert">{error}</p>}
    {selected && user && <section className="features" aria-label="功能狀態">
      <div className="section-heading"><h2>功能概覽</h2><span>規劃中</span></div>
      <div className="cards">{modules.map(([title, description]) =>
        <article key={title}><h3>{title}</h3><p>{description}</p><small>尚未實作</small></article>
      )}</div>
    </section>}
    <footer><a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">FastAPI Swagger 文件</a></footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
