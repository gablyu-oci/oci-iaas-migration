import { useMutation } from '@tanstack/react-query';
import client from '../client';

interface AuthPayload {
  email: string;
  password: string;
}

interface AuthResponse {
  access_token: string;
}

export function useRegister() {
  return useMutation({
    mutationFn: (data: AuthPayload) =>
      client.post<AuthResponse>('/api/auth/register', data).then((r) => r.data),
    onSuccess: (data) => {
      localStorage.setItem('token', data.access_token);
    },
  });
}

export function useLogin() {
  return useMutation({
    mutationFn: (data: AuthPayload) =>
      client.post<AuthResponse>('/api/auth/login', data).then((r) => r.data),
    onSuccess: (data) => {
      localStorage.setItem('token', data.access_token);
    },
  });
}
