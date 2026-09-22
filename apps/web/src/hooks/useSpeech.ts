import { useCallback, useEffect, useRef, useState } from 'react';

import { useUiStore, type Language } from '../store/uiStore';

/** Indian locales for both languages: en-IN reads plant names and numbers the way operators say them. */
export const SPEECH_LOCALE: Record<Language, string> = { en: 'en-IN', hi: 'hi-IN' };

function synthesis(): SpeechSynthesis | undefined {
  return typeof window !== 'undefined' && 'speechSynthesis' in window && typeof SpeechSynthesisUtterance === 'function'
    ? window.speechSynthesis
    : undefined;
}

function recognitionConstructor(): SpeechRecognitionConstructor | undefined {
  return typeof window === 'undefined' ? undefined : (window.SpeechRecognition ?? window.webkitSpeechRecognition);
}

/** Recognition errors worth telling the operator about; anything else reads as a generic failure. */
export type RecognitionError = 'denied' | 'no-speech' | 'no-microphone' | 'failed';

const RECOGNITION_ERRORS: Record<string, RecognitionError> = {
  'not-allowed': 'denied',
  'service-not-allowed': 'denied',
  'no-speech': 'no-speech',
  'audio-capture': 'no-microphone',
};

/**
 * Spoken answers through the browser's own voices (FR-VN-08). `speaking` is the key of the text being
 * read, so several speak buttons can share one hook and each knows whether it is the one talking.
 * There is one speech queue per page: starting a new utterance cancels whatever else was reading.
 */
export function useSpeechSynthesis() {
  const language = useUiStore((s) => s.language);
  const [speaking, setSpeaking] = useState<string | null>(null);
  const current = useRef<SpeechSynthesisUtterance | null>(null);

  const stop = useCallback(() => {
    if (!current.current) return;
    current.current = null;
    setSpeaking(null);
    synthesis()?.cancel();
  }, []);

  const speak = useCallback(
    (text: string, key: string = text) => {
      const engine = synthesis();
      if (!engine || !text.trim()) return;
      engine.cancel();

      const locale = SPEECH_LOCALE[language];
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = locale;
      // Without an explicit voice some browsers read Hindi with an English voice.
      const voices = engine.getVoices();
      utterance.voice =
        voices.find((v) => v.lang.replace('_', '-') === locale) ??
        voices.find((v) => v.lang.startsWith(language)) ??
        null;

      // A cancelled utterance still fires `end`/`error`; only the live one may clear the state.
      const done = () => {
        if (current.current !== utterance) return;
        current.current = null;
        setSpeaking(null);
      };
      utterance.onend = done;
      utterance.onerror = done;

      current.current = utterance;
      setSpeaking(key);
      engine.speak(utterance);
    },
    [language],
  );

  // Leaving the view must not leave the browser talking about it.
  useEffect(
    () => () => {
      if (current.current) synthesis()?.cancel();
    },
    [],
  );

  return { supported: Boolean(synthesis()), speaking, speak, stop };
}

/**
 * Push-to-talk through the Web Speech API: one utterance per `start`, interim words while it listens
 * and the final transcript handed to `onFinal` once recognition ends — so stopping early still
 * submits what was heard. The recognition language follows the app language.
 */
export function useSpeechRecognition(onFinal: (transcript: string, confidence: number) => void) {
  const language = useUiStore((s) => s.language);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [error, setError] = useState<RecognitionError | null>(null);
  const recognition = useRef<SpeechRecognition | null>(null);
  const onFinalRef = useRef(onFinal);

  useEffect(() => {
    onFinalRef.current = onFinal;
  });

  const start = useCallback(() => {
    const Recognition = recognitionConstructor();
    if (!Recognition || recognition.current) return;

    const session = new Recognition();
    session.lang = SPEECH_LOCALE[language];
    session.interimResults = true;
    session.continuous = false;
    session.maxAlternatives = 1;

    let final = '';
    let confidence = 0;
    session.onresult = (event) => {
      // `results` holds the whole utterance so far; rebuild rather than append to avoid repeats.
      let heard = '';
      let pending = '';
      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i];
        const best = result[0];
        if (result.isFinal) {
          heard += best.transcript;
          confidence = best.confidence;
        } else {
          pending += best.transcript;
        }
      }
      final = heard;
      setInterim(`${heard}${pending}`.trim());
    };
    session.onerror = (event) => {
      if (event.error !== 'aborted') setError(RECOGNITION_ERRORS[event.error] ?? 'failed');
    };
    session.onend = () => {
      recognition.current = null;
      setListening(false);
      setInterim('');
      const transcript = final.trim();
      if (transcript) onFinalRef.current(transcript, confidence);
    };

    recognition.current = session;
    setError(null);
    setInterim('');
    try {
      session.start();
      setListening(true);
    } catch {
      recognition.current = null;
      setError('failed');
    }
  }, [language]);

  const stop = useCallback(() => recognition.current?.stop(), []);

  // Unmounting mid-utterance drops it: nothing is left to show the answer to.
  useEffect(
    () => () => {
      const session = recognition.current;
      if (!session) return;
      session.onend = null;
      session.onresult = null;
      session.onerror = null;
      session.abort();
    },
    [],
  );

  return { supported: Boolean(recognitionConstructor()), listening, interim, error, start, stop };
}
