import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, IBM_Plex_Sans_Arabic } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const arabic = IBM_Plex_Sans_Arabic({ variable: "--font-arabic", subsets: ["arabic"], weight: ["400", "500", "600"] });

export const metadata: Metadata = {
  title: "Atlas — talk to your supply chain",
  description: "A multilingual voice agent that reasons over an ontology-driven supply-chain knowledge graph.",
};

export const viewport: Viewport = { themeColor: "#05080f" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} ${arabic.variable}`}>
      <body className="font-sans">{children}</body>
    </html>
  );
}
