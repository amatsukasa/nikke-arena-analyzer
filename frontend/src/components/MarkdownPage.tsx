import fs from 'node:fs/promises';
import path from 'node:path';
import type { ReactNode } from 'react';

type FrontMatter = {
  title: string;
  description?: string;
  updatedAt?: string;
};

type MarkdownPageProps = {
  fileName: 'about.md' | 'contact.md' | 'guide.md' | 'links.md' | 'updates.md';
};

type Block =
  | { type: 'heading'; level: number; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'quote'; text: string }
  | { type: 'code'; language?: string; text: string }
  | { type: 'hr' };

function parseFrontMatter(source: string): { data: FrontMatter; body: string } {
  const normalized = source.replace(/\r\n/g, '\n');
  if (!normalized.startsWith('---\n')) {
    return { data: { title: 'ページ' }, body: normalized };
  }

  const end = normalized.indexOf('\n---\n', 4);
  if (end === -1) return { data: { title: 'ページ' }, body: normalized };

  const entries = normalized.slice(4, end).split('\n');
  const values: Record<string, string> = {};
  for (const entry of entries) {
    const separator = entry.indexOf(':');
    if (separator === -1) continue;
    const key = entry.slice(0, separator).trim();
    const value = entry.slice(separator + 1).trim().replace(/^['"]|['"]$/g, '');
    if (key) values[key] = value;
  }

  return {
    data: {
      title: values.title || 'ページ',
      description: values.description || undefined,
      updatedAt: values.updatedAt || undefined,
    },
    body: normalized.slice(end + 5).trim(),
  };
}

function parseBlocks(markdown: string): Block[] {
  const lines = markdown.split('\n');
  const blocks: Block[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.match(/^```\s*([\w-]+)?\s*$/);
    if (fence) {
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !/^```\s*$/.test(lines[index])) {
        code.push(lines[index]);
        index += 1;
      }
      index += index < lines.length ? 1 : 0;
      blocks.push({ type: 'code', language: fence[1], text: code.join('\n') });
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2] });
      index += 1;
      continue;
    }

    if (/^(?:---+|\*\*\*+)\s*$/.test(line)) {
      blocks.push({ type: 'hr' });
      index += 1;
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^>\s?/, ''));
        index += 1;
      }
      blocks.push({ type: 'quote', text: quote.join(' ') });
      continue;
    }

    const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      const isOrdered = Boolean(ordered);
      const items: string[] = [];
      const pattern = isOrdered ? /^\s*\d+[.)]\s+(.+)$/ : /^\s*[-*+]\s+(.+)$/;
      while (index < lines.length) {
        const item = lines[index].match(pattern);
        if (!item) break;
        items.push(item[1]);
        index += 1;
      }
      blocks.push({ type: 'list', ordered: isOrdered, items });
      continue;
    }

    const paragraph = [line.trim()];
    index += 1;
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^(#{1,6})\s+/.test(lines[index]) &&
      !/^```/.test(lines[index]) &&
      !/^>\s?/.test(lines[index]) &&
      !/^\s*(?:[-*+]\s+|\d+[.)]\s+)/.test(lines[index]) &&
      !/^(?:---+|\*\*\*+)\s*$/.test(lines[index])
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ type: 'paragraph', text: paragraph.join(' ') });
  }

  return blocks;
}

function safeUrl(value: string, image = false): string | null {
  const url = value.trim();
  if (url.startsWith('/') || url.startsWith('./') || url.startsWith('../') || url.startsWith('#')) return url;
  try {
    const parsed = new URL(url);
    const allowed = image ? ['http:', 'https:'] : ['http:', 'https:', 'mailto:'];
    return allowed.includes(parsed.protocol) ? url : null;
  } catch {
    return null;
  }
}

function inline(text: string, keyPrefix: string): ReactNode[] {
  const pattern = /(!?\[[^\]]*\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`)/g;
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) nodes.push(text.slice(cursor, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${match.index}`;

    const image = token.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (image) {
      const src = safeUrl(image[2], true);
      nodes.push(src ? <img key={key} src={src} alt={image[1]} loading="lazy" /> : image[1]);
    } else if (link) {
      const href = safeUrl(link[2]);
      const external = href?.startsWith('http://') || href?.startsWith('https://');
      nodes.push(
        href ? (
          <a key={key} href={href} target={external ? '_blank' : undefined} rel={external ? 'noopener noreferrer' : undefined}>
            {link[1]}
          </a>
        ) : (
          link[1]
        ),
      );
    } else if (token.startsWith('**')) {
      nodes.push(<strong key={key} className="font-bold text-slate-100">{token.slice(2, -2)}</strong>);
    } else {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    }
    cursor = match.index + token.length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

function MarkdownContent({ markdown }: { markdown: string }) {
  return (
    <div className="markdown-content">
      {parseBlocks(markdown).map((block, index) => {
        const key = `block-${index}`;
        if (block.type === 'heading') {
          const content = inline(block.text, key);
          // ページのh1はFront Matterのtitleに一本化する。
          // Markdown本文で誤って#を使ってもh2として扱い、h1を重複させない。
          if (block.level === 1) return <h2 key={key}>{content}</h2>;
          if (block.level === 2) return <h2 key={key}>{content}</h2>;
          if (block.level === 3) return <h3 key={key}>{content}</h3>;
          if (block.level === 4) return <h4 key={key}>{content}</h4>;
          if (block.level === 5) return <h5 key={key}>{content}</h5>;
          return <h6 key={key}>{content}</h6>;
        }
        if (block.type === 'paragraph') return <p key={key}>{inline(block.text, key)}</p>;
        if (block.type === 'quote') return <blockquote key={key}>{inline(block.text, key)}</blockquote>;
        if (block.type === 'hr') return <hr key={key} />;
        if (block.type === 'code') return <pre key={key}><code className={block.language ? `language-${block.language}` : undefined}>{block.text}</code></pre>;
        const List = block.ordered ? 'ol' : 'ul';
        return <List key={key}>{block.items.map((item, itemIndex) => <li key={`${key}-${itemIndex}`}>{inline(item, `${key}-${itemIndex}`)}</li>)}</List>;
      })}
    </div>
  );
}

export default async function MarkdownPage({ fileName }: MarkdownPageProps) {
  const filePath = path.join(process.cwd(), 'content', fileName);
  let source: string;
  try {
    source = await fs.readFile(filePath, 'utf8');
  } catch (error) {
    console.error(`Markdown file could not be read: ${fileName}`, error);
    source = [
      '---',
      'title: ページを表示できません',
      'description: 本文ファイルを読み込めませんでした。時間をおいてもう一度お試しください。',
      '---',
      '',
      'ページの準備中です。',
    ].join('\n');
  }
  const { data, body } = parseFrontMatter(source);

  return (
    <main className="min-h-[calc(100vh-4rem)] bg-slate-950 px-4 py-10 text-slate-100 sm:px-6 sm:py-14">
      <article className="mx-auto max-w-4xl overflow-hidden rounded-2xl border border-white/10 bg-slate-900/70 shadow-2xl shadow-black/20">
        <header className="border-b border-white/10 bg-gradient-to-br from-blue-500/10 via-transparent to-indigo-500/10 px-5 py-8 sm:px-10 sm:py-10">
          <h1 className="text-3xl font-black tracking-tight text-white sm:text-4xl">{data.title}</h1>
          {data.description && <p className="mt-3 max-w-2xl leading-7 text-slate-400">{data.description}</p>}
          {data.updatedAt && <p className="mt-4 text-sm text-slate-500">更新日：{data.updatedAt}</p>}
        </header>
        <div className="px-5 py-8 sm:px-10 sm:py-10">
          <MarkdownContent markdown={body} />
        </div>
      </article>
    </main>
  );
}
