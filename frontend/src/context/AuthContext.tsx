'use client';

import React, { createContext, useState, useEffect, useContext } from 'react';
import { useRouter } from 'next/navigation';

interface User {
  id: number;
  email: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
  apiFetch: (url: string, options?: RequestInit) => Promise<Response>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const parseJwt = (token: string): any => {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    return JSON.parse(jsonPayload);
  } catch (e) {
    return null;
  }
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const router = useRouter();

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    const storedUser = localStorage.getItem('user');

    if (storedToken && storedUser) {
      const decoded = parseJwt(storedToken);
      if (decoded && decoded.exp * 1000 > Date.now()) {
        setToken(storedToken);
        setUser(JSON.parse(storedUser));
      } else {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        document.cookie = 'auth_token=; path=/; max-age=0';
        document.cookie = 'token=; path=/; max-age=0';
        document.cookie = 'role=; path=/; max-age=0';
      }
    }
    setIsLoading(false);
  }, []);

  const login = (newToken: string, newUser: User) => {
    setToken(newToken);
    setUser(newUser);
    localStorage.setItem('token', newToken);
    localStorage.setItem('user', JSON.stringify(newUser));
    
    // ミドルウェア（サーバーサイド）で判定できるようにCookieにもセット
    document.cookie = `auth_token=${newToken}; path=/; max-age=${60 * 60 * 24 * 7}; SameSite=Lax`;
    document.cookie = `role=${newUser.role}; path=/; max-age=${60 * 60 * 24 * 7}; SameSite=Lax`;
  };

  const logout = async () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    
    // Cookieもクリア
    document.cookie = 'auth_token=; path=/; max-age=0; path=/';
    document.cookie = 'token=; path=/; max-age=0; path=/';
    document.cookie = 'role=; path=/; max-age=0; path=/';
    document.cookie = 'site_session=; path=/; max-age=0; path=/';
    
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {
      console.error('Failed to logout via server api', e);
    }
    
    // router.push('/') を呼ぶ前に、画面を強制的にリロードしてミドルウェア判定を走らせる
    window.location.href = '/';
  };

  const apiFetch = async (url: string, options: RequestInit = {}) => {
    const headers = new Headers(options.headers || {});
    
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }

    if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json');
    }

    const response = await fetch(url, {
      ...options,
      credentials: 'include',
      headers
    });

    if (response.status === 401) {
      alert('セッションの期限が切れました。再度ログインしてください。');
      logout();
    }

    if (response.status === 403) {
      const data = await response.clone().json().catch(() => ({}));
      if (data.detail && data.detail.includes('BAN')) {
        alert('アカウントが利用停止されたため、ログアウトします。');
        logout();
      }
    }

    return response;
  };

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout, apiFetch }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
export default AuthProvider;
