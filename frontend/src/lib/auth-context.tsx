import React, { createContext, useContext } from 'react';
import type { User } from './api';

interface AuthContextType {
  user: User;
  isLoading: boolean;
}

const defaultUser: User = {
  userId: 'default_user',
  name: 'Default User',
  email: 'user@techsensing.com',
};

const AuthContext = createContext<AuthContextType>({
  user: defaultUser,
  isLoading: false,
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <AuthContext.Provider value={{ user: defaultUser, isLoading: false }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
