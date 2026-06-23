import axios from 'axios';
import { mapApiError } from './error_handling';

const apiClient = axios.create({ baseURL: '/api' });

apiClient.interceptors.response.use(
  response => response,
  error => {
    const mappedError = mapApiError(error);
    console.error("API Error:", mappedError);
    return Promise.reject(mappedError);
  }
);

export default apiClient;
