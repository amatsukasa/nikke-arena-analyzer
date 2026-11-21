"use client";

import { Node } from "@tiptap/core";
import { EditorContent, NodeViewWrapper, ReactNodeViewRenderer, useEditor, useEditorState, type NodeViewProps } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { isArticleLink, type ArticleNode } from "@/lib/articles";
import { ArticleImage, articleTypography } from "./ArticleBody";

const buttonStyle = "min-h-11 rounded-lg border border-white/15 px-3 py-2 text-sm hover:bg-white/10 disabled:opacity-50 aria-pressed:border-sky-400 aria-pressed:bg-sky-500/20";

function ImageNodeView({ node, updateAttributes, deleteNode }: NodeViewProps) {
  const { t } = useI18n();
  return (
    <NodeViewWrapper contentEditable={false} className="my-4 rounded-lg border border-white/10 p-3">
      <ArticleImage id={node.attrs.imageId} caption="" />
      <label className="block text-sm text-slate-300">
        {t("articles.caption")}
        <input value={node.attrs.caption} maxLength={300}
          onChange={event => updateAttributes({ caption: event.target.value })}
          className="mt-1 block min-h-11 w-full rounded-lg border border-white/15 bg-slate-900 px-3"
        />
      </label>
      <button type="button" onClick={deleteNode} className={`${buttonStyle} mt-2`}>{t("articles.removeImage")}</button>
    </NodeViewWrapper>
  );
}

