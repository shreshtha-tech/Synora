"use client";

import { useEffect, useMemo } from "react";
import { ReactFlow, Controls, Background, BackgroundVariant, MiniMap, Handle, Position, Panel, useNodesInitialized, useReactFlow, useStore, type NodeProps } from "@xyflow/react";
import { Maximize2 } from "lucide-react";
import "@xyflow/react/dist/style.css";
import { normalizeConcept, verticalMindMap, type ConceptNode } from "@/lib/mind-map-layout";

function ConceptCard({ data }: NodeProps<ConceptNode>) {
  return <div className="h-full w-full flex items-center justify-center rounded-2xl border border-white/90 bg-[#e0e5ec] px-4 py-3 text-center text-sm font-semibold leading-5 text-slate-700 shadow-[5px_5px_12px_#b8bec7,-5px_-5px_12px_#ffffff]">
    <Handle type="target" position={Position.Top} className="!h-1 !w-1 !border-0 !bg-slate-600" />
    <span className="whitespace-pre-wrap [overflow-wrap:anywhere]">{data.label}</span>
    <Handle type="source" position={Position.Bottom} className="!h-1 !w-1 !border-0 !bg-slate-600" />
  </div>;
}

const nodeTypes = { concept: ConceptCard };
const fitOptions = { padding: 0.2, minZoom: 0.000001, maxZoom: 1 };

function FrameAllContent() {
  const initialized = useNodesInitialized();
  const width = useStore(state => state.width);
  const height = useStore(state => state.height);
  const { fitView } = useReactFlow();

  // The final canvas size and measured cards are only known after mounting.
  // Fit again on resize, while leaving manual panning/zooming undisturbed.
  useEffect(() => {
    if (!initialized || !width || !height) return;
    const frame = requestAnimationFrame(() => { void fitView(fitOptions); });
    return () => cancelAnimationFrame(frame);
  }, [initialized, width, height, fitView]);

  return <Panel position="top-right">
    <button onClick={() => { void fitView({ ...fitOptions, duration: 250 }); }} className="flex items-center gap-2 rounded-lg border border-white/80 bg-white/90 px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-white" title="Fit every concept into the frame">
      <Maximize2 className="h-4 w-4" /> Fit all
    </button>
  </Panel>;
}

export default function MindMap({ data }: { data: unknown }) {
  const graph = useMemo(() => verticalMindMap(normalizeConcept(data)), [data]);
  const graphKey = useMemo(() => JSON.stringify(data), [data]);
  return <div className="h-full w-full bg-[#e0e5ec]" aria-label="Interactive concept map">
    <ReactFlow
      key={graphKey}
      defaultNodes={graph.nodes}
      defaultEdges={graph.edges}
      nodeTypes={nodeTypes}
      nodesConnectable={false}
      fitView
      fitViewOptions={fitOptions}
      minZoom={fitOptions.minZoom}
      maxZoom={2}
      colorMode="light"
    >
      <Background variant={BackgroundVariant.Dots} gap={14} size={0.8} color="#aeb8c7" />
      <FrameAllContent />
      <Controls position="bottom-left" fitViewOptions={fitOptions} className="!border-white/80 !shadow-md" />
      <MiniMap position="bottom-right" pannable zoomable nodeColor="#c3cad8" maskColor="rgba(224,229,236,0.65)" className="!bg-white/80 !rounded-xl !border !border-white/80 !shadow-sm" />
    </ReactFlow>
  </div>;
}
