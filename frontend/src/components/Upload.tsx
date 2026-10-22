"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useSession, signIn } from "next-auth/react";
import { UploadCloud, FileText, Loader2 } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export default function Upload() {
  const { data: session, status: sessionStatus } = useSession();
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState<string>("");

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (sessionStatus === "loading") return;
    if (!session) {
      await signIn("google");
      return;
    }
    if (!file) return;

    const token = session.backendToken;
    if (!token) {
      setStatus("Please sign in again to start a document session.");
      await signIn("google");
      return;
    }

    setUploading(true);
    setStatus("Uploading...");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/upload/`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      if (!res.ok) {
        if (res.status === 401 || res.status === 403) {
          setStatus("Your session expired. Please sign in again.");
          await signIn("google");
          return;
        }
        const errorData = await res.json().catch(() => null);
        setStatus(
          typeof errorData?.detail === "string"
            ? errorData.detail
            : `Upload failed (${res.status}). Please try again.`
        );
        return;
      }

      const data = await res.json();
      console.log("Upload success:", data);
      setStatus("Processing started! Redirecting...");
      router.push(`/doc/${data.id}`);
    } catch {
      setStatus("Unable to reach the upload service. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="neo-inset p-8 rounded-3xl w-full max-w-md mx-auto text-center">
      <div className="border-2 border-dashed border-gray-400 rounded-xl p-8 flex flex-col items-center justify-center cursor-pointer hover:bg-gray-50 transition-colors relative">
        <input
          type="file"
          className="absolute inset-0 opacity-0 cursor-pointer"
          onChange={handleFileChange}
          accept=".pdf,.docx"
        />
        <UploadCloud className="w-12 h-12 text-primary mb-4" />
        <p className="text-gray-600 font-medium">
          {file ? file.name : "Click or Drag to Upload PDF/DOCX"}
        </p>
      </div>

      {file && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-6"
        >
          <button
            onClick={handleUpload}
            disabled={uploading || sessionStatus === "loading"}
            className={cn(
              "neo-btn px-8 py-3 rounded-full font-bold text-primary flex items-center justify-center gap-2 mx-auto w-full",
              uploading && "opacity-70 cursor-not-allowed"
            )}
          >
            {uploading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <FileText className="w-5 h-5" />
                Start Learning
              </>
            )}
          </button>
        </motion.div>
      )}

      {status && <p role="status" className="mt-4 text-sm text-gray-500">{status}</p>}
    </div>
  );
}
