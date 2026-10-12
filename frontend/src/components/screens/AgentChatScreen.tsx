"use client";

import React, { useState, useEffect, useRef } from "react";
import { Screen } from "@/types";
import { Button, Badge } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";
import { sendAgentChatMessage } from "@/lib/api";

export interface ChatMessage {
  id: string;
  sender: "user" | "agent";
  text: string;
  timestamp: string;
  toolsUsed?: string[];
  evidence?: Record<string, unknown>;
  source?: string;
  isError?: boolean;
}

interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: {
      [index: number]: {
        transcript: string;
      };
    };
  };
}

interface SpeechRecognitionErrorLike {
  error: string;
}

interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

interface WindowWithSpeechRec extends Window {
  SpeechRecognition?: new () => SpeechRecognitionLike;
  webkitSpeechRecognition?: new () => SpeechRecognitionLike;
}

let messageSeq = 0;
function createMessageId(prefix: string): string {
  messageSeq += 1;
  return `${prefix}-${messageSeq}`;
}

function formatCurrentTimestamp(): string {
  const date = new Date();
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function AgentChatScreen({
  navigate,
  currentProject = "Pulse API",
  currentEnv = "Staging",
}: {
  navigate?: (s: Screen) => void;
  currentProject?: string;
  currentEnv?: string;
}) {
  const welcomeMessage: ChatMessage = {
    id: "msg-welcome",
    sender: "agent",
    text: "Hello! I am the **KintsuTech Autonomous Agent**. I can analyze API drift, calculate blast radius across downstream consumers, explain compatibility repairs, and report live system health grounded in backend telemetry.\n\nHow can I assist your integrations today?",
    timestamp: formatCurrentTimestamp(),
    toolsUsed: ["system_knowledge"],
    source: "system_knowledge",
  };

  const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessage]);

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastFailedQuery, setLastFailedQuery] = useState<string | null>(null);

  // Voice Input (Speech-to-Text) state
  const [isRecording, setIsRecording] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const [speechError, setSpeechError] = useState("");
  const [handsFree, setHandsFree] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  const handsFreeRef = useRef(handsFree);
  useEffect(() => {
    handsFreeRef.current = handsFree;
  }, [handsFree]);
  const lastTranscriptRef = useRef("");
  const handleSendRef = useRef<(text?: string) => Promise<void>>(() => Promise.resolve());

  // Voice Output (Text-to-Speech) state
  const [ttsSupported, setTtsSupported] = useState(false);
  const [speakingMessageId, setSpeakingMessageId] = useState<string | null>(null);
  const [isPaused, setIsPaused] = useState(false);
  const [speechRate, setSpeechRate] = useState(1.0);
  const [autoSpeak, setAutoSpeak] = useState(false);
  const [availableVoices, setAvailableVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [selectedVoiceIndex, setSelectedVoiceIndex] = useState<number>(0);
  const [showVoiceSettings, setShowVoiceSettings] = useState(false);

  // Modals & UI
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Note: Chat messages are session-only. No localStorage persistence.

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Initialize Web Speech API capabilities (client-only)
  useEffect(() => {
    if (typeof window === "undefined") return;

    const timer = window.setTimeout(() => {
      // Speech Recognition check
      const win = window as unknown as WindowWithSpeechRec;
      const SpeechRecognitionConstructor =
        win.SpeechRecognition || win.webkitSpeechRecognition;
      if (SpeechRecognitionConstructor) {
        setSpeechSupported(true);
        const recog = new SpeechRecognitionConstructor();
        recog.continuous = false;
        recog.interimResults = true;
        recog.lang = "en-US";

        recog.onstart = () => {
          setIsRecording(true);
          setSpeechError("");
        };

        recog.onresult = (event: SpeechRecognitionEventLike) => {
          let transcript = "";
          for (let i = event.resultIndex; i < event.results.length; i++) {
            transcript += event.results[i][0].transcript;
          }
          if (transcript) {
            setInput(transcript);
            lastTranscriptRef.current = transcript;
          }
        };

        recog.onerror = (event: SpeechRecognitionErrorLike) => {
          setIsRecording(false);
          if (event.error === "not-allowed") {
            setSpeechError("Microphone permission was denied. Please allow microphone access.");
          } else if (event.error === "no-speech") {
            setSpeechError("No speech detected. Please try speaking again.");
          } else {
            setSpeechError(`Speech recognition error: ${event.error}`);
          }
        };

        recog.onend = () => {
          setIsRecording(false);
          if (handsFreeRef.current && lastTranscriptRef.current.trim()) {
            const queryToSend = lastTranscriptRef.current.trim();
            lastTranscriptRef.current = "";
            handleSendRef.current(queryToSend);
          }
        };

        recognitionRef.current = recog;
      }

      // Text to Speech check
      if ("speechSynthesis" in window) {
        setTtsSupported(true);
        const loadVoices = () => {
          const voices = window.speechSynthesis.getVoices();
          setAvailableVoices(voices);
        };
        loadVoices();
        if (window.speechSynthesis.onvoiceschanged !== undefined) {
          window.speechSynthesis.onvoiceschanged = loadVoices;
        }
      }
    }, 0);

    return () => {
      window.clearTimeout(timer);
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  // Voice output playback handler
  const playSpeech = (text: string, messageId: string) => {
    if (!ttsSupported || typeof window === "undefined") return;

    // Stop any existing playback first (prevents overlapping speech!)
    window.speechSynthesis.cancel();

    // Remove markdown symbols for smooth, natural audio reading
    const cleanText = text
      .replace(/[*#`_~]/g, "")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/\n+/g, " ");

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = speechRate;

    if (availableVoices.length > 0 && availableVoices[selectedVoiceIndex]) {
      utterance.voice = availableVoices[selectedVoiceIndex];
    }

    utterance.onstart = () => {
      setSpeakingMessageId(messageId);
      setIsPaused(false);
    };

    utterance.onend = () => {
      setSpeakingMessageId(null);
      setIsPaused(false);
    };

    utterance.onerror = () => {
      setSpeakingMessageId(null);
      setIsPaused(false);
    };

    window.speechSynthesis.speak(utterance);
  };

  const pauseResumeSpeech = () => {
    if (!ttsSupported || typeof window === "undefined") return;
    if (isPaused) {
      window.speechSynthesis.resume();
      setIsPaused(false);
    } else {
      window.speechSynthesis.pause();
      setIsPaused(true);
    }
  };

  const stopSpeech = () => {
    if (!ttsSupported || typeof window === "undefined") return;
    window.speechSynthesis.cancel();
    setSpeakingMessageId(null);
    setIsPaused(false);
  };

  // Toggle voice recording
  const toggleRecording = () => {
    if (!speechSupported) {
      setSpeechError("Speech recognition is not supported in this browser.");
      return;
    }

    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
    } else {
      setSpeechError("");
      try {
        recognitionRef.current?.start();
      } catch (err: unknown) {
        // Recognition already started or error
        setSpeechError(err instanceof Error ? err.message : "Speech recognition failed to start");
      }
    }
  };

  // Send message
  const handleSend = async (customText?: string) => {
    handleSendRef.current = handleSend;
    const textToSend = customText !== undefined ? customText : input;
    if (!textToSend.trim() || loading) return;

    const userMessage: ChatMessage = {
      id: createMessageId("usr"),
      sender: "user",
      text: textToSend.trim(),
      timestamp: formatCurrentTimestamp(),
    };

    const newHistory = [...messages, userMessage];
    setMessages(newHistory);
    setInput("");
    setLoading(true);
    setLastFailedQuery(null);

    // If recording was active, stop it
    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
    }

    try {
      const historyContext = newHistory.slice(-6).map((m) => ({
        role: m.sender === "user" ? "user" : "assistant",
        content: m.text,
      }));

      const res = await sendAgentChatMessage(userMessage.text, historyContext, {
        project: currentProject,
        environment: currentEnv,
      });

      const agentMessage: ChatMessage = {
        id: createMessageId("agt"),
        sender: "agent",
        text: res.response,
        timestamp: formatCurrentTimestamp(),
        toolsUsed: res.tools_used,
        evidence: res.evidence,
        source: res.source,
      };

      setMessages((prev) => [...prev, agentMessage]);

      // If auto-speak is enabled, read response aloud immediately
      if (autoSpeak) {
        playSpeech(agentMessage.text, agentMessage.id);
      }
    } catch (err: unknown) {
      setLastFailedQuery(userMessage.text);
      const errorMessage: ChatMessage = {
        id: createMessageId("err"),
        sender: "agent",
        text: `⚠️ **Unable to retrieve verified response**: ${
          err instanceof Error ? err.message : "Network error"
        }. Please check that the FastAPI backend is running on port 8000 and try again.`,
        timestamp: formatCurrentTimestamp(),
        isError: true,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleClearChat = () => {
    stopSpeech();
    messageSeq = 0;
    setMessages([
      {
        id: "msg-welcome-reset",
        sender: "agent",
        text: "Conversation cleared. How can I assist your integrations?",
        timestamp: formatCurrentTimestamp(),
        toolsUsed: ["system_knowledge"],
      },
    ]);
    setShowClearConfirm(false);
  };

  const starterPrompts = [
    "What is KintsuTech?",
    "Why is my weather API failing?",
    "What API changes were detected?",
    "Show me the latest incidents.",
    "Which consumers are affected by this API change?",
    "Explain the proposed repair.",
    "Has this repair passed validation?",
    "What happens if I roll back the repair?",
    "Summarize the current system health.",
  ];

  return (
    <>
      {/* Page Header */}
      <div className="page-header">
        <div className="page-heading-wrap">
          <button className="page-back" onClick={() => navigate?.("overview")}>
            <Icon name="arrow" className="rotate-180" size={14} /> Back
          </button>
          <div>
            <div className="breadcrumbs">
              <span>{currentProject.toUpperCase()}</span>
              <Icon name="chevron" size={10} />
              <span>{currentEnv.toUpperCase()}</span>
              <Icon name="chevron" size={10} />
              <span>AI AGENT CHAT</span>
              <span className="ml-1">
                <Badge tone="success">ONLINE · VERIFIED BACKEND</Badge>
              </span>
            </div>
            <h1>Chat with AI Agent</h1>
            <p>
              Autonomous conversational agent with voice input, text-to-speech, and live backend tool diagnostics.
            </p>
          </div>
        </div>
        <div className="page-actions">
          {speakingMessageId && (
            <Button variant="danger" icon="close" onClick={stopSpeech}>
              Stop Audio
            </Button>
          )}
          <Button
            variant="secondary"
            onClick={() => setShowVoiceSettings(true)}
          >
            Voice Settings
          </Button>
          <Button
            variant="ghost"
            onClick={() => setShowClearConfirm(true)}
          >
            Clear Chat
          </Button>
        </div>
      </div>

      {/* Main Chat Shell */}
      <div className="panel max-w-4xl mx-auto flex flex-col h-[700px] shadow-sm overflow-hidden mb-8">
        {/* Top Status Bar */}
        <div className="p-3.5 bg-stone-50 border-b border-stone-200 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <strong className="text-stone-800">KintsuTech AI Agent</strong>
            <span className="text-stone-400">· Grounded in FastAPI tool diagnostics</span>
          </div>
          <div className="flex items-center gap-3 text-stone-500">
            {isRecording && (
              <span className="text-red-600 font-semibold flex items-center gap-1 animate-pulse">
                <Icon name="mic" size={13} /> Listening to your microphone...
              </span>
            )}
            {speakingMessageId && (
              <span className="text-emerald-700 font-semibold flex items-center gap-1">
                <Icon name="spark" size={13} /> Playing response audio
              </span>
            )}
            <Badge tone="neutral">Port 8000 Connected</Badge>
          </div>
        </div>

        {/* Message Stream */}
        <div className="flex-1 p-5 overflow-y-auto space-y-4 bg-[#FAF8F5]">
          {messages.map((m) => {
            const isUser = m.sender === "user";
            const isPlayingThis = speakingMessageId === m.id;

            return (
              <div
                key={m.id}
                className={`flex gap-3 max-w-2xl ${isUser ? "ml-auto flex-row-reverse" : "mr-auto"}`}
              >
                {/* Avatar */}
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold ${
                    isUser
                      ? "bg-stone-800 text-white"
                      : "bg-[#0A332C] text-[#C6923C] border border-[#C6923C]/30"
                  }`}
                >
                  {isUser ? "AK" : <Icon name="spark" size={15} />}
                </div>

                {/* Message Bubble */}
                <div className="flex flex-col gap-1">
                  <div
                    className={`p-4 rounded-xl text-sm leading-relaxed ${
                      isUser
                        ? "bg-[#0A332C] text-white rounded-tr-none shadow-sm"
                        : m.isError
                        ? "bg-red-50 text-red-900 border border-red-200 rounded-tl-none"
                        : "bg-white text-stone-900 border border-stone-200 rounded-tl-none shadow-sm"
                    }`}
                  >
                    <div className="whitespace-pre-wrap">{m.text}</div>

                    {/* Tools used pill tags */}
                    {m.toolsUsed && m.toolsUsed.length > 0 && (
                      <div className="mt-3 pt-2 border-t border-stone-100 flex flex-wrap gap-1 items-center">
                        <span className="text-[10px] font-bold text-stone-400 uppercase tracking-wider mr-1">
                          TOOLS:
                        </span>
                        {m.toolsUsed.map((t) => (
                          <span
                            key={t}
                            className="text-[10px] px-1.5 py-0.5 rounded bg-stone-100 text-stone-600 font-mono font-medium"
                          >
                            ✓ {t}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Bubble Metadata & TTS Controls */}
                  <div
                    className={`flex items-center gap-2 text-[11px] text-stone-400 px-1 ${
                      isUser ? "justify-end" : "justify-start"
                    }`}
                  >
                    <span>{m.timestamp}</span>

                    {/* TTS Button on Assistant responses */}
                    {!isUser && !m.isError && ttsSupported && (
                      <div className="flex items-center gap-1 ml-2">
                        {isPlayingThis ? (
                          <>
                            <button
                              onClick={pauseResumeSpeech}
                              className="text-stone-600 hover:text-stone-900 font-semibold px-1 rounded flex items-center gap-0.5"
                            >
                              <Icon name={isPaused ? "play" : "clock"} size={12} />
                              {isPaused ? "Resume" : "Pause"}
                            </button>
                            <button
                              onClick={stopSpeech}
                              className="text-red-600 hover:text-red-800 font-semibold px-1 rounded flex items-center gap-0.5"
                            >
                              <Icon name="close" size={12} />
                              Stop
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => playSpeech(m.text, m.id)}
                            className="text-emerald-700 hover:text-emerald-900 font-semibold flex items-center gap-1 px-1 rounded transition-colors"
                          >
                            <Icon name="spark" size={12} /> Listen
                          </button>
                        )}
                      </div>
                    )}

                    {m.isError && lastFailedQuery && (
                      <button
                        onClick={() => handleSend(lastFailedQuery)}
                        className="text-red-700 font-semibold hover:underline ml-2"
                      >
                        Retry query
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}

          {/* Loading indicator */}
          {loading && (
            <div className="flex gap-3 max-w-2xl mr-auto">
              <div className="w-8 h-8 rounded-full bg-[#0A332C] text-[#C6923C] flex items-center justify-center flex-shrink-0 text-xs font-bold">
                <Icon name="spark" size={15} />
              </div>
              <div className="p-4 bg-white border border-stone-200 rounded-xl rounded-tl-none text-xs text-stone-500 flex items-center gap-2 shadow-sm">
                <span className="w-2 h-2 rounded-full bg-emerald-600 animate-ping" />
                Analyzing backend telemetry and executing diagnostic tools...
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Speech recognition error banner */}
        {speechError && (
          <div className="p-2.5 bg-red-50 border-t border-red-200 text-red-800 text-xs flex items-center justify-between">
            <span>⚠️ {speechError}</span>
            <button onClick={() => setSpeechError("")} className="font-bold text-red-700">
              ×
            </button>
          </div>
        )}

        {/* Suggested Starter Prompts Carousel */}
        <div className="px-4 py-2 bg-stone-50 border-t border-stone-200 flex items-center gap-2 overflow-x-auto text-xs whitespace-nowrap">
          <span className="text-[10px] font-bold text-stone-400 uppercase">SUGGESTED:</span>
          {starterPrompts.map((p) => (
            <button
              key={p}
              onClick={() => handleSend(p)}
              disabled={loading}
              className="px-2.5 py-1 bg-white border border-stone-200 hover:border-stone-400 text-stone-700 rounded-full transition-all text-xs flex-shrink-0"
            >
              {p}
            </button>
          ))}
        </div>

        {/* Input Bar */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="p-3 bg-white border-t border-stone-200 flex items-end gap-2"
        >
          {/* Microphone button */}
          <button
            type="button"
            onClick={toggleRecording}
            className={`p-2.5 rounded-lg border transition-all flex items-center justify-center flex-shrink-0 ${
              isRecording
                ? "bg-red-600 text-white border-red-700 animate-pulse shadow-md"
                : "bg-stone-50 hover:bg-stone-100 text-stone-700 border-stone-200"
            }`}
            title={isRecording ? "Stop recording" : "Speak your query (Speech to Text)"}
          >
            <Icon name={isRecording ? "close" : "mic"} size={17} />
          </button>

          {/* Multiline textarea */}
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              isRecording
                ? "Listening... Speak now..."
                : "Ask about API changes, failure diagnostics, impact, or recovery... (Enter to send)"
            }
            rows={1}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            className="flex-1 p-2.5 bg-stone-50 border border-stone-200 rounded-lg text-sm text-stone-900 focus:bg-white focus:border-stone-400 outline-none resize-none max-h-32 min-h-[42px]"
          />

          {/* Send button */}
          <Button
            type="submit"
            disabled={!input.trim() || loading}
            icon="arrow"
            className="h-[42px] px-4"
          >
            Send
          </Button>
        </form>
      </div>

      {/* Voice Settings Modal */}
      {showVoiceSettings && (
        <div className="modal-scrim" onClick={() => setShowVoiceSettings(false)}>
          <section className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-head">
              <h2 className="text-base font-bold text-stone-900">Voice & Speech Settings</h2>
              <Button variant="icon" icon="close" onClick={() => setShowVoiceSettings(false)} />
            </div>

            <div className="space-y-4 text-xs">
              <div>
                <label className="font-semibold text-stone-800 block mb-1">
                  Automatic Audio Playback
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="autoSpeak"
                    checked={autoSpeak}
                    onChange={(e) => setAutoSpeak(e.target.checked)}
                    className="rounded"
                  />
                  <label htmlFor="autoSpeak" className="text-stone-600">
                    Automatically read assistant responses aloud
                  </label>
                </div>
              </div>

              <div>
                <label className="font-semibold text-stone-800 block mb-1">
                  Hands-Free Voice Input
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="handsFree"
                    checked={handsFree}
                    onChange={(e) => setHandsFree(e.target.checked)}
                    className="rounded"
                  />
                  <label htmlFor="handsFree" className="text-stone-600">
                    Auto-send recognized voice message without manual click
                  </label>
                </div>
              </div>

              <div>
                <label className="font-semibold text-stone-800 block mb-1">
                  Speech Rate ({speechRate}x)
                </label>
                <input
                  type="range"
                  min="0.75"
                  max="1.5"
                  step="0.05"
                  value={speechRate}
                  onChange={(e) => setSpeechRate(parseFloat(e.target.value))}
                  className="w-full"
                />
              </div>

              {availableVoices.length > 0 && (
                <div>
                  <label className="font-semibold text-stone-800 block mb-1">
                    Speech Voice ({availableVoices.length} detected)
                  </label>
                  <select
                    value={selectedVoiceIndex}
                    onChange={(e) => setSelectedVoiceIndex(parseInt(e.target.value))}
                    className="w-full p-2 border border-stone-200 rounded text-xs"
                  >
                    {availableVoices.map((v, i) => (
                      <option key={i} value={i}>
                        {v.name} ({v.lang})
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <div className="modal-actions">
              <Button onClick={() => setShowVoiceSettings(false)}>Save Settings</Button>
            </div>
          </section>
        </div>
      )}

      {/* Clear Confirmation Modal */}
      {showClearConfirm && (
        <div className="modal-scrim" onClick={() => setShowClearConfirm(false)}>
          <section className="modal" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-base font-bold text-stone-900">Clear Conversation?</h2>
            <p className="modal-intro">
              This will remove all saved chat messages from local browser storage.
            </p>
            <div className="modal-actions">
              <Button variant="ghost" onClick={() => setShowClearConfirm(false)}>
                Cancel
              </Button>
              <Button variant="danger" onClick={handleClearChat}>
                Clear All Messages
              </Button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
