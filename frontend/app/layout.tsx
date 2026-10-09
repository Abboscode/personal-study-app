import type { Metadata } from "next";
import Link from "next/link";
import "katex/dist/katex.min.css";
import "highlight.js/styles/github-dark.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Personal Study",
  description: "A private, self-hosted spaced repetition study app",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <Link className="brand" href="/">Recall</Link>
          <nav aria-label="Main navigation">
            <Link href="/">Dashboard</Link>
            <Link href="/import">Import</Link>
            <Link href="/generate">Generate</Link>
            <Link href="/notes/generate">Notes</Link>
            <Link className="nav-review" href="/review">Start review</Link>
          </nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
