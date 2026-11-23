"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

declare global {
  interface Window {
    google?: any;
    SpeechRecognition?: any;
    webkitSpeechRecognition?: any;
  }
}

interface Citation {
  source_file?: string;
  document_name?: string;
  doc_title?: string;
  issue_year?: string;
  file_type?: string;
  chapter?: string;
  article?: string;
  clause?: string;
  page_number?: number;
  quote?: string;
  is_table?: boolean;
}

interface ChatMessage {
  id: string;
  backendMessageId?: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  expanded_queries?: string[];
  is_safe?: boolean;
  feedback?: "like" | "dislike" | null;
  timestamp: string;
}

interface TDMUAuthUser {
  email: string;
  student_id: string;
  full_name: string;
  avatar_url?: string;
  picture?: string;
  is_tdmu_student: boolean;
  is_admin?: boolean;
}

interface ChatSessionItem {
  id: string;
  title: string;
  created_at: string;
  message_count: number;
  messages: {
    id: string;
    role: "user" | "assistant";
    content: string;
    citations: Citation[];
    is_safe: boolean;
    feedback?: "like" | "dislike" | null;
    created_at: string;
  }[];
}

const WELCOME_MESSAGE: ChatMessage = {
  id: "welcome-msg",
  role: "assistant",
  content:
    "Xin chào bạn! Tôi là **Trợ lý AI Học vụ chính thức của Trường Đại học Thủ Dầu Một (TDMU)** — ứng dụng công nghệ **Advanced RAG** chống ảo giác 100%.\n\nBạn có thể tra cứu nhanh về:\n- **Điều kiện xét và xếp hạng tốt nghiệp TDMU** (Điều 27, Điều 28)\n- **Cảnh báo học vụ & buộc thôi học** (Điều 23)\n- **Khối lượng tín chỉ đăng ký tối thiểu & học lại** (Điều 19)\n- **Bảng khối lượng tín chỉ và thời gian đào tạo chuẩn** (Điều 12, Điều 15)\n\nMọi câu trả lời đều đi kèm trích dẫn chính xác tới từng **Điều, Khoản và Số trang** văn bản quy chế. Bạn có thể bấm trực tiếp vào thẻ **Tên file / Trang PDF** ở mỗi trích dẫn để mở văn bản gốc ngay tại trang đó.",
  citations: [],
  is_safe: true,
  timestamp: "Sẵn sàng",
};

const SUGGESTED_QUESTIONS = [
  "Khi nào sinh viên TDMU bị cảnh báo kết quả học tập hoặc buộc thôi học (Điều 23)?",
  "Quy đổi số tín chỉ tích lũy và hệ số hưởng học bổng khuyến khích học tập TDMU (Hướng dẫn 03/HD-ĐHTDM)?",
  "Có những hình thức nào để hoàn thành Chuẩn đầu ra Ngoại ngữ và điểm chuẩn EPT/IELTS/TOEIC tại TDMU (Công văn 432)?",
  "Xếp hạng tốt nghiệp Xuất sắc, Giỏi, Khá và trường hợp bị giảm hạng tốt nghiệp (Điều 28)?",
  "Khối lượng tín chỉ tối thiểu phải đăng ký trong mỗi học kỳ và quy định học lại (Điều 19)?",
];

function extractMssvClientSide(email: string): string {
  const prefix = email.trim().split("@")[0] || "";
  const match = prefix.match(/(\d{7,15})/);
  return match ? match[1] : prefix.toUpperCase();
}

function buildPdfCitationUrl(
  docTitle?: string,
  pageNumber?: number,
  fileType?: string
): string {
  const trimmed = (docTitle || "").trim();
  const isDocx =
    fileType?.toLowerCase() === "docx" ||
    trimmed.toLowerCase().endsWith(".docx");
  if (isDocx) {
    return `http://127.0.0.1:8000/pdfs/${encodeURIComponent(trimmed)}`;
  }
  const safeFile = trimmed.toLowerCase().endsWith(".pdf")
    ? trimmed
    : "quy_che_dao_tao_tdmu_1774.pdf";
  const pageFragment = pageNumber ? `#page=${pageNumber}` : "";
  return `http://127.0.0.1:8000/pdfs/${encodeURIComponent(
    safeFile
  )}${pageFragment}`;
}

function buildDocxPreviewUrl(docTitle?: string): string {
  const trimmed = (docTitle || "").trim();
  return `http://127.0.0.1:8000/preview-docx/${encodeURIComponent(trimmed)}`;
}

function buildExportDocxUrl(sourceFile?: string): string {
  const trimmed = (sourceFile || "").trim() || "quy_che_dao_tao_tdmu_1774.pdf";
  return `http://127.0.0.1:8000/export-docx/${encodeURIComponent(trimmed)}`;
}

