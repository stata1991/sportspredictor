// src/api.ts
import axios from "axios";

const api = axios.create({
  baseURL: "http://127.0.0.1:8000", // backend URL
});

// ── ETag cache: stores etag + last response per URL ──
const etagCache: Record<string, { etag: string; data: unknown }> = {};

api.interceptors.request.use((config) => {
  const key = `${config.method}:${config.url}:${JSON.stringify(config.params ?? {})}`;
  const cached = etagCache[key];
  if (cached) {
    config.headers = config.headers ?? {};
    config.headers["If-None-Match"] = cached.etag;
  }
  return config;
});

api.interceptors.response.use(
  (response) => {
    const etag = response.headers["etag"];
    if (etag) {
      const key = `${response.config.method}:${response.config.url}:${JSON.stringify(response.config.params ?? {})}`;
      etagCache[key] = { etag, data: response.data };
    }
    return response;
  },
  (error) => {
    if (error.response?.status === 304) {
      const cfg = error.config;
      const key = `${cfg.method}:${cfg.url}:${JSON.stringify(cfg.params ?? {})}`;
      const cached = etagCache[key];
      if (cached) {
        return { ...error.response, status: 200, data: cached.data };
      }
    }
    return Promise.reject(error);
  }
);

export default api;
