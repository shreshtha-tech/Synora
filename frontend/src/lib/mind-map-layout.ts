import { Position, type Edge, type Node } from "@xyflow/react";

export type Concept = { name: string; children: Concept[] };
export type ConceptNode = Node<{ label: string }, "concept">;
const WIDTH = 220;
const GAP = 64;

export function normalizeConcept(value: unknown, name = "Concept Map", depth = 0): Concept {
  if (depth > 64) return { name, children: [] };
  if (typeof value === "string" || typeof value === "number") return { name: String(value), children: [] };
  if (Array.isArray(value)) return { name, children: value.map(child => normalizeConcept(child, "Concept", depth + 1)) };
  if (!value || typeof value !== "object") return { name, children: [] };
  const record = value as Record<string, unknown>;
  const label = record.name ?? record.label ?? record.title;
  if (typeof label === "string") {
    const children = record.children ?? record.subtopics;
    return { name: label, children: Array.isArray(children) ? children.map(child => normalizeConcept(child, "Concept", depth + 1)) : [] };
  }
  return {
    name,
    children: Object.entries(record).map(([key, child]) => {
      if (typeof child === "string" || typeof child === "number") return { name: key, children: [{ name: String(child), children: [] }] };
      return normalizeConcept(child, key, depth + 1);
    }),
  };
}

export function verticalMindMap(tree: Concept): { nodes: ConceptNode[]; edges: Edge[] } {
  const widths = new Map<string, number>();
  const heights = new Map<string, number>();
  const rowHeights: number[] = [];
  function measure(concept: Concept, id: string, depth: number): number {
    const lines = concept.name.split("\n").reduce((count, line) => count + Math.max(1, Math.ceil(line.length / 22)), 0);
    const height = Math.max(64, 24 + lines * 20);
    heights.set(id, height);
    rowHeights[depth] = Math.max(rowHeights[depth] || 0, height);
    const childrenWidth = concept.children.reduce((sum, child, index) => sum + measure(child, `${id}-${index}`, depth + 1), 0) + Math.max(0, concept.children.length - 1) * GAP;
    const width = Math.max(WIDTH, childrenWidth);
    widths.set(id, width);
    return width;
  }
  measure(tree, "root", 0);
  const rowY: number[] = [0];
  for (let depth = 1; depth < rowHeights.length; depth++) rowY[depth] = rowY[depth - 1] + rowHeights[depth - 1] + 100;
  const nodes: ConceptNode[] = [];
  const edges: Edge[] = [];
  function place(concept: Concept, id: string, left: number, depth: number, parent?: string) {
    const width = widths.get(id)!;
    nodes.push({ id, type: "concept", data: { label: concept.name }, position: { x: left + (width - WIDTH) / 2, y: rowY[depth] }, sourcePosition: Position.Bottom, targetPosition: Position.Top, style: { width: WIDTH, height: heights.get(id) } });
    if (parent) edges.push({ id: `${parent}:${id}`, source: parent, target: id, type: "default", style: { stroke: "#8b92f2", strokeWidth: 1.2, strokeDasharray: "5 5" } });
    let childLeft = left;
    concept.children.forEach((child, index) => {
      const childId = `${id}-${index}`;
      place(child, childId, childLeft, depth + 1, id);
      childLeft += widths.get(childId)! + GAP;
    });
  }
  place(tree, "root", 0, 0);
  return { nodes, edges };
}
