import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import "highlight.js/styles/github-dark.css";
import { API_URL } from "../../config";
import { getAuthToken } from "@/lib/api";

// Extend GitHub's default sanitization schema to allow class attributes
// on table elements for styling. Scripts, event handlers, etc. remain blocked.
const sanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    table: [...(defaultSchema.attributes?.table || []), "className", "class"],
    th: [...(defaultSchema.attributes?.th || []), "className", "class"],
    td: [...(defaultSchema.attributes?.td || []), "className", "class"],
    tr: [...(defaultSchema.attributes?.tr || []), "className", "class"],
    thead: [...(defaultSchema.attributes?.thead || []), "className", "class"],
    tbody: [...(defaultSchema.attributes?.tbody || []), "className", "class"],
  },
};

type Props = {
  content: string;
  enableMarkdown?: boolean;
};

export default function SafeMarkdownRenderer({ content, enableMarkdown = true }: Props) {
  if (!enableMarkdown || !content) {
    return <div className="whitespace-pre-wrap leading-relaxed">{content}</div>;
  }

  return (
  <div className="prose prose-sm dark:prose-invert max-w-none leading-relaxed dark:text-zinc-100 text-zinc-800">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema], rehypeHighlight as any]}
        components={{
          h1: ({ node, ...props }) => (
            <h1 className="text-xl font-bold mb-2" {...props} />
          ),
          h2: ({ node, ...props }) => (
            <h2 className="text-lg font-bold mb-2" {...props} />
          ),
          h3: ({ node, ...props }) => (
            <h3 className="text-base font-bold mb-1" {...props} />
          ),
          h4: ({ node, ...props }) => (
            <h4 className="text-sm font-bold mb-1" {...props} />
          ),
          h5: ({ node, ...props }) => (
            <h5 className="text-sm font-semibold mb-1" {...props} />
          ),
          h6: ({ node, ...props }) => (
            <h6 className="text-xs font-semibold mb-1" {...props} />
          ),
          p: ({ node, ...props }) => <p className="mb-2" {...props} />,
          ul: ({ node, ...props }) => (
            <ul className="list-disc pl-5 mb-2 space-y-1" {...props} />
          ),
          ol: ({ node, ...props }) => (
            <ol className="list-decimal pl-5 mb-2 space-y-1" {...props} />
          ),
          li: ({ node, ...props }) => <li className="mb-1" {...props} />,
          blockquote: ({ node, ...props }) => (
            <blockquote
              className="border-l-4 border-primary/40 pl-4 italic text-foreground/80 dark:text-foreground/80 my-2"
              {...props}
            />
          ),
          code: ({ node, inline, className, children, ...props }: any) => {
            return !inline ? (
              <pre className="bg-muted/40 dark:bg-card/40 text-foreground dark:text-foreground p-3 rounded-lg overflow-x-auto my-3 text-sm border border-border shadow-sm">
                <code className={className} {...props}>
                  {children}
                </code>
              </pre>
            ) : (
              <code className="bg-muted/60 dark:bg-card/60 text-primary dark:text-primary px-1.5 py-0.5 rounded-md text-sm font-mono border border-border">
                {children}
              </code>
            );
          },
          table: ({ node, ...props }) => (
            <table className="table-auto border-collapse border border-border my-4" {...props} />
          ),
          thead: ({ node, ...props }) => (
            <thead className="bg-muted/60 dark:bg-card/60" {...props} />
          ),
          th: ({ node, ...props }) => (
            <th className="border border-border px-3 py-1 text-left font-semibold" {...props} />
          ),
          td: ({ node, ...props }) => (
            <td className="border border-border px-3 py-1" {...props} />
          ),
          tr: ({ node, ...props }) => (
            <tr className="border-b border-border" {...props} />
          ),
          tbody: ({ node, ...props }) => (
            <tbody {...props} />
          ),
          a: ({ node, href, children, ...props }) => {
            // Render excel-skill download links as styled download buttons
            if (href && href.includes('/excel-skill/download/')) {
              const handleClick = (e: React.MouseEvent) => {
                e.preventDefault();
                const token = getAuthToken();
                const url = `${API_URL}${href}${token ? `?token=${encodeURIComponent(token)}` : ''}`;
                window.open(url, '_blank');
              };
              return (
                <button
                  onClick={handleClick}
                  className="inline-flex items-center gap-2 px-3 py-1.5 my-1 rounded-md text-sm font-medium bg-green-100 dark:bg-green-950/40 text-green-700 dark:text-green-400 border border-green-300 dark:border-green-800 hover:bg-green-200 dark:hover:bg-green-900/50 transition-colors cursor-pointer"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                  {children}
                </button>
              );
            }
            return <a href={href} {...props}>{children}</a>;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
