"use client";

import * as React from "react";

import { Button } from "@/components/ui";

export function ThemeToggle() {
  const [dark, setDark] = React.useState(false);

  React.useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      globalThis.localStorage.setItem("dsn-lai-theme", next ? "dark" : "light");
    } catch {
      // A browser that refuses storage still gets the toggle for this session.
    }
  }

  return (
    <Button variant="ghost" size="sm" onClick={toggle} aria-label="Switch colour theme">
      <span aria-hidden>{dark ? "☀" : "☾"}</span>
      {dark ? "Light" : "Dark"}
    </Button>
  );
}
