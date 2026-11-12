import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ApiError, getCurrentTenant, getMe, getTenants, login, logout, type Tenant, type User } from './api';
import './style.css';

const modules = [
  ['SOP 知識問答', 'RAG（檢索增強生成）與引用來源'],
  ['庫存與銷售分析', 'Agent + ERP Tool（工具）'],
  ['採購建議與人工核准', 'Approval（人工核准）與冪等寫入'],
  ['執行監控', 'Trace（追蹤）、Metrics（指標）'],
];

function App() {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selected, setSelected] = useState<Tenant | null>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  function clearSession() {
    setToken(null); setUser(null); setTenants([]); setSelected(null); setPassword('');
  }

  function showError(cause: unknown) {
    if (cause instanceof ApiError && cause.status === 401) clearSession();
    setError(cause instanceof Error ? cause.message : '發生未預期錯誤。');
  }

  async function submitLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const accessToken = await login(email.trim(), password);
      const [currentUser, available] = await Promise.all([getMe(accessToken), getTenants(accessToken)]);
      setToken(accessToken); setUser(currentUser); setTenants(available); setPassword('');
    } catch (cause) { showError(cause); }
    finally { setBusy(false); }
  }

  async function selectTenant(id: string) {
    setSelected(null); setError('');
    if (!token || !id) return;
    setBusy(true);
    try { setSelected(await getCurrentTenant(token, id)); }
    catch (cause) { showError(cause); }
    finally { setBusy(false); }
  }

  async function submitLogout() {
    setBusy(true); setError('');
    try { if (token) await logout(token); }
    catch (cause) { showError(cause); }
    finally { clearSession(); setBusy(false); }
  }

  return <main>
    <header className="masthead">
      <span className="eyebrow">M1 · 身分與授權基礎</span>
      <h1>Enterprise AI Operations Agent</h1>
      <p>企業 AI 營運代理系統</p>
    </header>

    {!token ? <section className="panel login-panel" aria-labelledby="login-title">
      <div><p className="eyebrow">安全登入</p><h2 id="login-title">登入工作空間</h2>
        <p className="muted">使用管理員建立的帳號登入。登入憑證只保留在目前頁面記憶體中。</p></div>
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
    {selected && token && <section className="features" aria-label="功能狀態">
      <div className="section-heading"><h2>功能概覽</h2><span>規劃中</span></div>
      <div className="cards">{modules.map(([title, description]) =>
        <article key={title}><h3>{title}</h3><p>{description}</p><small>尚未實作</small></article>
      )}</div>
    </section>}
    <footer><a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">FastAPI Swagger 文件</a></footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
