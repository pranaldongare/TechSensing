import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import type { UserProfile } from '@/lib/api';

interface ProfileContextType {
  profiles: UserProfile[];
  activeProfileId: string;
  activeProfile: UserProfile | undefined;
  setActiveProfileId: (id: string) => void;
  refresh: () => Promise<void>;
}

const ProfileContext = createContext<ProfileContextType | undefined>(undefined);

export const ProfileProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [profiles, setProfiles] = useState<UserProfile[]>([]);
  const [activeProfileId, setActiveProfileIdState] = useState<string>(
    () => localStorage.getItem('activeProfileId') || 'default',
  );

  const setActiveProfileId = useCallback((id: string) => {
    setActiveProfileIdState(id);
    localStorage.setItem('activeProfileId', id);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const res = await api.sensingListProfiles();
      const list = res.profiles || [];
      setProfiles(list);
      const ids = list.map((p) => p.id);
      if (ids.length && !ids.includes(activeProfileId)) {
        setActiveProfileId(ids.includes('default') ? 'default' : ids[0]);
      }
    } catch {
      /* not authenticated yet, or backend down — ignore */
    }
  }, [activeProfileId, setActiveProfileId]);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const activeProfile = profiles.find((p) => p.id === activeProfileId);

  return (
    <ProfileContext.Provider
      value={{ profiles, activeProfileId, activeProfile, setActiveProfileId, refresh }}
    >
      {children}
    </ProfileContext.Provider>
  );
};

export const useProfile = (): ProfileContextType => {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error('useProfile must be used within ProfileProvider');
  return ctx;
};
