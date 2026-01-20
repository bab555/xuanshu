import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';

// 创建 axios 实例
export const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器：添加 token
api.interceptors.request.use((config) => {
  const authStorage = localStorage.getItem('auth-storage');
  if (authStorage) {
    try {
      const { state } = JSON.parse(authStorage);
      if (state?.token) {
        config.headers.Authorization = `Bearer ${state.token}`;
      }
    } catch {
      // 忽略解析错误
    }
  }
  return config;
});

// 响应拦截器：处理错误
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // 清除 token 并跳转登录
      localStorage.removeItem('auth-storage');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// API 方法封装
export const apiService = {
  // 认证
  auth: {
    login: (data: { username: string; password: string }) =>
      api.post<{ user_id: string; username: string; token: string }>('/auth/login', data),
    register: (data: { username: string; password: string }) =>
      api.post<{ user_id: string; username: string; token: string }>('/auth/register', data),
  },

  // 文档
  docs: {
    my: () =>
      api.get<{ docs: Array<{ doc_id: string; title: string; status: string; updated_at: string }> }>(
        '/docs/my'
      ),
    cc: () =>
      api.get<{ docs: Array<{ doc_id: string; title: string; from_user: string; shared_at: string }> }>(
        '/docs/cc'
      ),
    create: (title?: string) => api.post<{ doc_id: string }>('/docs', { title }),
    get: (id: string) => api.get(`/docs/${id}`),
    update: (id: string, data: { title?: string; content_md?: string; doc_variables?: Record<string, any> }) =>
      api.put(`/docs/${id}`, data),
    share: (id: string, toUsername: string, note?: string) =>
      api.post<{ share_id: string }>(`/docs/${id}/share`, { to_username: toUsername, note }),
    delete: (id: string) => api.delete<{ ok: boolean }>(`/docs/${id}`),
    deleteCc: (id: string) => api.delete<{ ok: boolean }>(`/docs/${id}/cc`),
  },

  // 用户（抄送下拉）
  users: {
    list: () => api.get<{ users: Array<{ user_id: string; username: string }> }>('/users'),
  },

  // 工作流
  workflow: {
    run: (docId: string, data: { user_message?: string; attachments?: string[] }) =>
      api.post<{ run_id: string; status: string }>(`/workflow/docs/${docId}/run`, data),
    chat: (docId: string, data: { user_message: string; attachments?: string[] }) =>
      api.post<{ run_id: string; status: string; message: string }>(`/workflow/docs/${docId}/chat`, data),
    execute: (docId: string) =>
      api.post<{ run_id: string; status: string }>(`/workflow/docs/${docId}/execute`),
    status: (runId: string) => api.get(`/workflow/runs/${runId}`),
    // WebSocket 连接
    stream: (runId: string): WebSocket => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      return new WebSocket(`${protocol}//${host}${API_BASE}/workflow/runs/${runId}/stream`);
    },
  },

  // 附件
  attachments: {
    upload: async (docId: string, file: File) => {
      const form = new FormData();
      form.append('file', file);
      form.append('doc_id', docId);
      return api.post('/attachments', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
    },
    get: (attachmentId: string) => api.get(`/attachments/${attachmentId}`),
    list: (docId: string) => api.get(`/attachments/doc/${docId}`),
  },

  // 导出
  exports: {
    // 同步导出（直接下载）
    download: (docId: string) =>
      api.post(`/exports/${docId}`, {}, {
        responseType: 'blob',
        timeout: 120000,
      }),
    // 异步导出
    create: (docId: string) =>
      api.post<{ export_id: string; status: string }>(`/exports/docs/${docId}/docx`),
    status: (exportId: string) => api.get(`/exports/${exportId}`),
    downloadById: (exportId: string) =>
      api.get(`/exports/${exportId}/download`, { responseType: 'blob' }),
  },
};

export default api;
