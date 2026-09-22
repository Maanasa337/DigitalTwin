import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { useUiStore, type Language } from '../store/uiStore';

/**
 * Switch the app language. The store persists the choice and drives the voice `lang`; i18next
 * re-renders the copy — both have to move together, so every switcher goes through here.
 */
export function useChangeLanguage() {
  const { i18n } = useTranslation();
  const setLanguage = useUiStore((s) => s.setLanguage);

  return useCallback(
    (value: Language) => {
      setLanguage(value);
      void i18n.changeLanguage(value);
    },
    [i18n, setLanguage],
  );
}
