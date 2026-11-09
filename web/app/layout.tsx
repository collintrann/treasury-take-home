import type { Metadata } from "next";
import Link from "next/link";
import { Atkinson_Hyperlegible } from "next/font/google";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

// Designed for low-vision readers.
const atkinson = Atkinson_Hyperlegible({ variable: "--font-atkinson", subsets: ["latin"], weight: ["400", "700"] });

export const metadata: Metadata = {
  title: { default: "Label Check", template: "%s | Label Check" },
  description: "Review alcohol label applications against their label artwork",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${atkinson.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-card focus:px-4 focus:py-2 focus:font-bold"
        >
          Skip to main content
        </a>
        <header className="bg-masthead text-masthead-foreground">
          <div className="mx-auto flex max-w-7xl flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-4">
            <Link
              href="/"
              className="rounded-sm text-2xl font-bold focus-visible:outline-3 focus-visible:outline-offset-4 focus-visible:outline-masthead-foreground"
            >
              Label Check
            </Link>
            <span className="text-lg opacity-90">Alcohol label application review</span>
          </div>
        </header>

        <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 pt-6 pb-10">
          <TooltipProvider delayDuration={300}>{children}</TooltipProvider>
        </main>

        <footer className="border-t bg-card">
          <p className="mx-auto max-w-7xl px-4 py-5 text-muted-foreground">
            Prototype. Not connected to COLA. Label images are sent to Anthropic to be read and are not stored.
          </p>
        </footer>
      </body>
    </html>
  );
}
