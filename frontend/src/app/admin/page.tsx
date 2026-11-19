"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

interface TDMUAuthUser {
  email: string;
  student_id: string;
  full_name: string;
  avatar_url?: string;
  picture?: string;
  is_tdmu_student: boolean;
  is_admin?: boolean;
}

const ALLOWED_ADMIN_EMAIL = "2224801030361@student.tdmu.edu.vn";

interface ActiveDocumentItem {
  file: string;
  doc_title: string;
  issue_year: string;
  file_type: string;
  chunks_count: number;
  pdf_url: string;
  export_docx_url: string;
}

interface TopicDistributionItem {
  topic: string;
  count: number;
  percentage: number;
}

interface RecentQueryItem {
  message_id: string;
  question: string;
  topic: string;
  citations_count: number;
  is_answerable: boolean;
  feedback: "like" | "dislike" | null;
  created_at: string;
}

interface AdminAnalyticsData {
  status: string;
  university: string;
  active_documents_count: number;
  total_chunks_indexed: number;
  active_documents: ActiveDocumentItem[];
  total_queries: number;
  total_users: number;
  total_sessions: number;
  feedback_summary: {
    like_count: number;
    dislike_count: number;
    total_rated: number;
    satisfaction_rate: number;
  };
  topic_distribution: TopicDistributionItem[];
  recent_queries: RecentQueryItem[];
}

