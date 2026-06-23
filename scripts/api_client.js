import axios from 'axios';
import { mapApiError } from './error_handling';

const isProd = import.meta?.env?.PROD ?? process.env.NODE_ENV === 'production';

const apiClient = axios.create({ baseURL: '/api' });

apiClient.interceptors.response.use(
  response => response,
  error => {
    const mappedError = mapApiError(error);
    // Preserve the HTTP status code so callers can branch on it.
    mappedError.status = error.response?.status;
    // In development, log to the console so errors are visible.
    // In production, a real telemetry sink (Sentry, Datadog, etc.) should
    // be wired in instead.  Do NOT log the full error object — it may
    // contain PII, tokens, or server internals.
    if (!isProd) {
      console.error(`[API Error] status=${error.response?.status} code=${mappedError.title}`);
    }
    return Promise.reject(mappedError);
  }
);

export default apiClient;
