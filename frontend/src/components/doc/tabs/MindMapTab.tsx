import MindMap from "@/components/MindMap";
import TabLoadingPlaceholder from "@/components/doc/TabLoadingPlaceholder";
import type { MindTree } from "@/components/doc/types";

interface MindMapTabProps {
  hasMindTree: boolean;
  mindTree: Partial<MindTree>;
  isProcessing: boolean;
  progress: number;
}

export default function MindMapTab({ hasMindTree, mindTree, isProcessing, progress }: MindMapTabProps) {
  return (
    <section className="h-full min-h-0 flex flex-col gap-6 w-full" aria-label="Document mind map">
      <h2 className="text-2xl font-bold text-gray-800">Concept Map</h2>
      {hasMindTree ? (
        <div className="flex-1 min-h-0 w-full relative overflow-hidden rounded-3xl neo-inset">
          <MindMap data={mindTree} />
        </div>
      ) : isProcessing ? (
        <TabLoadingPlaceholder label="Building Mind Map..." progress={progress} />
      ) : (
        <div className="flex items-center justify-center p-8 text-gray-500 h-full">No mind map available.</div>
      )}
    </section>
  );
}
