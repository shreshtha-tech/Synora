import { Position, type Edge, type Node } from "@xyflow/react";

export type Concept = { name: string; children: Concept[] };
export type ConceptNode = Node<{ label: string }, "concept">;
const WIDTH = 160;
const GAP = 40;

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

export function verticalMindMap(tree: Concept, availableWidth = 1400): { nodes: ConceptNode[]; edges: Edge[] } {
  type Entry = { concept: Concept; id: string; parent?: string };
  const levels: Entry[][] = [];
  function collect(concept: Concept, id: string, depth: number, parent?: string) {
    (levels[depth] ||= []).push({ concept, id, parent });
    concept.children.forEach((child, index) => collect(child, `${id}-${index}`, depth + 1, id));
  }
  collect(tree, "root", 0);
  const columns = Math.max(1, Math.floor((availableWidth + GAP) / (WIDTH + GAP)));
  const nodes: ConceptNode[] = [];
  const edges: Edge[] = [];
  let y = 0;
  for (const level of levels) {
    // Lay each depth out independently. A large descendant branch must not
    // stretch the root/category row across the width of all its leaves.
    for (let offset = 0; offset < level.length; offset += columns) {
      const row = level.slice(offset, offset + columns);
      const heights = row.map(({ concept }) => {
        const lines = concept.name.split("\n").reduce((count, line) => count + Math.max(1, Math.ceil(line.length / 20)), 0);
        return Math.max(36, 20 + lines * 16);
      });
      const rowWidth = row.length * WIDTH + (row.length - 1) * GAP;
      const startX = Math.max(0, (availableWidth - rowWidth) / 2);
      row.forEach(({ concept, id, parent }, column) => {
        nodes.push({ id, type: "concept", data: { label: concept.name }, position: { x: startX + column * (WIDTH + GAP), y }, sourcePosition: Position.Bottom, targetPosition: Position.Top, style: { width: WIDTH, height: heights[column] } });
        if (parent) edges.push({ id: `${parent}:${id}`, source: parent, target: id, type: "default", style: { stroke: "#8b92f2", strokeWidth: 1, strokeDasharray: "5 5" } });
      });
      y += Math.max(...heights) + 72;
    }
  }
  return { nodes, edges };
}