const ArticleImageExtension = Node.create({
  name: "articleImage",
  group: "block",
  atom: true,
  addAttributes() {
    return { imageId: { default: null }, caption: { default: "" } };
  },
  parseHTML() {
    return [{ tag: "figure[data-article-image]" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["figure", { ...HTMLAttributes, "data-article-image": "" }];
  },
  addNodeView() {
    return ReactNodeViewRenderer(ImageNodeView);
  },
});

const extensions = [
  StarterKit.configure({
    blockquote: false, code: false, codeBlock: false, horizontalRule: false,
    italic: false, orderedList: false, strike: false, underline: false,
    heading: { levels: [2] },
    link: { openOnClick: false, autolink: false, linkOnPaste: false, isAllowedUri: isArticleLink },
  }),
  ArticleImageExtension,
];

type Selection = { from: number; to: number };
type LinkForm = { selection: Selection; href: string; text?: string; invalid?: boolean };

function ToolbarButton({ children, pressed, disabled, onClick }: {
  children: ReactNode; pressed?: boolean; disabled?: boolean; onClick: () => void;
}) {
  return (
    <button type="button" className={buttonStyle} aria-pressed={pressed} disabled={disabled}
      onMouseDown={event => event.preventDefault()} onClick={onClick}>{children}</button>
  );
}

export default function ArticleEditor({ initialBody, disabled, onChange, onUploadState }: {
  initialBody: ArticleNode; disabled: boolean; onChange: (body: ArticleNode) => void; onUploadState: (active: boolean) => void;
}) {
  const { t } = useI18n();
  const fileInput = useRef<HTMLInputElement>(null);
  const insertAt = useRef<Selection | null>(null);
  const [link, setLink] = useState<LinkForm | null>(null);
  const [imageError, setImageError] = useState("");
  const [uploading, setUploading] = useState(false);
  const label = useId();
  const editor = useEditor({
    extensions,
    content: initialBody,
    immediatelyRender: false,
    editorProps: {
      attributes: { class: `${articleTypography} min-h-56 px-3 py-2 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sky-500 sm:px-4`,
        role: "textbox", "aria-multiline": "true", "aria-labelledby": label },
    },
    onUpdate: ({ editor }) => onChange(editor.getJSON()),
  });
  const active = useEditorState({
    editor,
    selector: ({ editor }) => ({
      paragraph: editor?.isActive("paragraph"), heading: editor?.isActive("heading"),
      bold: editor?.isActive("bold"), list: editor?.isActive("bulletList"), link: editor?.isActive("link"),
    }),
  });
  useEffect(() => {
    editor?.setEditable(!disabled && !uploading, false);
  }, [disabled, editor, uploading]);
  if (!editor) return <p role="status">{t("articles.loading")}</p>;
  const contentEditor = editor;

  function openLink() {
    contentEditor.commands.extendMarkRange("link");
    const { from, to } = contentEditor.state.selection;
    const current = contentEditor.getAttributes("link").href as string | undefined;
    setLink({ selection: { from, to }, href: current ?? "", text: from === to ? "" : undefined });
  }

  function applyLink(event: FormEvent) {
    event.preventDefault();
    if (!link) return;
    const href = link.href.trim();
    if (!isArticleLink(href) || (link.text !== undefined && !link.text.trim())) {
      setLink({ ...link, invalid: true });
      return;
    }
    const chain = contentEditor.chain().focus().setTextSelection(link.selection);
    if (link.text !== undefined) {
      chain.insertContent({ type: "text", text: link.text, marks: [{ type: "link", attrs: { href } }] }).run();
    } else {
      chain.setLink({ href }).run();
    }
    setLink(null);
  }

  async function upload(file?: File) {
    if (!file) return;
    const placement = insertAt.current ?? contentEditor.state.selection;
    setUploading(true);
    onUploadState(true);
    setImageError("");
    contentEditor.setEditable(false, false);
    try {
      const body = new FormData();
      body.set("file", file);
      const response = await fetch("/api/admin/articles/images", { method: "POST", body });
      if (!response.ok) {
        setImageError(t(response.status === 413 ? "articles.imageTooLarge" : "articles.imageError"));
        return;
      }
      const { image_id } = await response.json();
      contentEditor.setEditable(true, false);
      const inserted = contentEditor.chain().focus().insertContentAt(placement, {
        type: "articleImage", attrs: { imageId: image_id, caption: "" },
      }).run();
      if (!inserted) setImageError(t("articles.imageError"));
    } catch {
      setImageError(t("articles.imageError"));
    } finally {
      contentEditor.setEditable(true, false);
      setUploading(false);
      onUploadState(false);
    }
  }

  return (
    <div className="min-w-0 space-y-2">
      <div id={label} className="text-sm font-medium text-slate-200">{t("articles.body")}</div>
      <div className="overflow-hidden rounded-xl border border-white/15 bg-slate-950">
        <div className="flex flex-wrap gap-2 border-b border-white/10 bg-slate-900 p-2" role="group" aria-label={t("articles.formatting")}>
          <ToolbarButton pressed={active?.paragraph} disabled={uploading || !!link} onClick={() => contentEditor.chain().focus().setParagraph().run()}>{t("articles.paragraph")}</ToolbarButton>
          <ToolbarButton pressed={active?.heading} disabled={uploading || !!link} onClick={() => contentEditor.chain().focus().toggleHeading({ level: 2 }).run()}>{t("articles.heading")}</ToolbarButton>
          <ToolbarButton pressed={active?.bold} disabled={uploading || !!link} onClick={() => contentEditor.chain().focus().toggleBold().run()}>{t("articles.bold")}</ToolbarButton>
          <ToolbarButton pressed={active?.list} disabled={uploading || !!link} onClick={() => contentEditor.chain().focus().toggleBulletList().run()}>{t("articles.bullets")}</ToolbarButton>
          <ToolbarButton pressed={active?.link} disabled={uploading || !!link} onClick={openLink}>{t("articles.link")}</ToolbarButton>
          <ToolbarButton disabled={uploading || !!link} onClick={() => {
            const { from, to } = contentEditor.state.selection;
            // Insert after selected text rather than replacing it.
            insertAt.current = { from: from === to ? from : to, to };
            fileInput.current?.click();
          }}>{t("articles.insertImage")}</ToolbarButton>
          <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={event => {
            const file = event.target.files?.[0];
            event.target.value = "";
            void upload(file);
          }} />
        </div>
        {link && (
          <form className="space-y-2 border-b border-white/10 p-3" onSubmit={applyLink}>
            <label className="block text-sm">
              {t("articles.linkUrl")}
              <input autoFocus value={link.href} maxLength={2048} inputMode="url" autoCapitalize="none"
                onChange={event => setLink({ ...link, href: event.target.value, invalid: false })}
                className="mt-1 block min-h-11 w-full rounded-lg border border-white/15 bg-slate-900 px-3" />
            </label>
            {link.text !== undefined && (
              <label className="block text-sm">{t("articles.linkText")}
                <input value={link.text} onChange={event => setLink({ ...link, text: event.target.value, invalid: false })}
                  className="mt-1 block min-h-11 w-full rounded-lg border border-white/15 bg-slate-900 px-3" />
              </label>
            )}
            {link.invalid && <p role="alert" className="text-sm text-rose-300">{t("articles.invalidLink")}</p>}
            <div className="flex flex-wrap gap-2">
              <button type="submit" className={buttonStyle}>{t("articles.applyLink")}</button>
              {link.text === undefined && link.href && (
                <button type="button" className={buttonStyle} onClick={() => {
                  contentEditor.chain().focus().setTextSelection(link.selection).unsetLink().run();
                  setLink(null);
                }}>{t("articles.removeLink")}</button>
              )}
              <button type="button" className={buttonStyle} onClick={() => { setLink(null); contentEditor.commands.focus(); }}>{t("articles.cancel")}</button>
            </div>
          </form>
        )}
        <EditorContent editor={editor} />
      </div>
      {uploading && <p role="status" className="text-sm text-slate-300">{t("articles.uploading")}</p>}
      {imageError && <p role="alert" className="text-sm text-rose-300">{imageError}</p>}
    </div>
  );
}
