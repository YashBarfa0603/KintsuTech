import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "KintsuTech — Detect. Adapt. Recover.",
  description:
    "API change detection, impact analysis, AI-assisted repair, validation, and recovery platform.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
