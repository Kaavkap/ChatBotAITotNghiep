import "./globals.css";

export const metadata = {
  title:
    "Trợ lý Trí tuệ Nhân tạo Hỗ trợ Thông tin Học vụ - Trường Đại học Thủ Dầu Một (TDMU)",
  description:
    "Hệ thống Advanced RAG tư vấn quy chế học vụ TDMU chính xác 100% — SV: Lê Quốc Bảo (MSSV: 2224801030361, Lớp: D22KTPM01) - GVHD: ThS. Lê Từ Minh Trí",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi">
      <body className="antialiased selection:bg-blue-600 selection:text-white">
        {children}
      </body>
    </html>
  );
}
