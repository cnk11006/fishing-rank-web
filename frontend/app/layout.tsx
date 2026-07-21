import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "피싱템 순위 레이더",
  description: "피싱템 쇼핑 순위·키워드·광고 통합 분석 시스템",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
