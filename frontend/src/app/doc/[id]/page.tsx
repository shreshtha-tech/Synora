"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { useSession, signIn } from "next-auth/react";
import LoadingScreen from "@/components/LoadingScreen";
import DocumentTabBar from "@/components/doc/DocumentTabBar";
import ProcessingBanner from "@/components/doc/ProcessingBanner";
import PdfViewer from "@/components/doc/PdfViewer";
import TopicsTab from "@/components/doc/tabs/TopicsTab";
import MindMapTab from "@/components/doc/tabs/MindMapTab";
import QnaTab from "@/components/doc/tabs/QnaTab";
import PredictedTab from "@/components/doc/tabs/PredictedTab";
import PreviousTab from "@/components/doc/tabs/PreviousTab";
import type { DocumentDetails } from "@/components/doc/types";
import { apiRequest, errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

export type TabId = "topics" | "mindmap" | "qna" | "predicted" | "previous";

export default function DocumentPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: session, status: sessionStatus } = useSession();
  const [activeTab, setActiveTab] = useState<TabId>("topics");
  const [data, setData] = useState<DocumentDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const token = session?.backendToken;
  const isProcessing = data?.status === "processing" || data?.status === "topics_ready";
  const progress = data?.progress || 0;

  useEffect(() => {
    if (!id || !token) return;
    const controller = new AbortController();
    let timeout: ReturnType<typeof setTimeout>;
    const fetchDocument = async () => {
      try {
        const document = await apiRequest<DocumentDetails>(`/api/v1/documents/${id}`, token, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setData(document);
        setError("");
        setLoading(false);
        if (["processing", "topics_ready", "deleting"].includes(document.status)) {
          timeout = setTimeout(fetchDocument, 2000);
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        setError(errorMessage(error));
        setLoading(false);
      }
    };
    void fetchDocument();
    return () => { controller.abort(); clearTimeout(timeout); };
  }, [id, token, refresh]);

  const handleRetry = async () => {
    setRetrying(true);
    setError("");
    try {
      await apiRequest(`/api/v1/documents/${id}/retry`, token, { method: "POST" });
      setData(previous => previous ? { ...previous, status: "processing", progress: 0, error: null } : previous);
      setRefresh(value => value + 1);
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setRetrying(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm("Delete this document and its chat history?")) return;
    setDeleting(true);
    try {
      await apiRequest(`/api/v1/documents/${id}`, token, { method: "DELETE" });
      router.push("/dashboard");
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setDeleting(false);
    }
  };

  if (sessionStatus === "loading") return <LoadingScreen progress={0} />;
  if (!token) return <div className="p-8 text-center"><p>Please sign in again to access this document.</p><button className="neo-btn px-6 py-3 mt-4" onClick={() => signIn("google")}>Sign in with Google</button></div>;
  if (loading && !error) return <LoadingScreen progress={0} />;
  if (!data) return <div className="p-8 text-center" role="alert"><p>{error || "Document not found."}</p><button className="neo-btn px-6 py-3 mt-4" onClick={() => { setLoading(true); setRefresh(value => value + 1); }}>Retry loading</button></div>;

  const isFullScreen = activeTab !== "topics";
  const processingError = data.error || (data.status === "failed" ? "Document processing failed. Please retry." : "");
  return (
    <div className="flex flex-col h-[calc(100vh-64px)] overflow-hidden bg-[#e0e5ec]">
      <DocumentTabBar activeTab={activeTab} onTabChange={setActiveTab} isProcessing={isProcessing} deleting={deleting} onDelete={handleDelete} />
      {error && <div role="alert" className="px-6 py-3 bg-red-50 text-red-700 flex items-center justify-between gap-3"><span>{error}</span><button className="underline shrink-0" onClick={() => setRefresh(value => value + 1)}>Refresh</button></div>}
      {processingError && !isProcessing && <div role="alert" className="px-6 py-3 bg-amber-50 text-amber-900 flex items-center justify-between gap-3"><span>{processingError}</span><button disabled={retrying} onClick={handleRetry} className="neo-btn px-4 py-2 shrink-0 disabled:opacity-50">{retrying ? "Starting..." : "Retry processing"}</button></div>}
      {isProcessing && <ProcessingBanner progress={progress} />}
      <div className="flex flex-col lg:flex-row flex-1 min-h-0 overflow-hidden">
        {!isFullScreen && <PdfViewer fileUrl={data.fileUrl} fileType={data.fileType} />}
        <div className={cn("p-6 lg:p-8 min-h-0 flex-1 bg-[#e0e5ec]", activeTab === "mindmap" ? "overflow-hidden" : "overflow-y-auto", isFullScreen ? "w-full" : "w-full lg:w-1/2")}>
          {activeTab === "topics" && <TopicsTab topics={data.topics} explanations={data.explanations} hasExplanations={Object.keys(data.explanations).length > 0} isProcessing={isProcessing} progress={progress} />}
          {activeTab === "mindmap" && <MindMapTab hasMindTree={Boolean(data.mindTree.name)} mindTree={data.mindTree} isProcessing={isProcessing} progress={progress} />}
          {activeTab === "qna" && <QnaTab documentId={id} session={session} />}
          {activeTab === "predicted" && <PredictedTab hasPredictedQuestions={data.predictedQuestions.length > 0} predictedQuestions={data.predictedQuestions} isProcessing={isProcessing} progress={progress} />}
          {activeTab === "previous" && <PreviousTab documentId={id} token={token} />}
        </div>
      </div>
    </div>
  );
}
