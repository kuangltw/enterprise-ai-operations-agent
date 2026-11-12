import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const modules = [
  ['SOP 知識問答', 'RAG（檢索增強生成）與引用來源', '規劃中'],
  ['庫存與銷售分析', 'Agent + ERP Tool（工具）', '規劃中'],
  ['採購建議與人工核准', 'Approval（人工核准）與冪等寫入', '規劃中'],
  ['執行監控', 'Trace（追蹤）、Metrics（指標）', '規劃中'],
];

function App() {
  return <main>
    <header>
      <span className="eyebrow">M1 · 基礎骨架</span>
      <h1>Enterprise AI Operations Agent</h1>
      <p>企業 AI 營運代理系統</p>
      <p className="notice">目前為開發中的示範專案。以下四項業務功能尚未實作。</p>
    </header>
    <section className="cards" aria-label="MVP 功能">
      {modules.map(([title, description, status]) =>
        <article key={title}>
          <h2>{title}</h2>
          <p>{description}</p>
          <small>{status}</small>
        </article>
      )}
    </section>
    <footer>
      <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">FastAPI Swagger 文件</a>
      <a href="http://127.0.0.1:8080/health/ready" target="_blank" rel="noreferrer">Demo ERP 健康檢查</a>
    </footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>
);
