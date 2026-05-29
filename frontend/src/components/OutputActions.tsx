import { useState } from "react";

type OutputMode = "default" | "document" | "email";

type OutputActionsProps = {
  text: string;
  filenamePrefix: string;
  mode?: OutputMode;
};

type AsyncActionState = "idle" | "success" | "failed";

function toFilename(prefix: string, extension: "txt" | "html"): string {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "");
  return `${prefix}_${stamp}.${extension}`;
}

function normalizeLineEndings(value: string): string {
  return value.replace(/\r\n/g, "\n");
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function stripMarkdownBoldMarkers(value: string): string {
  const withoutPairs = value.replace(/\*\*([\s\S]+?)\*\*/g, "$1");
  return withoutPairs.replace(/\*\*/g, "");
}

function countMarkdownBoldSpans(value: string): number {
  const matches = value.match(/\*\*([\s\S]+?)\*\*/g);
  return matches ? matches.length : 0;
}

function getMarkdownBoldOutliers(value: string): string[] {
  const outliers: string[] = [];
  const markerCount = (value.match(/\*\*/g) || []).length;
  if (markerCount % 2 !== 0) {
    outliers.push("Unmatched `**` marker detected.");
  }
  if (/\*\*\s*\*\*/.test(value)) {
    outliers.push("Empty bold marker pair (`****`) detected.");
  }
  return outliers;
}

function markdownBoldToInlineHtml(value: string): string {
  const escaped = escapeHtml(value);
  const withBold = escaped.replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>");
  return withBold.replace(/\*\*/g, "");
}

function markdownBoldToParagraphHtml(value: string): string {
  return normalizeLineEndings(value)
    .split("\n")
    .map((line) => (line.trim() ? `<p>${markdownBoldToInlineHtml(line)}</p>` : "<p>&nbsp;</p>"))
    .join("");
}

function buildPrintableHtml(title: string, value: string): string {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${escapeHtml(title)}</title>
    <style>
      :root { color-scheme: light; }
      body {
        margin: 0;
        background: #fff;
        color: #111827;
        font-family: "Arial", "Helvetica Neue", Helvetica, sans-serif;
      }
      main {
        max-width: 800px;
        margin: 0 auto;
        padding: 32px 28px 44px;
      }
      h1 {
        margin: 0 0 20px;
        font-size: 18px;
      }
      p {
        margin: 0 0 10px;
        font-size: 13px;
        line-height: 1.5;
        white-space: normal;
      }
      strong {
        font-weight: 700;
      }
      @media print {
        main {
          max-width: 100%;
          padding: 0;
        }
      }
    </style>
  </head>
  <body>
    <main>
      <h1>${escapeHtml(title)}</h1>
      ${markdownBoldToParagraphHtml(value)}
    </main>
  </body>
</html>`;
}

function buildRichEmailHtml(value: string): string {
  const lines = normalizeLineEndings(value).split("\n");
  const htmlLines = lines.map((line) => (line ? markdownBoldToInlineHtml(line) : "<br />")).join("<br />");
  return `<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.45;">${htmlLines}</div>`;
}

export function OutputActions({ text, filenamePrefix, mode = "default" }: OutputActionsProps) {
  const [copyState, setCopyState] = useState<AsyncActionState>("idle");
  const [richCopyState, setRichCopyState] = useState<AsyncActionState>("idle");
  const [pdfState, setPdfState] = useState<AsyncActionState>("idle");

  if (!text.trim()) {
    return null;
  }

  const normalizedText = normalizeLineEndings(text);
  const plainText = stripMarkdownBoldMarkers(normalizedText);
  const boldSpanCount = countMarkdownBoldSpans(normalizedText);
  const outliers = getMarkdownBoldOutliers(normalizedText);
  const hasMarkdownBold = boldSpanCount > 0 || outliers.length > 0;

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(plainText);
      setCopyState("success");
    } catch {
      setCopyState("failed");
    }
    window.setTimeout(() => setCopyState("idle"), 1800);
  }

  async function onCopyRichEmail() {
    const richHtml = buildRichEmailHtml(normalizedText);
    try {
      if (typeof ClipboardItem !== "undefined" && "write" in navigator.clipboard) {
        const item = new ClipboardItem({
          "text/plain": new Blob([plainText], { type: "text/plain" }),
          "text/html": new Blob([richHtml], { type: "text/html" })
        });
        await navigator.clipboard.write([item]);
      } else {
        await navigator.clipboard.writeText(plainText);
      }
      setRichCopyState("success");
    } catch {
      setRichCopyState("failed");
    }
    window.setTimeout(() => setRichCopyState("idle"), 2200);
  }

  function onDownload() {
    const blob = new Blob([plainText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = toFilename(filenamePrefix, "txt");
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function onPrintPdf() {
    const printableTitle = filenamePrefix.replace(/_/g, " ");
    const printableHtml = buildPrintableHtml(printableTitle, normalizedText);
    const triggerIframeFallback = () => {
      const iframe = document.createElement("iframe");
      iframe.style.position = "fixed";
      iframe.style.width = "0";
      iframe.style.height = "0";
      iframe.style.border = "0";
      iframe.style.opacity = "0";
      iframe.setAttribute("aria-hidden", "true");
      document.body.appendChild(iframe);
      const frameDoc = iframe.contentDocument;
      if (!frameDoc) {
        iframe.remove();
        setPdfState("failed");
        window.setTimeout(() => setPdfState("idle"), 2200);
        return;
      }
      frameDoc.open();
      frameDoc.write(printableHtml);
      frameDoc.close();

      window.setTimeout(() => {
        try {
          const frameWindow = iframe.contentWindow;
          if (!frameWindow) {
            throw new Error("Print iframe is unavailable.");
          }
          frameWindow.focus();
          frameWindow.print();
          setPdfState("success");
        } catch {
          setPdfState("failed");
        } finally {
          window.setTimeout(() => iframe.remove(), 1500);
          window.setTimeout(() => setPdfState("idle"), 2200);
        }
      }, 260);
    };

    try {
      const popup = window.open("", "_blank", "noopener,noreferrer");
      if (!popup) {
        triggerIframeFallback();
        return;
      }
      popup.document.open();
      popup.document.write(printableHtml);
      popup.document.close();
      window.setTimeout(() => {
        try {
          popup.focus();
          popup.print();
          setPdfState("success");
        } catch {
          triggerIframeFallback();
        }
      }, 260);
    } catch {
      triggerIframeFallback();
    }
    window.setTimeout(() => setPdfState("idle"), 2200);
  }

  return (
    <>
      <div className="output-actions">
        <button type="button" className="secondary-btn" onClick={onCopy}>
          {copyState === "idle"
            ? mode === "email"
              ? "Copy Plain Email"
              : "Copy Plain Text"
            : copyState === "success"
              ? "Copied"
              : "Copy failed"}
        </button>
        {mode === "email" && hasMarkdownBold ? (
          <button type="button" className="secondary-btn" onClick={onCopyRichEmail}>
            {richCopyState === "idle"
              ? "Copy Rich Email (bold)"
              : richCopyState === "success"
                ? "Rich copy ready"
                : "Rich copy failed"}
          </button>
        ) : null}
        <button type="button" className="secondary-btn" onClick={onDownload}>
          Download Plain .txt
        </button>
        {mode !== "email" ? (
          <button type="button" className="secondary-btn" onClick={onPrintPdf}>
            {pdfState === "idle"
              ? "Print / Save PDF (bold)"
              : pdfState === "success"
                ? "Print dialog opened"
                : "Enable popups for PDF"}
          </button>
        ) : null}
      </div>
      {hasMarkdownBold ? (
        <p className="helper">
          Markdown bold spans detected: {boldSpanCount}. Plain copy/download removes `**`; PDF and rich-email keep
          bold.
        </p>
      ) : null}
      {outliers.map((item) => (
        <p key={item} className="helper">
          Formatting outlier: {item}
        </p>
      ))}
    </>
  );
}
