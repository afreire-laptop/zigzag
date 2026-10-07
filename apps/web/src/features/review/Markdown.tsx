import type { ReactNode } from "react";
import styles from "./Markdown.module.css";

// Renders the subset of Markdown the API's handoff renderer produces, as React elements (never raw HTML).
// Headings are shifted down so the document nests under the page's own headings.

function inline(text: string): ReactNode[] {
  let offset = 0; // each part's position in the line is its stable key
  return text.split(/(\*\*[^*]+\*\*|_[^_]+_)/g).map((part) => {
    const key = offset;
    offset += part.length;
    if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={key}>{part.slice(2, -2)}</strong>;
    if (/^_[^_]+_$/.test(part)) return <em key={key}>{part.slice(1, -1)}</em>;
    return part;
  });
}

/** Lines ending in two spaces continue with a line break, as in Markdown. */
function withBreaks(lines: readonly string[]): ReactNode[] {
  let offset = 0; // keyed by position in the text, which is stable for a rendered document
  return lines.flatMap((line, i) => {
    offset += line.length + 1;
    return [...inline(line.trim()), i < lines.length - 1 ? <br key={`br-${offset}`} /> : null];
  });
}

export function Markdown({ source }: { source: string }) {
  const blocks: ReactNode[] = [];
  const lines = source.split("\n");
  let i = 0;
  const at = (n: number): string => lines[n] ?? "";
  while (i < lines.length) {
    const line = at(i);
    const key = `${blocks.length}`;
    if (line.trim() === "") {
      i++;
    } else if (/^#{1,3} /.test(line)) {
      const level = line.indexOf(" ");
      const text = inline(line.slice(level + 1));
      blocks.push(
        level === 1 ? <h3 key={key}>{text}</h3> : level === 2 ? <h4 key={key}>{text}</h4> : <h5 key={key}>{text}</h5>,
      );
      i++;
    } else if (line.startsWith("- ")) {
      const items: string[][] = [];
      while (i < lines.length && (at(i).startsWith("- ") || at(i).startsWith("  "))) {
        if (at(i).startsWith("- ")) items.push([at(i).slice(2)]);
        else items.at(-1)?.push(at(i));
        i++;
      }
      blocks.push(
        <ul key={key}>
          {items.map((item) => (
            <li key={item.join("\n")}>{withBreaks(item)}</li>
          ))}
        </ul>,
      );
    } else if (line.startsWith(">")) {
      const quoted: string[] = [];
      while (i < lines.length && at(i).startsWith(">")) quoted.push(at(i++).replace(/^> ?/, ""));
      blocks.push(<blockquote key={key}>{quoted.join("\n")}</blockquote>);
    } else if (line === "---") {
      blocks.push(<hr key={key} />);
      i++;
    } else {
      const paragraph: string[] = [];
      while (i < lines.length && at(i).trim() !== "" && !/^(#|- |>|---$)/.test(at(i))) paragraph.push(at(i++));
      blocks.push(<p key={key}>{withBreaks(paragraph)}</p>);
    }
  }
  return <div className={styles.document}>{blocks}</div>;
}
