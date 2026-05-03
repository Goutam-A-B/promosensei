import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PromoSensei",
  description: "Find the best deals across Indian e-commerce platforms."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" dir="auto">
      <body>{children}</body>
    </html>
  );
}
