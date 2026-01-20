import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiService } from '@/services/api';
import { Header } from '@/components/layout/Header';
import './DocList.css';

interface SharedDoc {
  doc_id: string;
  title: string;
  from_user: string;
  shared_at: string;
}

export function SharedDocs() {
  const [docs, setDocs] = useState<SharedDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    loadDocs();
  }, []);

  const loadDocs = async () => {
    try {
      const res = await apiService.docs.cc();
      setDocs(res.data.docs);
    } catch (err) {
      console.error('加载抄送文档失败', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (docId: string) => {
    if (!confirm('确定删除该抄送记录？（仅对你隐藏，不影响抄送方）')) return;
    try {
      await apiService.docs.deleteCc(docId);
      await loadDocs();
    } catch (err) {
      console.error('删除抄送失败', err);
      alert('删除失败，请稍后重试');
    }
  };

  return (
    <div className="doc-list-page">
      <Header />
      <main className="doc-list-main">
        <div className="doc-list-header">
          <h2>抄送给我的</h2>
        </div>

        {loading ? (
          <div className="doc-list-loading">加载中...</div>
        ) : docs.length === 0 ? (
          <div className="doc-list-empty">
            <p>暂无抄送文档</p>
            <p className="doc-list-hint">其他用户分享给你的文档会显示在这里</p>
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
                  <span className="doc-from">来自 {doc.from_user}</span>
                  <span className="doc-time">{new Date(doc.shared_at).toLocaleString('zh-CN')}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
