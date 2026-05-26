import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type SystemState = {
  llmProvider: 'openai' | 'anthropic';
  openaiApiKey: string;
  anthropicApiKey: string;
  llmModel: string;
  setLLMProvider: (provider: 'openai' | 'anthropic') => void;
  setOpenAIApiKey: (key: string) => void;
  setAnthropicApiKey: (key: string) => void;
  setLLMModel: (model: string) => void;
  hasValidKey: () => boolean;
};

export const useSystemStore = create<SystemState>()(
  persist(
    (set, get) => ({
      llmProvider: 'openai',
      openaiApiKey: '',
      anthropicApiKey: '',
      llmModel: 'gpt-4o',
      
      setLLMProvider: (provider) => set({ llmProvider: provider }),
      setOpenAIApiKey: (key) => set({ openaiApiKey: key }),
      setAnthropicApiKey: (key) => set({ anthropicApiKey: key }),
      setLLMModel: (model) => set({ llmModel: model }),
      
      hasValidKey: () => {
        const state = get();
        if (state.llmProvider === 'openai') {
          return state.openaiApiKey.startsWith('sk-') && state.openaiApiKey.length > 20;
        }
        if (state.llmProvider === 'anthropic') {
          return state.anthropicApiKey.startsWith('sk-ant-') && state.anthropicApiKey.length > 20;
        }
        return false;
      }
    }),
    {
      name: 'propai-system-storage', // name of the item in the storage (must be unique)
    }
  )
);
