interface PdfViewerProps {
  fileUrl?: string;
  fileType?: "pdf" | "docx";
}

export default function PdfViewer({ fileUrl, fileType = "pdf" }: PdfViewerProps) {
  return <div className="w-full lg:w-1/2 h-[35vh] lg:h-full shrink-0 bg-gray-100 border-r border-gray-300 flex flex-col">
    {fileUrl ? <>
      <a href={fileUrl} target="_blank" rel="noopener noreferrer" className="px-4 py-2 text-sm text-primary underline bg-white">Open original document in a new tab</a>
      {fileType === "pdf" ? <iframe src={fileUrl} className="w-full flex-1 min-h-0" title="Document Viewer" /> : <p className="p-6 text-gray-600">Your DOCX is available from the link above. Its study notes are shown alongside.</p>}
    </> : <div className="p-6 text-gray-500">The original document is unavailable.</div>}
  </div>;
}
