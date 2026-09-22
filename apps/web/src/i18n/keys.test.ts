import { describe, expect, it } from 'vitest';

import en from './en.json';
import hi from './hi.json';

/**
 * Guard against raw keys on screen: every literal `t('a.b')` and `labelKey: 'a.b'` in the source must
 * resolve to a string in both languages. Keys built at runtime (`t(\`status.${x}\`)`) are not seen
 * here; their families are listed explicitly below.
 */
const sources = import.meta.glob<string>(['../**/*.{ts,tsx}', '!../**/*.test.{ts,tsx}'], {
  query: '?raw',
  import: 'default',
  eager: true,
});

const PATTERNS = [
  /\bt\(\s*(['"])([A-Za-z0-9_.]+)\1/g,
  // `t(cond ? 'a.b' : 'c.d')`
  /\bt\([^()'"]*\?\s*(['"])([A-Za-z0-9_.]+)\1/g,
  /\bt\([^()'"]*\?\s*['"][A-Za-z0-9_.]+['"]\s*:\s*(['"])([A-Za-z0-9_.]+)\1/g,
  /labelKey:\s*(['"])([A-Za-z0-9_.]+)\1/g,
];

/** Families addressed with template literals; each member must exist too. */
const RUNTIME_KEYS = [
  ...['oee', 'availability', 'performance', 'quality'].map((k) => `analytics.${k}`),
  ...['downtime_cost', 'failure_risk', 'energy_cost'].map((k) => `maintenance.weight.${k}`),
  ...['critical', 'serious', 'warning', 'info'].map((k) => `alarms.severity.${k}`),
  ...['active', 'acknowledged', 'shelved', 'cleared'].map((k) => `alarms.status.${k}`),
  ...['running', 'done', 'failed'].map((k) => `benchmarks.status.${k}`),
  ...['pass', 'fail', 'none'].map((k) => `benchmarks.verdict.${k}`),
  ...['anomaly', 'failure', 'rul', 'survival'].map((k) => `models.taskName.${k}`),
  ...['candidate', 'production', 'archived'].map((k) => `models.stageName.${k}`),
  ...['high', 'medium', 'low'].map((k) => `machine.confidence.${k}`),
  ...['good', 'warning', 'serious', 'critical', 'neutral'].map((k) => `status.level.${k}`),
  ...['denied', 'no-speech', 'no-microphone', 'failed'].map((k) => `voice.mic.error.${k}`),
  ...['deletion_auc', 'insertion_auc', 'pgi', 'sensitivity_max', 'sparsity', 'truth_top1_agreement', 'window_jaccard'].flatMap(
    (k) => [`explainQuality.metric.${k}.label`, `explainQuality.metric.${k}.help`],
  ),
  ...['higher', 'lower'].map((k) => `explainQuality.better.${k}`),
  ...['edge', 'server'].map((k) => `machine.timeline.source.${k}`),
  ...['synthetic', 'cmapss', 'ai4i'].flatMap((k) => [`models.train.sourceName.${k}`, `models.train.sourceHint.${k}`]),
];

function lookup(dict: unknown, key: string): unknown {
  return key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], dict);
}

function usedKeys(): Map<string, string> {
  const found = new Map<string, string>();
  for (const [file, source] of Object.entries(sources)) {
    for (const pattern of PATTERNS) {
      for (const match of source.matchAll(pattern)) if (!found.has(match[2])) found.set(match[2], file);
    }
  }
  return found;
}

describe('translation keys used in source', () => {
  const used = usedKeys();

  it('finds the source files and their keys', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(50);
    expect(used.has('nav.fleet')).toBe(true);
  });

  it.each([
    ['en', en],
    ['hi', hi],
  ])('are all defined in %s', (_lang, dict) => {
    const missing = [...used].filter(([key]) => typeof lookup(dict, key) !== 'string').map(([key, file]) => `${key} (${file})`);
    expect(missing).toEqual([]);
  });

  it.each([
    ['en', en],
    ['hi', hi],
  ])('include every runtime-built key in %s', (_lang, dict) => {
    expect(RUNTIME_KEYS.filter((key) => typeof lookup(dict, key) !== 'string')).toEqual([]);
  });
});
