import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiService } from '@/services/api';
import { Header } from '@/components/layout/Header';
import type { Document } from '@/types';
import './DocList.css';

export function MyDocs() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    loadDocs();
  }, []);

  const loadDocs = async () => {
    try {
      const res = await apiService.docs.my();
      setDocs(res.data.docs);
    } catch (err) {
      console.error('加载文档失败', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    try {
      const res = await apiService.docs.create();
      navigate(`/doc/${res.data.doc_id}`);
    } catch (err) {
      console.error('创建文档失败', err);
    }
  };

  const handleDelete = async (docId: string) => {
    if (!confirm('确定删除该文档？（仅从“我的文档”隐藏，不影响已抄送者）')) return;
    try {
      await apiService.docs.delete(docId);
      await loadDocs();
    } catch (err) {
      console.error('删除文档失败', err);
      alert('删除失败，请稍后重试');
    }
  };

  return (
    <div className="doc-list-page">
      <Header />
      <main className="doc-list-main">
        <div className="doc-list-header">
          <h2>我的文档</h2>
          <button className="btn btn-primary" onClick={handleCreate}>
            + 新建文档
          </button>
        </div>

        {loading ? (
          <div className="doc-list-loading">加载中...</div>
        ) : docs.length === 0 ? (
          <div className="doc-list-empty">
            <p>还没有文档</p>
            <button className="btn btn-primary" onClick={handleCreate}>
              创建第一个文档
            </button>
          </div>
        ) : (
          <div className="doc-list">
            {docs.map((doc) => (
              <div
                key={doc.doc_id}
                className="doc-item card"
                onClick={() => navigate(`/doc/${doc.doc_id}`)}
              >
                <button
                  className="doc-item-delete"
                  title="删除"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(doc.doc_id);
                  }}
                >
                  ×
                </button>
                <div className="doc-item-title">{doc.title}</div>
                <div className="doc-item-meta">
                  <span className={`doc-status status-${doc.status}`}>{doc.status}</span>
                  <span className="doc-time">{new Date(doc.updated_at).toLocaleString('zh-CN')}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
