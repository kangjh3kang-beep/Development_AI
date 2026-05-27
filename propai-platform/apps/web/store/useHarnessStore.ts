import { create } from 'zustand';

export type TenantStatus = 'active' | 'suspended' | 'throttled';
export type UserRole = 'super_admin' | 'tenant_admin' | 'user';

export interface TenantNode {
  id: string;
  name: string;
  role: UserRole;
  status: TenantStatus;
  aiModel: string;
  tokenUsage: number;
  lastActive: string;
}

interface HarnessState {
  nodes: TenantNode[];
  globalStatus: 'optimal' | 'degraded' | 'critical';
  toggleNodeStatus: (id: string, newStatus: TenantStatus) => void;
  updateNodeRole: (id: string, newRole: UserRole) => void;
  getGlobalMetrics: () => { totalTokens: number; activeNodes: number; suspendedNodes: number };
}

const mockNodes: TenantNode[] = [
  { id: 'node-01', name: 'Cyberdyne Systems', role: 'super_admin', status: 'active', aiModel: 'GPT-4o', tokenUsage: 1245000, lastActive: '2 min ago' },
  { id: 'node-02', name: 'Tyrell Corp', role: 'tenant_admin', status: 'active', aiModel: 'Claude 3 Opus', tokenUsage: 890200, lastActive: '15 min ago' },
  { id: 'node-03', name: 'Weyland-Yutani', role: 'tenant_admin', status: 'throttled', aiModel: 'GPT-4 Turbo', tokenUsage: 2150000, lastActive: 'Just now' },
  { id: 'node-04', name: 'Omni Consumer', role: 'user', status: 'suspended', aiModel: 'GPT-3.5', tokenUsage: 0, lastActive: '2 days ago' },
  { id: 'node-05', name: 'Massive Dynamic', role: 'user', status: 'active', aiModel: 'Claude 3 Haiku', tokenUsage: 45200, lastActive: '1 hr ago' },
];

export const useHarnessStore = create<HarnessState>((set, get) => ({
  nodes: mockNodes,
  globalStatus: 'optimal',
  
  toggleNodeStatus: (id, newStatus) => set((state) => {
    const updatedNodes = state.nodes.map(node => 
      node.id === id ? { ...node, status: newStatus } : node
    );
    
    // 글로벌 상태 업데이트 (위험 노드 비율에 따라)
    const suspendedCount = updatedNodes.filter(n => n.status === 'suspended').length;
    const newGlobalStatus = suspendedCount > 2 ? 'critical' : suspendedCount > 0 ? 'degraded' : 'optimal';
    
    return { nodes: updatedNodes, globalStatus: newGlobalStatus };
  }),
  
  updateNodeRole: (id, newRole) => set((state) => ({
    nodes: state.nodes.map(node => 
      node.id === id ? { ...node, role: newRole } : node
    )
  })),
  
  getGlobalMetrics: () => {
    const { nodes } = get();
    return {
      totalTokens: nodes.reduce((sum, node) => sum + node.tokenUsage, 0),
      activeNodes: nodes.filter(n => n.status === 'active').length,
      suspendedNodes: nodes.filter(n => n.status === 'suspended').length,
    };
  }
}));
