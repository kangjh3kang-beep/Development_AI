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
  getActiveApiKey: () => string;
};

export const useSystemStore = create<SystemState>()(
  persist(
    (set, get) => ({
      llmProvider: 'openai',
      openaiApiKey: '',
      anthropicApiKey: '',
      llmModel: 'auto',
      
      setLLMProvider: (provider) => set({ llmProvider: provider, llmModel: 'auto' }),
      setOpenAIApiKey: (key) => set({ openaiApiKey: key.trim() }),
      setAnthropicApiKey: (key) => set({ anthropicApiKey: key.trim() }),
      setLLMModel: (model) => set({ llmModel: model }),
      
      hasValidKey: () => {
        const state = get();
        const key = state.llmProvider === 'openai' ? state.openaiApiKey : state.anthropicApiKey;
        // Accept any key that is non-empty and at least 10 chars long
        // Modern OpenAI keys: sk-proj-..., sk-..., sess-... etc.
        // Modern Anthropic keys: sk-ant-api03-..., sk-ant-..., etc.
        return key.trim().length >= 10;
      },

      getActiveApiKey: () => {
        const state = get();
        return state.llmProvider === 'openai' ? state.openaiApiKey : state.anthropicApiKey;
      },
    }),
    {
      name: 'propai-system-storage',
    }
  )
);