function stripMarkdownForSpeech(markdownText: string): string {
  return (markdownText || "")
    .replace(/\|[-:\s|]+\|/g, " ")
    .replace(/\|/g, ", ")
    .replace(/[*_~`#>]+/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function splitCleanTextIntoTtsSegments(
  cleanText: string,
  targetChunkLen: number = 250
): string[] {
  const normalized = (cleanText || "").trim();
  if (!normalized) return [];

  // Tách theo ranh giới câu (. ; ! ? hoặc xuống dòng) để câu đọc tự nhiên, mỗi đoạn ~200-300 ký tự
  const rawSentences = normalized
    .split(/(?<=[\.\!\?\;\:])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);

  const segments: string[] = [];
  let current = "";

  for (const sentence of rawSentences) {
    if (sentence.length > 450) {
      if (current) {
        segments.push(current);
        current = "";
      }
      // Nếu 1 câu quá dài, tách nhỏ theo dấu phẩy
      const commaParts = sentence.split(/,\s+/);
      let subBuf = "";
      for (const part of commaParts) {
        const candidate = subBuf ? `${subBuf}, ${part}` : part;
        if (candidate.length > targetChunkLen && subBuf) {
          segments.push(subBuf.trim());
          subBuf = part;
        } else {
          subBuf = candidate;
        }
      }
      if (subBuf.trim()) {
        segments.push(subBuf.trim());
      }
      continue;
    }

    const candidate = current ? `${current} ${sentence}` : sentence;
    if (candidate.length > targetChunkLen && current) {
      segments.push(current.trim());
      current = sentence;
    } else {
      current = candidate;
    }
  }

  if (current.trim()) {
    segments.push(current.trim());
  }

  // Giới hạn tối đa 6 đoạn đầu (~1.500 ký tự) để phát nhanh và trọn ý chính
  return segments.slice(0, 6);
}

async function convertAudioBlobToWavBase64(blob: Blob): Promise<string> {
  try {
    const arrayBuffer = await blob.arrayBuffer();
    const AudioCtx =
      window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioCtx) {
      throw new Error("No AudioContext");
    }
    const audioCtx = new AudioCtx({ sampleRate: 16000 });
    const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
    const channelData = audioBuffer.getChannelData(0);
    const sampleRate = audioBuffer.sampleRate;
    const numSamples = channelData.length;

    const wavBuffer = new ArrayBuffer(44 + numSamples * 2);
    const view = new DataView(wavBuffer);
    const writeStr = (offset: number, str: string) => {
      for (let i = 0; i < str.length; i++) {
        view.setUint8(offset + i, str.charCodeAt(i));
      }
    };

    writeStr(0, "RIFF");
    view.setUint32(4, 36 + numSamples * 2, true);
    writeStr(8, "WAVE");
    writeStr(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, 1, true); // Mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(36, "data");
    view.setUint32(40, numSamples * 2, true);

    let offset = 44;
    for (let i = 0; i < numSamples; i++, offset += 2) {
      const s = Math.max(-1, Math.min(1, channelData[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    await audioCtx.close().catch(() => { });

    const bytes = new Uint8Array(wavBuffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  } catch {
    return await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const res = String(reader.result || "");
        resolve(res.includes(",") ? res.split(",", 2)[1] : res);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }
}

function MarkdownContent({
  content,
  isUser = false,
  compact = false,
}: {
  content: string;
  isUser?: boolean;
  compact?: boolean;
}) {
  return (
    <div
      className={compact ? "text-xs leading-relaxed" : "text-sm leading-relaxed"}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => (
            <p className="mb-2.5 last:mb-0 whitespace-pre-line">{children}</p>
          ),
          strong: ({ children }) => (
            <strong
              className={`font-bold ${isUser ? "text-amber-200" : "text-[#0054A6]"
                }`}
            >
              {children}
            </strong>
          ),
          ul: ({ children }) => (
            <ul className="list-disc pl-5 mb-2.5 space-y-1">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-5 mb-2.5 space-y-1">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto rounded-xl border border-blue-200 shadow-sm bg-white">
              <table className="min-w-full divide-y divide-blue-100 text-left text-xs sm:text-sm">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-[#0054A6]/10 text-[#0054A6] font-bold uppercase tracking-wider text-xs">
              {children}
            </thead>
          ),
          tbody: ({ children }) => (
            <tbody className="divide-y divide-slate-200 bg-white text-slate-800">
              {children}
            </tbody>
          ),
          tr: ({ children }) => (
            <tr className="hover:bg-blue-50/40 transition-colors">{children}</tr>
          ),
          th: ({ children }) => (
            <th className="px-3.5 py-2.5 font-bold border-r border-blue-100 last:border-r-0">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3.5 py-2 border-r border-slate-100 last:border-r-0 align-top">
              {children}
            </td>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-[#0054A6] bg-blue-50/50 pl-3 py-1.5 my-2 italic text-slate-700 rounded-r">
              {children}
            </blockquote>
          ),
          code: ({ children }) => (
            <code
              className={`px-1.5 py-0.5 rounded font-mono text-xs ${isUser
                  ? "bg-blue-800 text-amber-200"
                  : "bg-slate-100 text-[#0054A6] border border-slate-200"
                }`}
            >
              {children}
            </code>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default function HomePage() {
  // --- STATE XÁC THỰC GOOGLE OAUTH THỰC TẾ (@student.tdmu.edu.vn) & LỊCH SỬ HỘI THOẠI ---
  const [authUser, setAuthUser] = useState<TDMUAuthUser | null>(null);
  const [authStatusNotice, setAuthStatusNotice] = useState<string | null>(null);
  const [showAuthModal, setShowAuthModal] = useState<boolean>(false);
  const [authModalError, setAuthModalError] = useState<string | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState<boolean>(false);
  const [isGisButtonRendered, setIsGisButtonRendered] =
    useState<boolean>(false);
  const googleClientId = (
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || ""
  ).trim();

  // Quản lý Phiên chat & Sidebar lịch sử
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [chatSessions, setChatSessions] = useState<ChatSessionItem[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false);

  // --- STATE RAG CHAT & GIỌNG NÓI ĐA PHƯƠNG THỨC (HYBRID VOICE INPUT & TTS) ---
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [isListeningVoice, setIsListeningVoice] = useState<boolean>(false);
  const [voiceStatusHint, setVoiceStatusHint] = useState<string | null>(null);
  const [speakingMessageId, setSpeakingMessageId] = useState<string | null>(
    null
  );
  const [isLoadingTts, setIsLoadingTts] = useState<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const googleButtonContainerRef = useRef<HTMLDivElement | null>(null);
  const speechRecognitionRef = useRef<any>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recordingTimeoutRef = useRef<any>(null);
  const ttsAudioRef = useRef<HTMLAudioElement | null>(null);
  const ttsAbortRef = useRef<AbortController | null>(null);
  const ttsPlaybackSessionRef = useRef<number>(0);
  // Client-side Blob URL cache theo từng đoạn văn bản hoặc từng tin nhắn để bấm nghe lại không cần gọi lại API
  const ttsSegmentBlobUrlCacheRef = useRef<Map<string, string>>(new Map());
  const ttsMessageSegmentsCacheRef = useRef<Map<string, string[]>>(new Map());

  // --- HÀM TẢI LỊCH SỬ PHIÊN CHAT TỪ BACKEND (`GET /api/chat/history`) ---
  const fetchChatHistory = useCallback(async (email: string) => {
    if (!email) return;
    setIsLoadingHistory(true);
    try {
      const res = await fetch(
        `http://127.0.0.1:8000/api/chat/history?email=${encodeURIComponent(
          email
        )}`
      );
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.sessions)) {
          setChatSessions(data.sessions);
        }
      }
    } catch {
      // Giữ nguyên danh sách nếu không kết nối được
    } finally {
      setIsLoadingHistory(false);
    }
  }, []);

  // Khôi phục phiên đăng nhập sinh viên TDMU từ localStorage khi mở trang
  useEffect(() => {
    try {
      const saved = localStorage.getItem("tdmu_oauth_user");
      if (saved) {
        const parsed: TDMUAuthUser = JSON.parse(saved);
        if (
          parsed &&
          parsed.email &&
          parsed.email.toLowerCase().endsWith("@student.tdmu.edu.vn")
        ) {
          const normalizedUser: TDMUAuthUser = {
            ...parsed,
            is_admin:
              parsed.email.toLowerCase() ===
              "2224801030361@student.tdmu.edu.vn",
          };
          setAuthUser(normalizedUser);
          fetchChatHistory(normalizedUser.email);
        }
      }
    } catch {
      // Ignore storage error
    }
  }, [fetchChatHistory]);

  // Nạp Google Identity Services (GIS) SDK (`https://accounts.google.com/gsi/client`) với hosted_domain="student.tdmu.edu.vn"
  useEffect(() => {
    if (!showAuthModal) {
      setIsGisButtonRendered(false);
      return;
    }

    const hasValidClientId = Boolean(
      googleClientId &&
      googleClientId !==
      "your_google_oauth_client_id.apps.googleusercontent.com"
    );
    if (!hasValidClientId) {
      setIsGisButtonRendered(false);
      return;
    }

    const existingScript = document.getElementById("google-gis-script");
    const initGis = () => {
      if (window.google?.accounts?.id && googleButtonContainerRef.current) {
        try {
          window.google.accounts.id.initialize({
            client_id: googleClientId,
            hd: "student.tdmu.edu.vn",
            hosted_domain: "student.tdmu.edu.vn",
            callback: async (response: any) => {
              if (response?.credential) {
                await verifyGoogleAccountWithBackend({
                  credential: response.credential,
                });
              }
            },
          });
          googleButtonContainerRef.current.innerHTML = "";
          window.google.accounts.id.renderButton(
            googleButtonContainerRef.current,
            {
              theme: "filled_blue",
              size: "large",
              text: "continue_with",
              shape: "pill",
              width: 340,
            }
          );
          setIsGisButtonRendered(true);
        } catch {
          setIsGisButtonRendered(false);
        }
      } else {
        setIsGisButtonRendered(false);
      }
    };

    if (!existingScript) {
      const script = document.createElement("script");
      script.id = "google-gis-script";
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.onload = initGis;
      script.onerror = () => setIsGisButtonRendered(false);
      document.body.appendChild(script);
    } else {
      initGis();
    }
  }, [showAuthModal, googleClientId]);

  // Cuộn tự động xuống tin nhắn mới nhất
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // --- XỬ LÝ XÁC THỰC GOOGLE OAUTH ID TOKEN THỰC TẾ & DOMAIN GUARD (`@student.tdmu.edu.vn`) ---
  const verifyGoogleAccountWithBackend = async (payload: {
    credential?: string;
    access_token?: string;
  }) => {
    setIsAuthenticating(true);
    setAuthStatusNotice(null);
    setAuthModalError(null);

    try {
      const res = await fetch("http://127.0.0.1:8000/api/auth/google", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        const msg =
          data.detail ||
          data.message ||
          `Xác thực Google OAuth bị từ chối (HTTP ${res.status})`;
        setAuthModalError(msg);
        return;
      }

      const verifiedUser: TDMUAuthUser = {
        email: data.email,
        student_id: data.student_id || extractMssvClientSide(data.email),
        full_name: data.full_name || `Sinh viên TDMU (${data.student_id})`,
        avatar_url: data.picture || data.avatar_url,
        picture: data.picture || data.avatar_url,
        is_tdmu_student: true,
        is_admin: Boolean(data.is_admin),
      };

      setAuthUser(verifiedUser);
      localStorage.setItem("tdmu_oauth_user", JSON.stringify(verifiedUser));
      setAuthStatusNotice(data.message);
      setShowAuthModal(false);
      setIsSidebarOpen(true);
      await fetchChatHistory(verifiedUser.email);
    } catch (err: any) {
      setAuthModalError(
        err?.message || "Không thể kết nối Backend để xác thực Google OAuth."
      );
    } finally {
      setIsAuthenticating(false);
    }
  };

  // Mở hộp thoại chọn tài khoản Google OAuth2 Popup (khi bấm nút Continue with Google tùy chỉnh)
  const handleTriggerGooglePopupLogin = () => {
    setAuthModalError(null);
    if (
      !googleClientId ||
      googleClientId === "your_google_oauth_client_id.apps.googleusercontent.com"
    ) {
      setAuthModalError(
        "Chưa cấu hình biến môi trường NEXT_PUBLIC_GOOGLE_CLIENT_ID. Vui lòng khai báo Google OAuth Client ID trong file .env để bật cửa sổ chọn tài khoản Google."
      );
      return;
    }

    if (window.google?.accounts?.oauth2) {
      const tokenClient = window.google.accounts.oauth2.initTokenClient({
        client_id: googleClientId,
        scope: "openid email profile",
        hint: "@student.tdmu.edu.vn",
        hosted_domain: "student.tdmu.edu.vn",
        callback: async (tokenResponse: any) => {
          if (tokenResponse?.access_token) {
            await verifyGoogleAccountWithBackend({
              access_token: tokenResponse.access_token,
            });
          } else if (tokenResponse?.error) {
            setAuthModalError(
              `Google OAuth Popup: ${tokenResponse.error_description || tokenResponse.error}`
            );
          }
        },
      });
      tokenClient.requestAccessToken({ prompt: "select_account" });
      return;
    }

    if (window.google?.accounts?.id) {
      window.google.accounts.id.prompt();
    } else {
      setAuthModalError(
        "Đang tải thư viện Google Identity Services (https://accounts.google.com/gsi/client). Vui lòng thử lại sau 1 giây."
      );
    }
  };

  const handleLogout = () => {
    setAuthUser(null);
    setChatSessions([]);
    setCurrentSessionId(null);
    setMessages([WELCOME_MESSAGE]);
    localStorage.removeItem("tdmu_oauth_user");
    setAuthStatusNotice(
      "Đã đăng xuất tài khoản sinh viên TDMU. Hệ thống chuyển về Chế độ Khách (Không lưu lịch sử chat)."
    );
  };

  // --- QUẢN LÝ PHIÊN CHAT TRÊN SIDEBAR ---
  const handleStartNewSession = () => {
    setCurrentSessionId(null);
    setMessages([WELCOME_MESSAGE]);
    setErrorBanner(null);
  };

  const handleSelectSession = (session: ChatSessionItem) => {
    setCurrentSessionId(session.id);
    if (!session.messages || session.messages.length === 0) {
      setMessages([WELCOME_MESSAGE]);
      return;
    }

    const loadedMessages: ChatMessage[] = session.messages.map((m) => ({
      id: `db-${m.id}`,
      backendMessageId: String(m.id),
      role: m.role,
      content: m.content,
      citations: m.citations || [],
      is_safe: m.is_safe,
      feedback: m.feedback ?? null,
      timestamp: m.created_at.slice(11, 16) || "Đã lưu",
    }));
    setMessages([WELCOME_MESSAGE, ...loadedMessages]);
  };

  // --- TÍNH NĂNG NHẬP GIỌNG NÓI 2 TẦNG (HYBRID VOICE INPUT: WEB SPEECH API + MEDIARECORDER FALLBACK CHO EDGE) ---
  const stopFallbackMediaRecorder = () => {
    if (recordingTimeoutRef.current) {
      clearTimeout(recordingTimeoutRef.current);
      recordingTimeoutRef.current = null;
    }
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state !== "inactive"
    ) {
      mediaRecorderRef.current.stop();
    }
  };

  const startFallbackMediaRecorder = async (reasonHint?: string) => {
    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices ||
      !navigator.mediaDevices.getUserMedia
    ) {
      setIsListeningVoice(false);
      setErrorBanner(
        "Trình duyệt không cấp quyền truy cập Micro (getUserMedia). Vui lòng kiểm tra quyền Micro trên thanh địa chỉ."
      );
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      const chunks: BlobPart[] = [];
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (ev) => {
        if (ev.data && ev.data.size > 0) {
          chunks.push(ev.data);
        }
      };

      recorder.onstart = () => {
        setIsListeningVoice(true);
        setVoiceStatusHint(
          reasonHint ||
          "🎙️ Đang ghi âm giọng nói (tối đa 15 giây)... Hãy nói câu hỏi và bấm lại nút 🎙️ để hoàn tất."
        );
      };

      recorder.onstop = async () => {
        setIsListeningVoice(false);
        if (mediaStreamRef.current) {
          mediaStreamRef.current.getTracks().forEach((t) => t.stop());
          mediaStreamRef.current = null;
        }
        const blob = new Blob(chunks, {
          type: recorder.mimeType || "audio/webm",
        });
        if (blob.size < 200) {
          setVoiceStatusHint(null);
          return;
        }

        setVoiceStatusHint(
          "⏳ Đang chuyển đổi giọng nói sang văn bản tiếng Việt tại máy chủ..."
        );
        try {
          const wavB64 = await convertAudioBlobToWavBase64(blob);
          const res = await fetch(
            "http://127.0.0.1:8000/api/speech-to-text",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                filename: "voice_query.wav",
                audio_base64: wavB64,
              }),
            }
          );
          const data = await res.json().catch(() => ({}));
          if (res.ok && data.text && String(data.text).trim()) {
            const recognized = String(data.text).trim();
            setInput((prev) =>
              prev.trim() ? `${prev.trim()} ${recognized}` : recognized
            );
            setVoiceStatusHint(`✓ Đã nhận diện giọng nói: “${recognized}”`);
          } else {
            setVoiceStatusHint(null);
            setErrorBanner(
              data.message ||
              data.detail ||
              "Không nhận diện được câu nói rõ ràng từ Micro. Vui lòng nói to hơn hoặc kiểm tra kết nối Micro."
            );
          }
        } catch (err: any) {
          setVoiceStatusHint(null);
          setErrorBanner(
            err?.message ||
            "Không thể kết nối tới endpoint /api/speech-to-text để nhận diện giọng nói."
          );
        }
      };

      recorder.start();
      recordingTimeoutRef.current = setTimeout(() => {
        stopFallbackMediaRecorder();
      }, 15000);
    } catch {
      setIsListeningVoice(false);
      setVoiceStatusHint(null);
      setErrorBanner(
        "Trình duyệt đã từ chối quyền truy cập Micro. Vui lòng bấm vào biểu tượng ổ khóa trên thanh địa chỉ để Cho phép (Allow) Micro."
      );
    }
  };

  const handleToggleVoiceInput = () => {
    if (typeof window === "undefined") return;

    // Nếu đang nghe hoặc đang ghi âm dự phòng -> Bấm lần nữa để dừng và xử lý ngay
    if (isListeningVoice) {
      if (
        mediaRecorderRef.current &&
        mediaRecorderRef.current.state !== "inactive"
      ) {
        stopFallbackMediaRecorder();
        return;
      }
      if (speechRecognitionRef.current) {
        try {
          speechRecognitionRef.current.stop();
        } catch { }
      }
      setIsListeningVoice(false);
      setVoiceStatusHint(null);
      return;
    }

    setErrorBanner(null);
    const SpeechRecognitionAPI =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    // Nếu trình duyệt không có Web Speech API -> Chuyển thẳng sang MediaRecorder + Backend STT
    if (!SpeechRecognitionAPI) {
      startFallbackMediaRecorder(
        "🎙️ Đang ghi âm giọng nói qua Micro (tối đa 15 giây)... Bấm lại nút 🎙️ khi nói xong."
      );
      return;
    }

    try {
      const recognition = new SpeechRecognitionAPI();
      recognition.lang = "vi-VN";
      recognition.continuous = false;
      recognition.interimResults = false;

      recognition.onstart = () => {
        setIsListeningVoice(true);
        setVoiceStatusHint(
          "🎙️ Đang lắng nghe giọng nói tiếng Việt (vi-VN)... Hãy nói câu hỏi của bạn."
        );
      };

      recognition.onresult = (event: any) => {
        const transcript = event?.results?.[0]?.[0]?.transcript || "";
        if (transcript.trim()) {
          setInput((prev) =>
            prev.trim()
              ? `${prev.trim()} ${transcript.trim()}`
              : transcript.trim()
          );
          setVoiceStatusHint(
            `✓ Đã nhận diện giọng nói: “${transcript.trim()}”`
          );
        }
      };

      recognition.onerror = (event: any) => {
        const errCode = event?.error || "unknown";
        speechRecognitionRef.current = null;

        if (errCode === "not-allowed" || errCode === "service-not-allowed") {
          setIsListeningVoice(false);
          setVoiceStatusHint(null);
          setErrorBanner(
            "Trình duyệt đã từ chối quyền sử dụng Micro (not-allowed). Vui lòng cho phép quyền Micro trên thanh địa chỉ trình duyệt."
          );
          return;
        }

        // Trên Microsoft Edge, webkitSpeechRecognition thường báo lỗi 'network' -> Tự động chuyển sang tầng 2 (MediaRecorder + Backend STT)
        if (
          errCode === "network" ||
          errCode === "audio-capture" ||
          errCode === "aborted"
        ) {
          startFallbackMediaRecorder(
            `⚠️ Web Speech API của trình duyệt báo lỗi (${errCode}) — Đã tự động chuyển sang chế độ Ghi âm dự phòng (tối đa 15 giây). Hãy nói câu hỏi và bấm lại 🎙️ để hoàn tất!`
          );
          return;
        }

        setIsListeningVoice(false);
        setVoiceStatusHint(null);
        setErrorBanner(
          `Không nhận diện được giọng nói (${errCode}). Bạn có thể bấm lại nút 🎙️ để thử lại.`
        );
      };

      recognition.onend = () => {
        if (
          !mediaRecorderRef.current ||
          mediaRecorderRef.current.state === "inactive"
        ) {
          setIsListeningVoice(false);
        }
      };

      speechRecognitionRef.current = recognition;
      recognition.start();
    } catch {
      startFallbackMediaRecorder(
        "🎙️ Đang ghi âm giọng nói dự phòng (tối đa 15 giây)... Bấm lại nút 🎙️ khi nói xong."
      );
    }
  };

  // --- TÍNH NĂNG ĐỌC TO CÂU TRẢ LỜI CUỐN CHIẾU TỪNG ĐOẠN + PREFETCH + CACHE BLOB URL (`POST /api/tts`) ---
  const stopCurrentTtsPlayback = () => {
    ttsPlaybackSessionRef.current += 1;
    if (ttsAbortRef.current) {
      try {
        ttsAbortRef.current.abort();
      } catch { }
      ttsAbortRef.current = null;
    }
    if (ttsAudioRef.current) {
      try {
        ttsAudioRef.current.pause();
        ttsAudioRef.current.currentTime = 0;
      } catch { }
      ttsAudioRef.current = null;
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
      } catch { }
    }
    setIsLoadingTts(false);
  };

  const fetchSegmentBlobUrl = async (
    segmentText: string,
    signal: AbortSignal
  ): Promise<string> => {
    const cacheKey = segmentText.trim();
    const cachedUrl = ttsSegmentBlobUrlCacheRef.current.get(cacheKey);
    if (cachedUrl) {
      return cachedUrl;
    }

    const response = await fetch("http://127.0.0.1:8000/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: cacheKey }),
      signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const audioBlob = await response.blob();
    const objectUrl = URL.createObjectURL(audioBlob);
    ttsSegmentBlobUrlCacheRef.current.set(cacheKey, objectUrl);
    return objectUrl;
  };

  const handleToggleSpeakAnswer = async (
    msgId: string,
    markdownContent: string
  ) => {
    if (typeof window === "undefined") return;

    // Nếu đang tải hoặc đang đọc chính tin nhắn này -> Bấm lần nữa để dừng ngay lập tức
    if (speakingMessageId === msgId) {
      stopCurrentTtsPlayback();
      setSpeakingMessageId(null);
      return;
    }

    // Tự động ngắt âm thanh cũ nếu đang phát tin nhắn khác
    stopCurrentTtsPlayback();

    const cleanText = stripMarkdownForSpeech(markdownContent);
    if (!cleanText) return;

    const segments = splitCleanTextIntoTtsSegments(cleanText, 240);
    if (segments.length === 0) return;

    const currentSessionToken = ttsPlaybackSessionRef.current;
    setSpeakingMessageId(msgId);
    setIsLoadingTts(true);

    const abortController = new AbortController();
    ttsAbortRef.current = abortController;

    try {
      // Kiểm tra xem toàn bộ danh sách Blob URL của tin nhắn này đã được cache ở client chưa
      const cachedMsgUrls = ttsMessageSegmentsCacheRef.current.get(msgId);
      const resolvedUrls: (string | null)[] = new Array(segments.length).fill(
        null
      );
      if (cachedMsgUrls && cachedMsgUrls.length === segments.length) {
        for (let i = 0; i < segments.length; i++) {
          resolvedUrls[i] = cachedMsgUrls[i];
        }
      }

      // Khởi tạo promise tải đoạn đầu tiên ngay lập tức (~1-2 giây)
      const segmentPromises: Promise<string>[] = [];
      segmentPromises[0] = resolvedUrls[0]
        ? Promise.resolve(resolvedUrls[0]!)
        : fetchSegmentBlobUrl(segments[0], abortController.signal);

      for (let idx = 0; idx < segments.length; idx++) {
        if (
          abortController.signal.aborted ||
          ttsPlaybackSessionRef.current !== currentSessionToken
        ) {
          return;
        }

        // Trong lúc chuẩn bị phát đoạn `idx`, tự động tải trước (prefetch) đoạn `idx + 1` ở chế độ nền
        if (idx + 1 < segments.length && !segmentPromises[idx + 1]) {
          segmentPromises[idx + 1] = resolvedUrls[idx + 1]
            ? Promise.resolve(resolvedUrls[idx + 1]!)
            : fetchSegmentBlobUrl(segments[idx + 1], abortController.signal);
        }

        const segUrl = await segmentPromises[idx];
        resolvedUrls[idx] = segUrl;

        if (
          abortController.signal.aborted ||
          ttsPlaybackSessionRef.current !== currentSessionToken
        ) {
          return;
        }

        // Ngay khi đoạn đầu tiên sẵn sàng -> Tắt trạng thái "⏳ Đang tạo giọng đọc..." và chuyển sang "⏹ Dừng đọc"
        if (idx === 0) {
          setIsLoadingTts(false);
        }

        await new Promise<void>((resolve, reject) => {
          const audio = new Audio(segUrl);
          ttsAudioRef.current = audio;

          audio.onended = () => {
            ttsAudioRef.current = null;
            resolve();
          };
          audio.onerror = () => {
            ttsAudioRef.current = null;
            reject(new Error("Audio playback error"));
          };
          audio.play().catch(reject);
        });
      }

      // Lưu cache danh sách Blob URL cho msgId để bấm nghe lại phát tức thì (0 ms)
      if (resolvedUrls.every((u) => typeof u === "string" && u.length > 0)) {
        ttsMessageSegmentsCacheRef.current.set(
          msgId,
          resolvedUrls as string[]
        );
      }

      if (ttsPlaybackSessionRef.current === currentSessionToken) {
        setSpeakingMessageId((curr) => (curr === msgId ? null : curr));
        setIsLoadingTts(false);
      }
    } catch (err: any) {
      if (
        err?.name === "AbortError" ||
        ttsPlaybackSessionRef.current !== currentSessionToken
      ) {
        return;
      }
      setIsLoadingTts(false);

      // Phương án dự phòng cuối cùng: window.speechSynthesis nếu mất kết nối mạng hoặc Backend ngoại tuyến
      if ("speechSynthesis" in window) {
        try {
          const utterance = new SpeechSynthesisUtterance(cleanText);
          utterance.lang = "vi-VN";
          utterance.rate = 1.02;
          const voices = window.speechSynthesis.getVoices();
          const viVoice = voices.find((v) =>
            v.lang?.toLowerCase().includes("vi")
          );
          if (viVoice) {
            utterance.voice = viVoice;
          }
          utterance.onend = () => {
            setSpeakingMessageId((curr) => (curr === msgId ? null : curr));
          };
          utterance.onerror = () => {
            setSpeakingMessageId((curr) => (curr === msgId ? null : curr));
          };
          window.speechSynthesis.speak(utterance);
          return;
        } catch { }
      }
      setSpeakingMessageId(null);
      setErrorBanner(
        "Không thể phát âm thanh câu trả lời. Vui lòng kiểm tra kết nối tới máy chủ Backend TDMU."
      );
    }
  };

  // --- TÍNH NĂNG ĐÁNH GIÁ MỨC ĐỘ HÀI LÒNG (👍 HỮU ÍCH / 👎 CHƯA CHÍNH XÁC) ---
  const handleFeedback = async (
    msg: ChatMessage,
    targetFeedback: "like" | "dislike"
  ) => {
    const newFeedback: "like" | "dislike" | null =
      msg.feedback === targetFeedback ? null : targetFeedback;

    setMessages((prev) =>
      prev.map((item) =>
        item.id === msg.id ? { ...item, feedback: newFeedback } : item
      )
    );

    const targetMessageId = msg.backendMessageId || msg.id;
    try {
      await fetch(
        `http://127.0.0.1:8000/api/messages/${encodeURIComponent(
          targetMessageId
        )}/feedback`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ feedback: newFeedback }),
        }
      );
    } catch {
      // Giữ trạng thái UI mượt mà ngay cả khi mạng gián đoạn tạm thời
    }
  };

  const handleDeleteSession = async (
    sessionId: string,
    e: React.MouseEvent
  ) => {
    e.stopPropagation();
    if (!authUser) return;

    try {
      await fetch(
        `http://127.0.0.1:8000/api/chat/session/${encodeURIComponent(
          sessionId
        )}?email=${encodeURIComponent(authUser.email)}`,
        {
          method: "DELETE",
        }
      );
      setChatSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (currentSessionId === sessionId) {
        setCurrentSessionId(null);
        setMessages([WELCOME_MESSAGE]);
      }
    } catch {
      setErrorBanner("Không thể xóa phiên hội thoại trên máy chủ.");
    }
  };

  // --- HÀM GỬI CÂU HỎI RAG CHAT ---
  const sendMessage = async (textToSend?: string) => {
    const trimmed = (textToSend ?? input).trim();
    if (!trimmed || isLoading) return;

    const nowStr = new Date().toLocaleTimeString("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
    });

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
      timestamp: nowStr,
    };

    setMessages((prev) => [...prev, userMsg]);
    if (textToSend === undefined) {
      setInput("");
    }
    setIsLoading(true);
    setErrorBanner(null);

    try {
      const response = await fetch("http://127.0.0.1:8000/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: trimmed,
          user_email: authUser?.email || null,
          user_name: authUser?.full_name || null,
          session_id: currentSessionId,
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(
          errData.detail || `Lỗi kết nối máy chủ (HTTP ${response.status})`
        );
      }

      const data = await response.json();

      const botMsg: ChatMessage = {
        id: `bot-${Date.now()}`,
        backendMessageId: data.message_id || `bot-${Date.now()}`,
        role: "assistant",
        content:
          data.answer || "Không nhận được nội dung phản hồi từ hệ thống RAG.",
        citations: Array.isArray(data.citations) ? data.citations : [],
        expanded_queries: Array.isArray(data.expanded_queries)
          ? data.expanded_queries
          : [],
        is_safe: typeof data.is_safe === "boolean" ? data.is_safe : true,
        feedback: null,
        timestamp: new Date().toLocaleTimeString("vi-VN", {
          hour: "2-digit",
          minute: "2-digit",
        }),
      };

      setMessages((prev) => [...prev, botMsg]);

      if (data.session_id) {
        setCurrentSessionId(data.session_id);
      }
      if (authUser?.email && data.persisted) {
        await fetchChatHistory(authUser.email);
      }
    } catch (err: any) {
      const errMessage =
        err?.message ||
        "Không thể kết nối tới Backend tại http://127.0.0.1:8000/api/chat";
      setErrorBanner(errMessage);
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content: `⚠️ Không thể kết nối đến máy chủ Backend TDMU (http://127.0.0.1:8000/api/chat). Chi tiết: ${errMessage}`,
          citations: [],
          is_safe: false,
          timestamp: nowStr,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const userInitials = authUser?.full_name
    ? authUser.full_name
      .split(" ")
      .filter(Boolean)
      .slice(-2)
      .map((w) => w[0]?.toUpperCase())
      .join("")
    : "SV";

  return (
    <div className="flex flex-col h-screen bg-slate-100 text-slate-900">
      {/* HEADER NHẬN DIỆN THƯƠNG HIỆU TRƯỜNG ĐẠI HỌC THỦ DẦU MỘT (TDMU - #0054A6) */}
      <header className="bg-[#0054A6] text-white shadow-lg border-b-4 border-amber-400 px-4 py-3.5 shrink-0">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          {/* Thương hiệu TDMU */}
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-xl bg-white text-[#0054A6] border-2 border-amber-300 flex flex-col items-center justify-center font-extrabold shadow-md shrink-0">
              <span className="text-xs leading-none tracking-tighter">TDMU</span>
              <span className="text-[10px] font-semibold text-amber-600 mt-0.5">
                AI RAG
              </span>
            </div>
            <div>
              <p className="text-[11px] sm:text-xs font-extrabold uppercase tracking-widest text-amber-300">
                TRƯỜNG ĐẠI HỌC THỦ DẦU MỘT (TDMU)
              </p>
              <h1 className="text-base sm:text-xl font-bold tracking-tight text-white mt-0.5">
                Trợ lý Trí tuệ Nhân tạo Hỗ trợ Thông tin Học vụ
              </h1>
            </div>
          </div>

          {/* GÓC TRÊN BÊN PHẢI HEADER: CHỈ HIỂN THỊ NÚT QUẢN TRỊ (/admin) KHI user.is_admin === true (2224801030361@student.tdmu.edu.vn) */}
          <div className="flex flex-wrap items-center justify-end gap-2.5">
            {authUser && authUser.is_admin === true && (
              <Link
                href="/admin"
                className="px-3 py-2 rounded-xl bg-[#003f7d] hover:bg-[#002f5e] text-amber-300 font-bold text-xs shadow-sm transition-all flex items-center gap-1.5 border border-amber-300/50"
              >
                <span>📊</span>
                <span>Quản trị & Thống kê</span>
              </Link>
            )}
            {!authUser ? (
              <button
                type="button"
                onClick={() => {
                  setAuthModalError(null);
                  setShowAuthModal(true);
                }}
                className="px-3.5 py-2 rounded-xl bg-white hover:bg-blue-50 text-[#0054A6] font-bold text-xs shadow-md transition-all flex items-center gap-2 border border-amber-300"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24">
                  <path
                    fill="#EA4335"
                    d="M12 5c1.6 0 3 .6 4.1 1.7l3.1-3.1C17.3 1.8 14.8 1 12 1 7.4 1 3.5 3.6 1.6 7.4l3.7 2.8C6.2 7.2 8.9 5 12 5z"
                  />
                  <path
                    fill="#4285F4"
                    d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5c-.3 1.5-1.1 2.8-2.4 3.6l3.7 2.9c2.2-2 3.7-5 3.7-8.7z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.3 14.8c-.2-.8-.4-1.6-.4-2.5s.2-1.7.4-2.5L1.6 7C.6 9 0 11.2 0 13.5s.6 4.5 1.6 6.5l3.7-2.9z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 24c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3.1 0-5.8-2.1-6.7-5l-3.7 2.9C3.5 21.4 7.4 24 12 24z"
                  />
                </svg>
                <span>Đăng nhập bằng Google (@student.tdmu.edu.vn)</span>
              </button>
            ) : (
              <div className="flex items-center gap-3 bg-[#003f7d] px-3.5 py-1.5 rounded-xl border border-amber-300/40 shadow-inner">
                {/* Avatar Sinh viên */}
                <div className="w-8 h-8 rounded-full bg-amber-400 text-[#003f7d] font-extrabold text-xs flex items-center justify-center shrink-0 border border-white">
                  {userInitials}
                </div>
                <div className="text-xs leading-tight">
                  <div className="flex items-center gap-1.5">
                    <strong className="text-white font-bold">
                      {authUser.full_name}
                    </strong>
                    <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-200 border border-emerald-400/30 text-[10px] font-bold">
                      MSSV: {authUser.student_id}
                    </span>
                    {authUser.is_admin && (
                      <span className="px-1.5 py-0.5 rounded bg-amber-400 text-[#003f7d] text-[10px] font-extrabold">
                        ADMIN
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-blue-200 font-mono">
                    {authUser.email}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="ml-1 px-2.5 py-1 rounded-lg bg-red-500/20 hover:bg-red-500/40 text-red-100 border border-red-400/30 text-xs font-semibold transition-colors"
                >
                  Đăng xuất
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* MODAL ĐĂNG NHẬP GOOGLE OAUTH THỰC TẾ (GOOGLE IDENTITY SERVICES - KHÔNG CÓ Ô NHẬP TAY GIẢ LẬP) */}
      {showAuthModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-blue-100">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-xl bg-[#0054A6] text-white font-extrabold text-xs flex items-center justify-center">
                  TDMU
                </div>
                <div>
                  <h3 className="text-sm font-extrabold text-slate-900">
                    Đăng nhập Google OAuth Sinh viên TDMU
                  </h3>
                  <p className="text-[11px] text-slate-500">
                    Xác thực chữ ký số Google ID Token với{" "}
                    <code className="text-[#0054A6] font-bold">
                      @student.tdmu.edu.vn
                    </code>
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowAuthModal(false)}
                className="text-slate-400 hover:text-slate-700 font-bold text-sm px-2"
              >
                ✕
              </button>
            </div>

            <div className="mt-4 space-y-4 text-xs">
              <div className="bg-blue-50/80 border border-blue-200 rounded-xl p-3 text-slate-700 leading-relaxed">
                <p className="font-bold text-[#0054A6] mb-1">
                  🔒 Xác thực Google Identity Services & Domain Guard:
                </p>
                <ul className="list-disc pl-4 space-y-1">
                  <li>
                    Hệ thống xác thực trực tiếp <strong>Google ID Token</strong>{" "}
                    từ tài khoản Google của bạn (bắt buộc mật khẩu & bảo mật 2
                    lớp của Google).
                  </li>
                  <li>
                    Chỉ chấp nhận tài khoản thuộc tên miền{" "}
                    <strong>@student.tdmu.edu.vn</strong> để lưu lịch sử chat
                    theo MSSV. Tài khoản <code>@gmail.com</code> cá nhân sẽ bị
                    từ chối (403).
                  </li>
                </ul>
              </div>

              {authModalError && (
                <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-3 text-xs font-medium leading-relaxed">
                  ⚠️ {authModalError}
                </div>
              )}

              {/* Vùng render nút chính thức của Google Identity Services */}
              <div
                ref={googleButtonContainerRef}
                className="flex justify-center"
              />

              {/* Chỉ hiển thị nút dự phòng nếu NEXT_PUBLIC_GOOGLE_CLIENT_ID chưa được cấu hình hoặc SDK Google bị lỗi không tải được */}
              {!isGisButtonRendered && (
                <button
                  type="button"
                  disabled={isAuthenticating}
                  onClick={handleTriggerGooglePopupLogin}
                  className="w-full py-2.5 px-4 rounded-xl bg-white hover:bg-slate-50 text-slate-800 font-bold text-xs shadow-sm border border-slate-300 flex items-center justify-center gap-2.5 transition-all disabled:opacity-50"
                >
                  <svg className="w-4 h-4" viewBox="0 0 24 24">
                    <path
                      fill="#EA4335"
                      d="M12 5c1.6 0 3 .6 4.1 1.7l3.1-3.1C17.3 1.8 14.8 1 12 1 7.4 1 3.5 3.6 1.6 7.4l3.7 2.8C6.2 7.2 8.9 5 12 5z"
                    />
                    <path
                      fill="#4285F4"
                      d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5c-.3 1.5-1.1 2.8-2.4 3.6l3.7 2.9c2.2-2 3.7-5 3.7-8.7z"
                    />
                    <path
                      fill="#FBBC05"
                      d="M5.3 14.8c-.2-.8-.4-1.6-.4-2.5s.2-1.7.4-2.5L1.6 7C.6 9 0 11.2 0 13.5s.6 4.5 1.6 6.5l3.7-2.9z"
                    />
                    <path
                      fill="#34A853"
                      d="M12 24c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3.1 0-5.8-2.1-6.7-5l-3.7 2.9C3.5 21.4 7.4 24 12 24z"
                    />
                  </svg>
                  <span>
                    {isAuthenticating
                      ? "Đang xác thực chữ ký Google Token..."
                      : "Continue with Google (@student.tdmu.edu.vn)"}
                  </span>
                </button>
              )}

              <div className="flex items-center justify-end pt-2 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setShowAuthModal(false)}
                  className="px-4 py-1.5 rounded-xl border border-slate-300 text-slate-700 font-semibold hover:bg-slate-50"
                >
                  Đóng
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* KHÔNG GIAN CHÍNH: TRỢ LÝ TRA CỨU QUY CHẾ & THỦ TỤC HỌC VỤ TDMU */}
      <div className="flex flex-1 overflow-hidden">
        {/* SIDEBAR LỊCH SỬ CÁC ĐOẠN CHAT CŨ (CHỈ HIỂN THỊ KHI ĐÃ ĐĂNG NHẬP EMAIL TDMU) */}
        {authUser && isSidebarOpen && (
          <aside className="w-72 bg-white border-r border-slate-200 flex flex-col shrink-0">
            <div className="p-3.5 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div>
                <p className="text-xs font-extrabold uppercase tracking-wider text-[#0054A6]">
                  🗂️ Lịch sử Hội thoại
                </p>
                <p className="text-[11px] text-slate-500">
                  MSSV:{" "}
                  <strong className="font-mono text-slate-700">
                    {authUser.student_id}
                  </strong>
                </p>
              </div>
              <button
                type="button"
                onClick={handleStartNewSession}
                className="px-2.5 py-1.5 rounded-lg bg-[#0054A6] hover:bg-[#003f7d] text-white text-xs font-bold shadow-xs transition-colors"
              >
                + Đoạn chat mới
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-2.5 space-y-1.5">
              {isLoadingHistory ? (
                <p className="text-xs text-slate-400 text-center py-6">
                  Đang tải lịch sử chat...
                </p>
              ) : chatSessions.length === 0 ? (
                <div className="text-center py-8 px-3">
                  <p className="text-xs font-semibold text-slate-500">
                    Chưa có phiên hội thoại nào được lưu.
                  </p>
                  <p className="text-[11px] text-slate-400 mt-1">
                    Hãy đặt câu hỏi đầu tiên để hệ thống tự động lưu theo MSSV{" "}
                    {authUser.student_id}.
                  </p>
                </div>
              ) : (
                chatSessions.map((sess) => {
                  const isSelected = currentSessionId === sess.id;
                  return (
                    <div
                      key={sess.id}
                      onClick={() => handleSelectSession(sess)}
                      className={`group rounded-xl p-2.5 text-xs cursor-pointer transition-all border flex items-start justify-between gap-2 ${isSelected
                          ? "bg-[#0054A6]/10 border-[#0054A6]/40 text-[#0054A6] font-bold"
                          : "bg-white hover:bg-slate-50 border-slate-200/80 text-slate-700"
                        }`}
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate leading-snug">{sess.title}</p>
                        <p className="text-[10px] text-slate-400 mt-1 font-normal">
                          {sess.message_count} tin nhắn •{" "}
                          {sess.created_at.slice(0, 16)}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => handleDeleteSession(sess.id, e)}
                        className="opacity-70 group-hover:opacity-100 text-slate-400 hover:text-red-600 px-1.5 py-0.5 rounded font-bold"
                        title="Xóa phiên chat này"
                      >
                        🗑
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </aside>
        )}

        {/* KHUNG CHAT CHÍNH */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Thanh công cụ phía trên khung chat: Ẩn/Hiện Sidebar lịch sử (hoặc thông báo chế độ Khách) */}
          <div className="bg-white border-b border-slate-200 px-4 py-2 flex flex-wrap items-center justify-between gap-2 shrink-0">
            <div className="flex items-center gap-2">
              {authUser ? (
                <button
                  type="button"
                  onClick={() => setIsSidebarOpen((prev) => !prev)}
                  className="px-2.5 py-1 rounded-lg border border-slate-300 bg-slate-50 hover:bg-slate-100 text-xs font-semibold text-slate-700 flex items-center gap-1.5"
                >
                  <span>
                    {isSidebarOpen ? "◀ Ẩn lịch sử" : "▶ Hiện lịch sử"}
                  </span>
                  <span className="px-1.5 py-0.2 rounded-full bg-[#0054A6] text-white text-[10px]">
                    {chatSessions.length}
                  </span>
                </button>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs font-semibold">
                  <span>🔓</span>
                  <span>
                    Chế độ Khách (Không lưu lịch sử chat) — Đăng nhập{" "}
                    <code className="font-mono font-bold">
                      @student.tdmu.edu.vn
                    </code>{" "}
                    để lưu hội thoại
                  </span>
                </span>
              )}
            </div>
          </div>

          {/* Danh sách tin nhắn cuộn tự động */}
          <main className="flex-1 overflow-y-auto px-4 py-5">
            <div className="max-w-4xl mx-auto space-y-5">
              {authStatusNotice && (
                <div className="bg-blue-50 border border-blue-200 text-[#0054A6] px-4 py-2.5 rounded-xl text-xs flex items-center justify-between">
                  <span>ℹ️ {authStatusNotice}</span>
                  <button
                    type="button"
                    onClick={() => setAuthStatusNotice(null)}
                    className="font-bold underline ml-4"
                  >
                    Đóng
                  </button>
                </div>
              )}

              {/* Gợi ý câu hỏi thực tế TDMU */}
              <div className="bg-white rounded-xl p-3.5 shadow-sm border border-blue-100">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-bold text-[#0054A6] uppercase tracking-wider">
                    💡 Gợi ý tra cứu Quy chế & Thủ tục Học vụ TDMU:
                  </p>
                  <span className="text-[11px] text-slate-400">
                    Nhấn vào câu hỏi để gửi nhanh
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {SUGGESTED_QUESTIONS.map((q, idx) => (
                    <button
                      key={idx}
                      type="button"
                      disabled={isLoading}
                      onClick={() => sendMessage(q)}
                      className="text-left text-xs bg-slate-50 hover:bg-[#0054A6]/10 text-slate-700 hover:text-[#0054A6] border border-slate-200 hover:border-[#0054A6]/40 rounded-lg px-3 py-1.5 font-medium transition-colors disabled:opacity-50"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>

              {errorBanner && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2.5 rounded-xl text-xs flex items-center justify-between">
                  <span>{errorBanner}</span>
                  <button
                    onClick={() => setErrorBanner(null)}
                    className="font-semibold underline ml-4"
                  >
                    Đóng
                  </button>
                </div>
              )}

              {/* Danh sách bong bóng chat */}
              {messages.map((msg) => {
                const isUser = msg.role === "user";
                return (
                  <div
                    key={msg.id}
                    className={`flex ${isUser ? "justify-end" : "justify-start"
                      }`}
                  >
                    <div
                      className={`max-w-[92%] sm:max-w-[82%] rounded-2xl px-4 py-3.5 shadow-sm ${isUser
                          ? "bg-[#0054A6] text-white rounded-br-none"
                          : "bg-white text-slate-800 border border-slate-200/90 rounded-bl-none"
                        }`}
                    >
                      {/* Header nhỏ của từng bong bóng */}
                      <div className="flex items-center justify-between gap-4 mb-2">
                        <span
                          className={`text-xs font-bold ${isUser ? "text-amber-200" : "text-[#0054A6]"
                            }`}
                        >
                          {isUser
                            ? authUser
                              ? `${authUser.full_name} (${authUser.student_id})`
                              : "Sinh viên TDMU (Khách)"
                            : "Trợ lý AI Học vụ TDMU"}
                        </span>
                        <div className="flex flex-wrap items-center gap-2">
                          {!isUser && (
                            <button
                              type="button"
                              onClick={() =>
                                handleToggleSpeakAnswer(msg.id, msg.content)
                              }
                              title="Đọc to câu trả lời bằng giọng tiếng Việt (Text-to-Speech)"
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold transition-colors border ${speakingMessageId === msg.id
                                  ? isLoadingTts
                                    ? "bg-amber-50 text-amber-800 border-amber-300 animate-pulse"
                                    : "bg-red-50 text-red-700 border-red-300 hover:bg-red-100"
                                  : "bg-blue-50 text-[#0054A6] border-blue-200 hover:bg-blue-100"
                                }`}
                            >
                              <span>
                                {speakingMessageId === msg.id
                                  ? isLoadingTts
                                    ? "⏳ Đang tạo giọng đọc..."
                                    : "⏹ Dừng đọc"
                                  : "🔊 Đọc câu trả lời"}
                              </span>
                            </button>
                          )}
                          {!isUser && msg.is_safe !== undefined && (
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold ${msg.is_safe
                                  ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                  : "bg-amber-50 text-amber-700 border border-amber-200"
                                }`}
                            >
                              {msg.is_safe
                                ? "✓ Đã xác thực Guardrail"
                                : "⚠ Cảnh báo Guardrail"}
                            </span>
                          )}
                          <span
                            className={`text-[11px] ${isUser ? "text-blue-200" : "text-slate-400"
                              }`}
                          >
                            {msg.timestamp}
                          </span>
                        </div>
                      </div>

                      {/* Nội dung câu trả lời được render bằng ReactMarkdown + remarkGfm */}
                      <MarkdownContent content={msg.content} isUser={isUser} />

                      {/* KHỐI MULTI-QUERY EXPANSION (HIỂN THỊ MINH BẠCH QUÁ TRÌNH MỞ RỘNG TRUY VẤN) */}
                      {!isUser &&
                        msg.expanded_queries &&
                        msg.expanded_queries.length > 0 && (
                          <div className="mt-3 pt-2.5 border-t border-dashed border-blue-200/80 text-xs">
                            <p className="text-[11px] font-bold text-[#0054A6] mb-1.5 flex items-center gap-1.5">
                              <span>🔎</span>
                              <span>
                                Truy vấn mở rộng học vụ (Multi-Query Expansion):
                              </span>
                            </p>
                            <div className="flex flex-wrap gap-1.5">
                              {msg.expanded_queries.map((eq, eqIdx) => (
                                <span
                                  key={eqIdx}
                                  className="bg-blue-50/80 text-slate-700 border border-blue-200/70 px-2.5 py-1 rounded-lg text-[11px]"
                                >
                                  {eq}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                      {/* KHỐI TRÍCH DẪN NGUỒN (ĐIỀU, KHOẢN, SỐ TRANG) KÈM LINK MỞ PDF ĐÚNG TRANG */}
                      {!isUser && msg.citations && msg.citations.length > 0 && (
                        <div className="mt-4 pt-3 border-t border-slate-200">
                          <div className="flex items-center justify-between gap-2 mb-2">
                            <span className="text-xs font-bold uppercase tracking-wider text-[#0054A6]">
                              📚 Trích dẫn nguồn Quy chế TDMU (
                              {msg.citations.length})
                            </span>
                            <span className="text-[11px] text-slate-400">
                              Nhấn vào tên file / số trang để mở PDF gốc (hoặc Xem trực tiếp / Tải DOCX)
                            </span>
                          </div>
                          <div className="space-y-2.5">
                            {msg.citations.map((cit, cIdx) => {
                              const pdfFileName =
                                cit.document_name ||
                                cit.source_file ||
                                "quy_che_dao_tao_tdmu_1774.pdf";
                              const isDocx =
                                cit.file_type?.toLowerCase() === "docx" ||
                                pdfFileName.toLowerCase().endsWith(".docx");
                              const displayTitle =
                                cit.doc_title || pdfFileName;
                              const issueYearLabel = cit.issue_year
                                ? ` (Ban hành: ${cit.issue_year})`
                                : "";
                              const pdfUrl = buildPdfCitationUrl(
                                pdfFileName,
                                cit.page_number,
                                cit.file_type
                              );
                              const docxPreviewUrl =
                                buildDocxPreviewUrl(pdfFileName);
                              const exportDocxUrl =
                                buildExportDocxUrl(pdfFileName);
                              const isTableQuote = Boolean(
                                cit.quote &&
                                (cit.quote.includes("| --- |") ||
                                  cit.quote.includes("|---|"))
                              );

                              return (
                                <div
                                  key={cIdx}
                                  className="bg-slate-50 border border-slate-200/90 rounded-xl p-2.5 text-xs"
                                >
                                  <div className="flex flex-wrap items-center gap-1.5 font-semibold text-slate-800 mb-1.5">
                                    {!isDocx ? (
                                      /* Văn bản PDF: Mở trực tiếp file PDF tại đúng trang + Nút phụ Tải bản Word (.docx) */
                                      <>
                                        <a
                                          href={pdfUrl}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          title={`Mở file ${pdfFileName} tại Trang ${cit.page_number ?? 1
                                            }`}
                                          className="inline-flex items-center gap-1.5 bg-[#0054A6] hover:bg-[#003f7d] text-white px-2.5 py-0.5 rounded-md shadow-xs transition-colors underline-offset-2 hover:underline"
                                        >
                                          <span>
                                            📄 {displayTitle}
                                            {issueYearLabel}
                                          </span>
                                          {cit.page_number && (
                                            <span className="bg-amber-300 text-[#003f7d] font-extrabold px-1.5 py-0.2 rounded text-[11px]">
                                              Trang {cit.page_number} ↗
                                            </span>
                                          )}
                                        </a>
                                        <a
                                          href={exportDocxUrl}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          title={`Chuyển đổi và tải về bản Microsoft Word (.docx) của văn bản ${displayTitle}`}
                                          className="inline-flex items-center gap-1 bg-blue-50 hover:bg-blue-100 text-[#0054A6] border border-blue-200 font-bold px-2 py-0.5 rounded-md shadow-xs transition-colors underline-offset-2 hover:underline text-[11px]"
                                        >
                                          ⬇ Tải bản Word (.docx)
                                        </a>
                                      </>
                                    ) : (
                                      /* Văn bản DOCX: Hiển thị đồng thời 2 nút hành động (Xem trực tiếp Tab mới & Tải file DOCX gốc) */
                                      <>
                                        <span className="inline-flex items-center gap-1 bg-[#0054A6] text-white px-2.5 py-0.5 rounded-md shadow-xs">
                                          📝 {displayTitle}
                                          {issueYearLabel}
                                        </span>
                                        <a
                                          href={docxPreviewUrl}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          title={`Xem trực tiếp nội dung ${pdfFileName} trên Tab mới`}
                                          className="inline-flex items-center gap-1 bg-amber-300 hover:bg-amber-400 text-[#003f7d] font-extrabold px-2 py-0.5 rounded-md shadow-xs transition-colors underline-offset-2 hover:underline text-[11px]"
                                        >
                                          👁 Xem trực tiếp (Tab mới)
                                        </a>
                                        <a
                                          href={pdfUrl}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          download={pdfFileName}
                                          title={`Tải file văn bản Word gốc: ${pdfFileName}`}
                                          className="inline-flex items-center gap-1 bg-blue-100 hover:bg-blue-200 text-[#0054A6] border border-blue-300 font-bold px-2 py-0.5 rounded-md shadow-xs transition-colors underline-offset-2 hover:underline text-[11px]"
                                        >
                                          ⬇ Tải file DOCX gốc
                                        </a>
                                      </>
                                    )}

                                    {cit.article && (
                                      <span className="bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-md">
                                        {cit.article}
                                      </span>
                                    )}
                                    {cit.clause && (
                                      <span className="bg-amber-100 text-amber-800 px-2 py-0.5 rounded-md">
                                        {cit.clause}
                                      </span>
                                    )}
                                    {isTableQuote && (
                                      <span className="bg-purple-100 text-purple-800 px-2 py-0.5 rounded-md">
                                        Bảng biểu
                                      </span>
                                    )}
                                  </div>
                                  {cit.chapter && (
                                    <div className="text-[11px] text-slate-500 mb-1.5 font-medium">
                                      {cit.chapter}
                                    </div>
                                  )}
                                  {cit.quote && (
                                    <div className="text-slate-700 bg-white p-2.5 rounded-lg border border-slate-200/80">
                                      {isTableQuote ? (
                                        <MarkdownContent
                                          content={cit.quote}
                                          compact={true}
                                        />
                                      ) : (
                                        <div className="italic">
                                          <MarkdownContent
                                            content={`“${cit.quote}”`}
                                            compact={true}
                                          />
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {/* KHỐI ĐÁNH GIÁ MỨC ĐỘ HÀI LÒNG CỦA SINH VIÊN (👍 HỮU ÍCH / 👎 CHƯA CHÍNH XÁC) */}
                      {!isUser && msg.id !== "welcome-msg" && (
                        <div className="mt-3 pt-2.5 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2 text-xs">
                          <span className="text-[11px] text-slate-400">
                            Đánh giá độ chính xác của câu trả lời:
                          </span>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => handleFeedback(msg, "like")}
                              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-bold border transition-all ${msg.feedback === "like"
                                  ? "bg-emerald-600 text-white border-emerald-600 shadow-xs"
                                  : "bg-slate-50 hover:bg-emerald-50 text-slate-600 hover:text-emerald-700 border-slate-200"
                                }`}
                            >
                              <span>👍</span>
                              <span>Hữu ích</span>
                            </button>
                            <button
                              type="button"
                              onClick={() => handleFeedback(msg, "dislike")}
                              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-bold border transition-all ${msg.feedback === "dislike"
                                  ? "bg-red-600 text-white border-red-600 shadow-xs"
                                  : "bg-slate-50 hover:bg-red-50 text-slate-600 hover:text-red-700 border-slate-200"
                                }`}
                            >
                              <span>👎</span>
                              <span>Chưa chính xác</span>
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              {/* Trạng thái đang tải (Typing Indicator) */}
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-white border border-slate-200 rounded-2xl rounded-bl-none px-4 py-3 shadow-sm flex items-center gap-3">
                    <div className="flex space-x-1.5">
                      <span className="w-2 h-2 bg-[#0054A6] rounded-full animate-bounce [animation-delay:-0.3s]"></span>
                      <span className="w-2 h-2 bg-[#0054A6] rounded-full animate-bounce [animation-delay:-0.15s]"></span>
                      <span className="w-2 h-2 bg-[#0054A6] rounded-full animate-bounce"></span>
                    </div>
                    <span className="text-xs text-slate-600 font-medium">
                      Trợ lý AI Học vụ TDMU đang tra cứu quy chế & đối chiếu
                      trích dẫn...
                    </span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </main>

          {/* KHUNG NHẬP TIN NHẮN KÈM NÚT NHẬP GIỌNG NÓI TIẾNG VIỆT (🎙️) */}
          <footer className="bg-white border-t border-slate-200 px-4 py-3 shrink-0">
            <div className="max-w-4xl mx-auto">
              {voiceStatusHint && (
                <div className="mb-2 bg-blue-50 border border-blue-200 text-[#0054A6] px-3 py-1.5 rounded-xl text-xs font-medium flex items-center justify-between">
                  <span>{voiceStatusHint}</span>
                  <button
                    type="button"
                    onClick={() => setVoiceStatusHint(null)}
                    className="font-bold underline ml-3 text-[11px]"
                  >
                    Ẩn
                  </button>
                </div>
              )}
              <div className="flex items-end gap-2">
                <button
                  type="button"
                  onClick={handleToggleVoiceInput}
                  disabled={isLoading}
                  title={
                    isListeningVoice
                      ? "Đang lắng nghe giọng nói tiếng Việt... Nhấn để dừng"
                      : "Nói câu hỏi bằng tiếng Việt (Voice Input vi-VN)"
                  }
                  className={`h-[58px] px-3.5 rounded-xl font-bold text-xs shadow-sm transition-all flex flex-col items-center justify-center gap-0.5 border shrink-0 ${isListeningVoice
                      ? "bg-red-600 text-white border-red-600 animate-pulse"
                      : "bg-slate-50 hover:bg-blue-50 text-[#0054A6] border-slate-300 hover:border-[#0054A6]"
                    }`}
                >
                  <span className="text-base leading-none">🎙️</span>
                  <span className="text-[10px]">
                    {isListeningVoice ? "Đang nghe..." : "Giọng nói"}
                  </span>
                </button>
                <textarea
                  rows={2}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={isLoading}
                  placeholder="Nhập hoặc nhấn 🎙️ nói câu hỏi về Quy chế Học vụ Trường Đại học Thủ Dầu Một (Nhấn Enter để gửi)..."
                  className="flex-1 resize-none rounded-xl border border-slate-300 bg-slate-50 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#0054A6] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0054A6]/20 disabled:opacity-60"
                />
                <button
                  type="button"
                  onClick={() => sendMessage()}
                  disabled={isLoading || !input.trim()}
                  className="h-[58px] px-5 rounded-xl bg-[#0054A6] hover:bg-[#003f7d] active:bg-[#002f5e] text-white font-semibold text-sm shadow-sm transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
                >
                  <span>{isLoading ? "Đang xử lý..." : "Gửi câu hỏi"}</span>
                  <span aria-hidden="true">➤</span>
                </button>
              </div>
              <p className="text-[11px] text-slate-400 mt-1.5 text-center">
                Trợ lý AI Học vụ chính thức — Trường Đại học Thủ Dầu Một (TDMU) •
                Đồ án Tốt nghiệp SV Lê Quốc Bảo (2224801030361)
              </p>
            </div>
          </footer>
        </div>
      </div>
    </div>
  );
}