export default function AdminDashboardPage() {
  const router = useRouter();
  const [authUser, setAuthUser] = useState<TDMUAuthUser | null>(null);
  const [authChecked, setAuthChecked] = useState<boolean>(false);
  const [analytics, setAnalytics] = useState<AdminAnalyticsData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // State cho tính năng tải lên & nạp văn bản mới (PDF / DOCX)
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isIngesting, setIsIngesting] = useState<boolean>(false);
  const [ingestNotice, setIngestNotice] = useState<string | null>(null);

  const fetchAnalytics = useCallback(async (userEmail: string) => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const res = await fetch("http://127.0.0.1:8000/api/admin/analytics", {
        headers: {
          "X-User-Email": userEmail,
        },
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }
      const data: AdminAnalyticsData = await res.json();
      setAnalytics(data);
    } catch (err: any) {
      setErrorMsg(
        err?.message ||
          "Không thể kết nối tới Backend tại http://127.0.0.1:8000/api/admin/analytics"
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Kiểm tra trạng thái đăng nhập ngay khi tải trang; chỉ cho phép duy nhất 2224801030361@student.tdmu.edu.vn
  useEffect(() => {
    try {
      const saved = localStorage.getItem("tdmu_oauth_user");
      if (saved) {
        const parsed: TDMUAuthUser = JSON.parse(saved);
        if (
          parsed &&
          parsed.is_tdmu_student &&
          parsed.email &&
          parsed.email.toLowerCase() === ALLOWED_ADMIN_EMAIL &&
          parsed.is_admin === true
        ) {
          setAuthUser(parsed);
          setAuthChecked(true);
          fetchAnalytics(parsed.email);
          return;
        }
      }
    } catch {
      // Ignore storage error
    }

    setAuthUser(null);
    setAuthChecked(true);
    setIsLoading(false);
    const redirectTimer = setTimeout(() => {
      router.replace("/");
    }, 2800);
    return () => clearTimeout(redirectTimer);
  }, [fetchAnalytics, router]);

  const handleIngestDocument = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!authUser?.email) return;

    setIsIngesting(true);
    setIngestNotice(null);
    setErrorMsg(null);

    try {
      let response: Response;
      if (selectedFile) {
        const formData = new FormData();
        formData.append("file", selectedFile);
        response = await fetch("http://127.0.0.1:8000/api/ingest", {
          method: "POST",
          headers: {
            "X-User-Email": authUser.email,
          },
          body: formData,
        });
      } else {
        response = await fetch("http://127.0.0.1:8000/api/ingest", {
          method: "POST",
          headers: {
            "X-User-Email": authUser.email,
          },
        });
      }

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(
          errData.detail || `Lỗi nạp dữ liệu (HTTP ${response.status})`
        );
      }

      const result = await response.json();
      setIngestNotice(
        `✓ Đã bóc tách và nạp thành công ${result.processed_files} văn bản (Tổng cộng: ${result.total_chunks_indexed} chunks trong Qdrant Vector Store).`
      );
      setSelectedFile(null);
      await fetchAnalytics(authUser.email);
    } catch (err: any) {
      setErrorMsg(err?.message || "Lỗi khi thực thi nạp văn bản vào Qdrant.");
    } finally {
      setIsIngesting(false);
    }
  };

  if (!authChecked) {
    return (
      <div className="min-h-screen bg-slate-100 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl p-6 shadow-md border border-slate-200 text-xs font-semibold text-slate-600">
          Đang kiểm tra quyền truy cập Quản trị TDMU...
        </div>
      </div>
    );
  }

  if (!authUser) {
    return (
      <div className="min-h-screen bg-slate-100 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-2xl p-6 shadow-xl border-2 border-red-200 text-center space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-red-100 text-red-700 font-extrabold text-xl flex items-center justify-center mx-auto">
            🔒
          </div>
          <h2 className="text-base font-extrabold text-slate-900">
            Truy cập bị từ chối (403 Forbidden) — Chỉ dành cho Quản trị viên TDMU
          </h2>
          <p className="text-xs text-slate-600 leading-relaxed">
            Cổng Quản trị & Thống kê chỉ cấp quyền truy cập duy nhất cho tài
            khoản Quản trị viên hệ thống:{" "}
            <code className="font-mono font-bold text-[#0054A6]">
              2224801030361@student.tdmu.edu.vn
            </code>
            .
          </p>
          <p className="text-[11px] text-amber-700 font-semibold">
            Đang tự động điều hướng về Trang chủ sau giây lát...
          </p>
          <div className="pt-2">
            <Link
              href="/"
              className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-[#0054A6] hover:bg-[#003f7d] text-white font-bold text-xs shadow-sm"
            >
              <span>⬅ Quay về Trang chủ để Đăng nhập Google OAuth</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const maxTopicCount = Math.max(
    1,
    ...(analytics?.topic_distribution.map((t) => t.count) || [1])
  );

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900 flex flex-col">
      {/* HEADER TRANG QUẢN TRỊ TDMU */}
      <header className="bg-[#0054A6] text-white shadow-lg border-b-4 border-amber-400 px-4 py-3.5">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-xl bg-white text-[#0054A6] border-2 border-amber-300 flex flex-col items-center justify-center font-extrabold shadow-md shrink-0">
              <span className="text-xs leading-none tracking-tighter">TDMU</span>
              <span className="text-[10px] font-semibold text-amber-600 mt-0.5">
                ADMIN
              </span>
            </div>
            <div>
              <p className="text-[11px] sm:text-xs font-extrabold uppercase tracking-widest text-amber-300">
                TRƯỜNG ĐẠI HỌC THỦ DẦU MỘT (TDMU)
              </p>
              <h1 className="text-base sm:text-xl font-bold tracking-tight text-white mt-0.5">
                Cổng Quản trị Kho Tri thức & Thống kê Mức độ Hài lòng
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => authUser?.email && fetchAnalytics(authUser.email)}
              disabled={isLoading}
              className="px-3.5 py-2 rounded-xl bg-[#003f7d] hover:bg-[#002f5e] text-white font-bold text-xs border border-blue-400/40 transition-colors"
            >
              🔄 Làm mới dữ liệu
            </button>
            <Link
              href="/"
              className="px-4 py-2 rounded-xl bg-amber-400 hover:bg-amber-300 text-[#003f7d] font-extrabold text-xs shadow-md transition-all flex items-center gap-1.5"
            >
              <span>💬</span>
              <span>Quay lại Khung Chat Học vụ</span>
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6 space-y-6">
        {errorMsg && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-xs font-medium flex items-center justify-between">
            <span>⚠️ {errorMsg}</span>
            <button
              type="button"
              onClick={() => setErrorMsg(null)}
              className="font-bold underline ml-4"
            >
              Đóng
            </button>
          </div>
        )}

        {ingestNotice && (
          <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 px-4 py-3 rounded-xl text-xs font-semibold flex items-center justify-between">
            <span>{ingestNotice}</span>
            <button
              type="button"
              onClick={() => setIngestNotice(null)}
              className="font-bold underline ml-4"
            >
              Đóng
            </button>
          </div>
        )}

        {/* 1. THẺ THỐNG KÊ TỔNG QUAN (4 KPI CARDS) */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-white rounded-2xl p-4 shadow-sm border border-blue-100">
            <p className="text-xs font-bold uppercase tracking-wider text-slate-400">
              📚 Văn bản Pháp quy TDMU
            </p>
            <p className="text-2xl font-extrabold text-[#0054A6] mt-1">
              {analytics ? analytics.active_documents_count : "—"} văn bản
            </p>
            <p className="text-xs text-slate-500 mt-1">
              100% văn bản chính thức đang hoạt động
            </p>
          </div>

          <div className="bg-white rounded-2xl p-4 shadow-sm border border-blue-100">
            <p className="text-xs font-bold uppercase tracking-wider text-slate-400">
              🧩 Chunks trong Qdrant Vector Store
            </p>
            <p className="text-2xl font-extrabold text-emerald-700 mt-1">
              {analytics ? analytics.total_chunks_indexed : "—"} chunks
            </p>
            <p className="text-xs text-slate-500 mt-1">
              Hierarchical Legal Chunking + Bảng biểu
            </p>
          </div>

          <div className="bg-white rounded-2xl p-4 shadow-sm border border-blue-100">
            <p className="text-xs font-bold uppercase tracking-wider text-slate-400">
              💬 Tổng số Câu hỏi Đã xử lý
            </p>
            <p className="text-2xl font-extrabold text-slate-900 mt-1">
              {analytics ? analytics.total_queries : "—"} lượt hỏi
            </p>
            <p className="text-xs text-slate-500 mt-1">
              {analytics
                ? `${analytics.total_users} SV đăng nhập • ${analytics.total_sessions} phiên lưu`
                : "Đang tải..."}
            </p>
          </div>

          <div className="bg-white rounded-2xl p-4 shadow-sm border border-amber-200">
            <p className="text-xs font-bold uppercase tracking-wider text-slate-400">
              👍 Tỷ lệ Sinh viên Hài lòng
            </p>
            <p className="text-2xl font-extrabold text-amber-600 mt-1">
              {analytics
                ? `${analytics.feedback_summary.satisfaction_rate}%`
                : "—"}
            </p>
            <p className="text-xs text-slate-500 mt-1">
              {analytics
                ? `👍 ${analytics.feedback_summary.like_count} Hữu ích • 👎 ${analytics.feedback_summary.dislike_count} Chưa chính xác`
                : "Đang tải..."}
            </p>
          </div>
        </section>

        {/* 2. BIỂU ĐỒ CHỦ ĐỀ HỎI NHIỀU NHẤT & TỶ LỆ ĐÁNH GIÁ HÀI LÒNG */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Biểu đồ thanh (Bar Chart) các chủ đề sinh viên hỏi nhiều nhất */}
          <div className="lg:col-span-2 bg-white rounded-2xl p-5 shadow-sm border border-slate-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h2 className="text-sm font-extrabold text-[#0054A6] uppercase tracking-wider">
                  📊 Biểu đồ Chủ đề Học vụ Sinh viên Hỏi nhiều nhất
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Phân loại tự động theo 4 nhóm chủ đề trong kho tri thức TDMU
                </p>
              </div>
              <span className="text-xs font-bold text-slate-600 bg-slate-100 px-2.5 py-1 rounded-lg">
                Tổng: {analytics?.total_queries ?? 0} câu hỏi
              </span>
            </div>

            <div className="mt-4 space-y-4">
              {(analytics?.topic_distribution || []).map((item, idx) => {
                const barWidth =
                  item.count > 0
                    ? Math.max(8, Math.round((item.count / maxTopicCount) * 100))
                    : 4;
                const barColors = [
                  "bg-[#0054A6]",
                  "bg-emerald-600",
                  "bg-amber-500",
                  "bg-rose-500",
                ];
                return (
                  <div key={idx} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-slate-800">
                        {item.topic}
                      </span>
                      <span className="font-semibold text-slate-600">
                        {item.count} lượt hỏi ({item.percentage}%)
                      </span>
                    </div>
                    <div className="w-full h-3.5 bg-slate-100 rounded-full overflow-hidden border border-slate-200/70">
                      <div
                        className={`h-full ${
                          barColors[idx % barColors.length]
                        } rounded-full transition-all duration-500`}
                        style={{ width: `${barWidth}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Thẻ chi tiết Mức độ Hài lòng (👍 / 👎) */}
          <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200 flex flex-col justify-between">
            <div>
              <h2 className="text-sm font-extrabold text-[#0054A6] uppercase tracking-wider pb-3 border-b border-slate-100">
                ⭐ Đánh giá Chất lượng Câu trả lời
              </h2>
              <p className="text-xs text-slate-500 mt-2 leading-relaxed">
                Ghi nhận trực tiếp từ nút <strong>👍 Hữu ích</strong> và{" "}
                <strong>👎 Chưa chính xác</strong> dưới mỗi phản hồi của Trợ lý
                AI Học vụ TDMU.
              </p>

              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-center">
                  <p className="text-xs font-bold text-emerald-800">
                    👍 Hữu ích
                  </p>
                  <p className="text-2xl font-extrabold text-emerald-700 mt-1">
                    {analytics?.feedback_summary.like_count ?? 0}
                  </p>
                </div>
                <div className="bg-rose-50 border border-rose-200 rounded-xl p-3 text-center">
                  <p className="text-xs font-bold text-rose-800">
                    👎 Chưa chính xác
                  </p>
                  <p className="text-2xl font-extrabold text-rose-700 mt-1">
                    {analytics?.feedback_summary.dislike_count ?? 0}
                  </p>
                </div>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-100">
              <div className="flex items-center justify-between text-xs mb-1.5">
                <span className="font-semibold text-slate-600">
                  Tỷ lệ phản hồi tích cực:
                </span>
                <span className="font-extrabold text-[#0054A6]">
                  {analytics?.feedback_summary.satisfaction_rate ?? 100}%
                </span>
              </div>
              <div className="w-full h-3 bg-slate-100 rounded-full overflow-hidden border border-slate-200">
                <div
                  className="h-full bg-emerald-500 rounded-full transition-all duration-500"
                  style={{
                    width: `${
                      analytics?.feedback_summary.satisfaction_rate ?? 100
                    }%`,
                  }}
                />
              </div>
            </div>
          </div>
        </section>

        {/* 3. DANH SÁCH VĂN BẢN QUY CHẾ ĐANG NẠP & FORM TẢI LÊN FILE PDF/DOCX MỚI */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Danh sách 3 văn bản chính thức TDMU */}
          <div className="lg:col-span-2 bg-white rounded-2xl p-5 shadow-sm border border-slate-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h2 className="text-sm font-extrabold text-[#0054A6] uppercase tracking-wider">
                  🗂️ Danh mục Văn bản Quy chế & Hướng dẫn Đang nạp trong Qdrant
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Hỗ trợ mở trực tiếp file PDF gốc hoặc tải bản Microsoft Word
                  (.docx) đã chuẩn hóa
                </p>
              </div>
            </div>

            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-slate-50 text-slate-600 border-b border-slate-200 uppercase">
                    <th className="py-2.5 px-3 font-bold">Tên văn bản TDMU</th>
                    <th className="py-2.5 px-3 font-bold">Năm ban hành</th>
                    <th className="py-2.5 px-3 font-bold">Định dạng</th>
                    <th className="py-2.5 px-3 font-bold">Số Chunks</th>
                    <th className="py-2.5 px-3 font-bold">Tác vụ</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {(analytics?.active_documents || []).map((doc, dIdx) => (
                    <tr key={dIdx} className="hover:bg-blue-50/40">
                      <td className="py-3 px-3">
                        <p className="font-bold text-slate-900">
                          {doc.doc_title}
                        </p>
                        <p className="text-[11px] text-slate-400 font-mono">
                          {doc.file}
                        </p>
                      </td>
                      <td className="py-3 px-3 font-semibold text-slate-700">
                        {doc.issue_year}
                      </td>
                      <td className="py-3 px-3">
                        <span className="px-2 py-0.5 rounded bg-blue-50 text-[#0054A6] border border-blue-200 font-bold uppercase text-[10px]">
                          {doc.file_type}
                        </span>
                      </td>
                      <td className="py-3 px-3 font-extrabold text-emerald-700">
                        {doc.chunks_count} chunks
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <a
                            href={doc.pdf_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-2.5 py-1 rounded-md bg-[#0054A6] hover:bg-[#003f7d] text-white font-bold text-[11px]"
                          >
                            📄 Mở file gốc ↗
                          </a>
                          <a
                            href={doc.export_docx_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-2.5 py-1 rounded-md bg-amber-100 hover:bg-amber-200 text-amber-900 border border-amber-300 font-bold text-[11px]"
                          >
                            ⬇ Tải .docx
                          </a>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Form tải lên file PDF / DOCX mới và gọi POST /api/ingest */}
          <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200 flex flex-col justify-between">
            <div>
              <h2 className="text-sm font-extrabold text-[#0054A6] uppercase tracking-wider pb-3 border-b border-slate-100">
                ⚡ Nạp Văn bản Quy chế Mới (POST /api/ingest)
              </h2>
              <p className="text-xs text-slate-500 mt-2 leading-relaxed">
                Tải lên thêm file <strong>.pdf</strong> hoặc{" "}
                <strong>.docx</strong> ban hành mới của Trường Đại học Thủ Dầu
                Một (hoặc đồng bộ lại toàn bộ kho tri thức hiện có vào Qdrant).
              </p>

              <form onSubmit={handleIngestDocument} className="mt-4 space-y-3.5">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1.5">
                    Chọn file văn bản mới (.pdf / .docx - Tùy chọn):
                  </label>
                  <input
                    type="file"
                    accept=".pdf,.docx"
                    onChange={(e) =>
                      setSelectedFile(e.target.files?.[0] || null)
                    }
                    className="w-full text-xs text-slate-700 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-blue-50 file:text-[#0054A6] hover:file:bg-blue-100 border border-slate-300 rounded-xl p-1.5 bg-slate-50"
                  />
                  {selectedFile && (
                    <p className="text-[11px] text-emerald-700 font-semibold mt-1">
                      Đã chọn: {selectedFile.name} (
                      {Math.round(selectedFile.size / 1024)} KB)
                    </p>
                  )}
                </div>

                <button
                  type="submit"
                  disabled={isIngesting}
                  className="w-full py-2.5 px-4 rounded-xl bg-[#0054A6] hover:bg-[#003f7d] text-white font-bold text-xs shadow-sm transition-all disabled:opacity-50"
                >
                  {isIngesting
                    ? "Đang bóc tách & nạp vào Qdrant..."
                    : selectedFile
                    ? `📤 Tải lên & Nạp "${selectedFile.name}" vào Qdrant`
                    : "🔄 Đồng bộ & Nạp lại Kho Tri thức Qdrant"}
                </button>
              </form>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-100 text-[11px] text-slate-400">
              Pipeline tự động nhận diện bảng biểu Markdown, phân mảnh theo{" "}
              <code>Chương/Điều/Khoản</code> hoặc <code>Mục/Tiểu mục</code> và
              vector hóa vào Qdrant.
            </div>
          </div>
        </section>

        {/* 4. NHẬT KÝ TRUY VẤN & ĐÁNH GIÁ GẦN ĐÂY */}
        <section className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200">
          <h2 className="text-sm font-extrabold text-[#0054A6] uppercase tracking-wider pb-3 border-b border-slate-100">
            🕒 Nhật ký Câu hỏi & Phản hồi Đánh giá Gần đây
          </h2>

          {!analytics?.recent_queries || analytics.recent_queries.length === 0 ? (
            <p className="text-xs text-slate-400 py-6 text-center">
              Chưa có truy vấn nào được ghi nhận. Hãy đặt câu hỏi bên khung Chat
              và bấm 👍 / 👎 để xem thống kê trực tiếp.
            </p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-slate-50 text-slate-600 border-b border-slate-200 uppercase">
                    <th className="py-2.5 px-3 font-bold">Câu hỏi của Sinh viên</th>
                    <th className="py-2.5 px-3 font-bold">Nhóm Chủ đề</th>
                    <th className="py-2.5 px-3 font-bold">Trích dẫn</th>
                    <th className="py-2.5 px-3 font-bold">Đánh giá SV</th>
                    <th className="py-2.5 px-3 font-bold">Thời gian</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {analytics.recent_queries.map((q, qIdx) => (
                    <tr key={qIdx} className="hover:bg-slate-50">
                      <td className="py-2.5 px-3 font-medium text-slate-800 max-w-md truncate">
                        {q.question}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className="px-2 py-0.5 rounded-md bg-blue-50 text-[#0054A6] border border-blue-200 font-semibold text-[11px]">
                          {q.topic}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-slate-600">
                        {q.citations_count} nguồn
                      </td>
                      <td className="py-2.5 px-3">
                        {q.feedback === "like" ? (
                          <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold text-[11px]">
                            👍 Hữu ích
                          </span>
                        ) : q.feedback === "dislike" ? (
                          <span className="px-2 py-0.5 rounded bg-rose-100 text-rose-800 font-bold text-[11px]">
                            👎 Chưa chính xác
                          </span>
                        ) : (
                          <span className="text-slate-400 text-[11px]">
                            Chưa đánh giá
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-slate-400 font-mono text-[11px]">
                        {q.created_at}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

