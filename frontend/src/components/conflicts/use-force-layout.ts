import { useMemo } from "react";

interface NodeInput {
  id: string;
}

interface EdgeInput {
  source: string;
  target: string;
  weight: number;
}

export interface PositionedNode {
  id: string;
  x: number;
  y: number;
}

export function useForceLayout(
  nodes: NodeInput[],
  edges: EdgeInput[],
  width: number,
  height: number,
): PositionedNode[] {
  return useMemo(() => {
    if (nodes.length === 0) return [];

    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.min(width, height) * 0.35;

    // Initialize positions in a circle
    const positions = nodes.map((n, i) => {
      const angle = (2 * Math.PI * i) / nodes.length;
      return {
        id: n.id,
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
        vx: 0,
        vy: 0,
      };
    });

    const idxMap = new Map(positions.map((p, i) => [p.id, i]));

    const REPULSION = 5000;
    const SPRING_K = 0.005;
    const SPRING_REST = 120;
    const GRAVITY = 0.01;
    const DAMPING = 0.85;
    const ITERATIONS = 120;

    for (let iter = 0; iter < ITERATIONS; iter++) {
      const cooling = 1 - iter / ITERATIONS;

      // Repulsion between all pairs
      for (let i = 0; i < positions.length; i++) {
        for (let j = i + 1; j < positions.length; j++) {
          const dx = positions[i].x - positions[j].x;
          const dy = positions[i].y - positions[j].y;
          const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
          const force = (REPULSION * cooling) / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          positions[i].vx += fx;
          positions[i].vy += fy;
          positions[j].vx -= fx;
          positions[j].vy -= fy;
        }
      }

      // Spring attraction along edges
      for (const edge of edges) {
        const si = idxMap.get(edge.source);
        const ti = idxMap.get(edge.target);
        if (si == null || ti == null) continue;
        const dx = positions[ti].x - positions[si].x;
        const dy = positions[ti].y - positions[si].y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
        const stretch = dist - SPRING_REST;
        const force = SPRING_K * stretch * Math.log2(1 + edge.weight);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        positions[si].vx += fx;
        positions[si].vy += fy;
        positions[ti].vx -= fx;
        positions[ti].vy -= fy;
      }

      // Center gravity
      for (const p of positions) {
        p.vx += (cx - p.x) * GRAVITY;
        p.vy += (cy - p.y) * GRAVITY;
      }

      // Apply velocities with damping
      let maxV = 0;
      for (const p of positions) {
        p.vx *= DAMPING;
        p.vy *= DAMPING;
        p.x += p.vx * cooling;
        p.y += p.vy * cooling;
        const v = p.vx * p.vx + p.vy * p.vy;
        if (v > maxV) maxV = v;
      }

      // Early termination when layout has stabilized
      if (maxV < 0.01) break;
    }

    return positions.map((p) => ({ id: p.id, x: p.x, y: p.y }));
  }, [nodes, edges, width, height]);
}
