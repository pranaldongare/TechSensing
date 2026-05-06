import { useState } from 'react';

interface StickyEntry<T> {
  data: T;
  fetchedAt: string;
}

function readSticky<T>(key: string): StickyEntry<T> | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StickyEntry<T>;
    if (parsed && 'data' in parsed) return parsed;
    return null;
  } catch {
    return null;
  }
}

/**
 * Persists state in localStorage so it survives navigation, tab switches, and
 * page reloads. Use this for top-bar tab data that's expensive to refetch
 * (e.g., model releases, AI leaderboard) so users see the last-fetched data
 * immediately on revisit and only fetch on demand or first run.
 *
 * Hydration is synchronous (in the useState initializer), so on the very
 * first render `value` already reflects the stored entry — callers can
 * branch on `value === null` to mean "no cache, first run".
 *
 * Returns [value, setValue, fetchedAt, clear].
 */
export function useStickyState<T>(
  key: string,
): [T | null, (next: T) => void, string | null, () => void] {
  const [entry, setEntry] = useState<StickyEntry<T> | null>(() => readSticky<T>(key));

  const setValue = (next: T) => {
    const now = new Date().toISOString();
    const newEntry: StickyEntry<T> = { data: next, fetchedAt: now };
    setEntry(newEntry);
    try {
      localStorage.setItem(key, JSON.stringify(newEntry));
    } catch {
      // Quota exceeded or storage disabled — accept in-memory state only.
    }
  };

  const clear = () => {
    setEntry(null);
    try {
      localStorage.removeItem(key);
    } catch {
      // Ignore.
    }
  };

  return [entry?.data ?? null, setValue, entry?.fetchedAt ?? null, clear];
}
