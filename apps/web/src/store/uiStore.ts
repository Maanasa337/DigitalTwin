import { create } from 'zustand';
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware';

export type ThemeMode = 'dark' | 'light';
export type Language = 'en' | 'hi';

interface UiState {
  themeMode: ThemeMode;
  navCollapsed: boolean;
  language: Language;
  toggleTheme: () => void;
  toggleNav: () => void;
  setLanguage: (language: Language) => void;
}

const safeLocalStorage: StateStorage = {
  getItem: (name) => {
    try {
      return window.localStorage.getItem(name);
    } catch {
      return null;
    }
  },
  setItem: (name, value) => {
    try {
      window.localStorage.setItem(name, value);
    } catch {
      /* storage unavailable: keep in memory only */
    }
  },
  removeItem: (name) => {
    try {
      window.localStorage.removeItem(name);
    } catch {
      /* storage unavailable */
    }
  },
};

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      themeMode: 'dark',
      navCollapsed: false,
      language: 'en',
      toggleTheme: () => set((s) => ({ themeMode: s.themeMode === 'dark' ? 'light' : 'dark' })),
      toggleNav: () => set((s) => ({ navCollapsed: !s.navCollapsed })),
      setLanguage: (language) => set({ language }),
    }),
    {
      name: 'twinvoice.ui',
      storage: createJSONStorage(() => safeLocalStorage),
      partialize: ({ themeMode, navCollapsed, language }) => ({ themeMode, navCollapsed, language }),
    },
  ),
);
