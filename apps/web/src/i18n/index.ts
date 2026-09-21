import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import { setFormatLocale } from '../lib/format';
import { useUiStore } from '../store/uiStore';
import en from './en.json';
import hi from './hi.json';

const language = useUiStore.getState().language;

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, hi: { translation: hi } },
  lng: language,
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

function applyLanguage(lng: string) {
  setFormatLocale(lng);
  document.documentElement.lang = lng;
}

applyLanguage(language);
i18n.on('languageChanged', applyLanguage);

export default i18n;
