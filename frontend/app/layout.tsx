import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "IPO Lens",
  description: "Understand an IPO beyond the hype. Research aid, not investment advice.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
