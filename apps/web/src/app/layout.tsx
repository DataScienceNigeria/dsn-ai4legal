import type { Metadata } from "next";

import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "Legal Operations Platform",
  description:
    "DSN and EqualyzAI legal operations. AI may recommend, an authorised human confirms.",
};

/*
  Theme and organisation are both read before the first paint. Leaving either
  to React means the page renders once in the wrong colour and corrects itself,
  which reads as a fault rather than a preference.
*/
const THEME_SCRIPT = `
try {
  var stored = localStorage.getItem('dsn-lai-theme');
  var dark = stored ? stored === 'dark' : true;
  if (dark) document.documentElement.classList.add('dark');
} catch (e) {
  document.documentElement.classList.add('dark');
}
try {
  var org = localStorage.getItem('dsn-lai-entity');
  if (org) document.documentElement.dataset.entity = org;
} catch (e) {
  document.documentElement.dataset.entity = 'DSN';
}
`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-GB" suppressHydrationWarning>
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
