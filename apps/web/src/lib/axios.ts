import axios from 'axios';

import { getAccessToken, login } from './auth';

export const http = axios.create({ baseURL: '/api/v1' });

http.interceptors.request.use(async (config) => {
  const token = await getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

http.interceptors.response.use(undefined, (error: unknown) => {
  if (axios.isAxiosError(error) && error.response?.status === 401) login();
  return Promise.reject(error);
});
