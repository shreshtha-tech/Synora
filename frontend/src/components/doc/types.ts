export type MindTree = { name: string; children: MindTree[] };
export type ChatMessage = { id?: string; role: "user" | "ai"; content: string; createdAt?: string };
export type DocumentDetails = {
  id: string;
  name: string;
  status: string;
  progress: number;
  fileUrl: string;
  fileType: "pdf" | "docx";
  error?: string | null;
  topics: string[];
  explanations: Record<string, string>;
  mindTree: Partial<MindTree>;
  predictedQuestions: { question: string; answer: string }[];
};
