import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { User, getCurrentUser, setCurrentUser, removeCurrentUser, api, getAuthToken } from './api';

interface AuthContextType {
  user: User | null;
  setUser: (user: User | null) => void;
  logout: () => void;
  isAuthenticated: boolean;
  isLoading: boolean;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUserState] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      setIsLoading(true);
      const storedUser = getCurrentUser();
      if (storedUser) {
        setUserState(storedUser);
      }

      const token = getAuthToken();
      if (token && storedUser) {
        try {
          console.log("Fetching fresh user data...");
          console.log(storedUser);
          console.log("printing id", storedUser.userId);
          const fresh = await api.getUser(storedUser.userId);
          if (!cancelled) {
            setUserState(fresh);
            setCurrentUser(fresh);
          }
        } catch (_) {
        }
      }
      if (!cancelled) setIsLoading(false);
    };
    void init();
    return () => {
      cancelled = true;
    };
  }, []);

  const setUser = (newUser: User | null) => {
    setUserState(newUser);
    if (newUser) {
      setCurrentUser(newUser);
    } else {
      removeCurrentUser();
    }
  };

  const logout = () => {
    setUserState(null);
    removeCurrentUser();
  };

  const refreshUser = useCallback(async () => {
    const current = getCurrentUser();
    const token = getAuthToken();
    if (!current || !token) return;
    try {
      const fresh = await api.getUser(current.userId);
      setUserState(fresh);
      setCurrentUser(fresh);
    } catch (error) {
      console.error('Failed to refresh user:', error);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, setUser, logout, isAuthenticated: !!user, isLoading, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
