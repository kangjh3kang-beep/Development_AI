"use client";

import { useState, useRef, useEffect } from "react";

interface Message {
    id: string;
    role: "user" | "ai";
    content: string;
    status?: "generating" | "complete";
}

export default function GenerativePanel() {
    const [messages, setMessages] = useState<Message[]>([
        { 
            id: "msg-0", 
            role: "ai", 
            content: "건축 AI 생성 에이전트입니다. 대지 면적, 용도, 층수 등의 요구 사항을 프롬프트로 입력해주시면 해당 조건에 맞는 3D 모델(IFC/GLTF) 초안을 생성하여 우측 뷰어에 로드합니다."
        }
    ]);
    const [input, setInput] = useState("");
    const [isGenerating, setIsGenerating] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || isGenerating) return;

        const userMsg: Message = { id: `msg-${Date.now()}`, role: "user", content: input };
        setMessages((prev) => [...prev, userMsg]);
        setInput("");
        setIsGenerating(true);

        const aiMsg: Message = { id: `msg-${Date.now() + 1}`, role: "ai", content: "AI 모델이 법규 및 일조권을 고려하여 3D 매스(Mass) 설계를 생성하고 있습니다...", status: "generating" };
        setMessages((prev) => [...prev, aiMsg]);

        // Simulate API latency for diffusion model / agent reasoning
        setTimeout(() => {
            setMessages((prev) => 
                prev.map((msg) => 
                    msg.id === aiMsg.id ? { 
                        ...msg, 
                        content: "설계 생성이 완료되었습니다. 대지면적 대비 건폐율 48%, 용적률 195%의 15층 오피스텔 스키마가 로드되었습니다. 우측 WebGL 뷰어에서 확인하십시오.", 
                        status: "complete" 
                    } : msg
                )
            );
            setIsGenerating(false);
        }, 3500);
    };

    return (
        <div className="flex flex-col h-[500px] w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-lg font-sans overflow-hidden">
            <div className="p-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900">
                <h3 className="font-bold text-slate-800 dark:text-slate-200 flex items-center gap-2">
                    <span className="text-xl">✨</span> PropAI Generative Agent
                </h3>
            </div>
            
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.map((msg) => (
                    <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-sm ${
                            msg.role === 'user' 
                                ? 'bg-blue-600 text-white rounded-br-none' 
                                : 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 rounded-bl-none border border-slate-200 dark:border-slate-700'
                        }`}>
                            {msg.status === "generating" ? (
                                <div className="flex items-center gap-2">
                                    <div className="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin"></div>
                                    {msg.content}
                                </div>
                            ) : (
                                <p className="leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                            )}
                        </div>
                    </div>
                ))}
                <div ref={messagesEndRef} />
            </div>

            <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900">
                <form onSubmit={handleSubmit} className="flex gap-2 relative">
                    <input 
                        type="text" 
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="예) 역삼동 700평 대지에 15층 규모의 친환경 오피스 건물 설계해줘" 
                        disabled={isGenerating}
                        className="flex-1 pl-4 pr-12 py-3 bg-white dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-full shadow-inner focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 text-sm text-slate-800 dark:text-slate-100 placeholder-slate-400"
                    />
                    <button 
                        type="submit" 
                        disabled={!input.trim() || isGenerating}
                        className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 flex items-center justify-center bg-blue-600 text-white rounded-full hover:bg-blue-700 transition disabled:opacity-50 disabled:hover:bg-blue-600"
                    >
                        <svg className="w-4 h-4 translate-x-[1px]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path></svg>
                    </button>
                </form>
            </div>
        </div>
    );
}
