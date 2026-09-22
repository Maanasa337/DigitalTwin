import { Table, Typography } from 'antd';
import type { ReactNode } from 'react';

/**
 * Renders the small Markdown subset our generated reports use (headings, paragraphs, bullet lists,
 * pipe tables, `**bold**`, `` `code` ``) as React elements. Nothing is ever injected as HTML, so an
 * untrusted string cannot run script; anything unrecognised is shown as plain text.
 */
export function MiniMarkdown({ source }: { source: string }) {
  return <>{parseBlocks(source)}</>;
}

function inline(text: string, key: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4)
      return <strong key={`${key}-${i}`}>{part.slice(2, -2)}</strong>;
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2)
      return <Typography.Text key={`${key}-${i}`} code>{part.slice(1, -1)}</Typography.Text>;
    return part;
  });
}

const cells = (row: string) =>
  row
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((c) => c.trim());

export function parseBlocks(source: string): ReactNode[] {
  const lines = source.replace(/\r\n/g, '\n').split('\n');
  const out: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = `b${i}`;
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (!line.trim()) {
      i += 1;
    } else if (heading) {
      const level = Math.min(heading[1].length + 1, 5) as 2 | 3 | 4 | 5;
      out.push(
        <Typography.Title key={key} level={level} style={{ marginTop: 16 }}>
          {inline(heading[2], key)}
        </Typography.Title>,
      );
      i += 1;
    } else if (line.trim().startsWith('|')) {
      const rows: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(lines[(i += 1) - 1]);
      const [head, ...body] = rows.filter((r) => !/^\s*\|?\s*:?-{2,}/.test(r));
      const columns = cells(head ?? '').map((title, c) => ({
        key: String(c),
        dataIndex: String(c),
        title: inline(title, `${key}h${c}`),
        render: (v: string) => inline(v ?? '', `${key}c${c}`),
      }));
      const data = body.map((r, n) => ({ key: n, ...Object.fromEntries(cells(r).map((v, c) => [String(c), v])) }));
      out.push(
        <Table key={key} size="small" columns={columns} dataSource={data} pagination={false} style={{ marginBottom: 16 }} />,
      );
    } else if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[(i += 1) - 1].replace(/^\s*[-*]\s+/, ''));
      out.push(
        <ul key={key}>
          {items.map((item, n) => (
            <li key={n}>{inline(item, `${key}l${n}`)}</li>
          ))}
        </ul>,
      );
    } else {
      const para: string[] = [];
      while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|\s*\||\s*[-*]\s)/.test(lines[i]))
        para.push(lines[(i += 1) - 1]);
      out.push(<Typography.Paragraph key={key}>{inline(para.join(' '), key)}</Typography.Paragraph>);
    }
  }
  return out;
}
