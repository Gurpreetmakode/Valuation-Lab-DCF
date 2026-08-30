import type { WatchlistEntry } from './types';

const STORAGE_KEY = 'intrinsic:watchlist';

export function loadWatchlist(): WatchlistEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveWatchlist(entries: WatchlistEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // localStorage unavailable (private browsing, etc.), fail silently
  }
}

export function upsertWatchlistEntry(entries: WatchlistEntry[], entry: WatchlistEntry): WatchlistEntry[] {
  const withoutExisting = entries.filter((e) => e.ticker !== entry.ticker);
  return [...withoutExisting, entry];
}

export function removeWatchlistEntry(entries: WatchlistEntry[], ticker: string): WatchlistEntry[] {
  return entries.filter((e) => e.ticker !== ticker);
}
