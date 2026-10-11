"use client";

import React, { useState } from "react";
import { Screen } from "@/types";
import { Button } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";
import { sendAgentChatMessage } from "@/lib/api";

export function KintsuCopilot({
  open,
  close,
  context,
  navigate,
}: {
  open: boolean;
  close: () => void;
  context: string;
  navigate: (s: Screen) => void;
}) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ who: "user" | "ai"; text: string }[]>([
    {
      who: "ai",
      text: "I'm Kintsu Copilot, grounded in the current case evidence. Ask me about detected anomalies, impact tracing, or validation logs.",
    },
  ]);
  const [voiceActive, setVoiceActive] = useState(false);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim()) return;

    const q = input;
    setInput("");
    setMessages((prev) => [...prev, { who: "user", text: q }]);

    try {
      const res = await sendAgentChatMessage(q, undefined, { screen: context });
      if (res && res.response) {
        setMessages((prev) => [...prev, { who: "ai", text: res.response }]);
        return;
      }
    } catch {
      // Fallback to contextual response
    }

    const lower = q.toLowerCase();
    let answer =
      "I analyzed case KIN-2841 in Stripe API. The field `name` was replaced by `display_name` at 14:14 UTC across 412 observed responses.";

    if (lower.includes("fail") || lower.includes("failure")) {
      answer =
        "Validation failed on checkout regression check: expected total was 12900, received 13287 due to a tax calculation mismatch. Approval is blocked until resolved.";
    } else if (lower.includes("workflow") || lower.includes("impact")) {
      answer =
        "The AI Dependency Graph confirms 3 downstream workflows affected: Checkout, Order Total, and Order Receipt.";
    } else if (lower.includes("safe") || lower.includes("approve")) {
      answer =
        "Passing 14 deterministic checks makes the proposal eligible for review, but does not deploy automatically. Human platform engineer approval is enforced.";
    } else if (lower.includes("repair") || lower.includes("fix")) {
      answer =
        "The proposed fix creates a boundary adapter `normalizeIntent` with fallback `display_name ?? name` and source telemetry.";
    }

    setMessages((prev) => [...prev, { who: "ai", text: answer }]);
  };

  const toggleVoice = () => {
    if (voiceActive) {
      setVoiceActive(false);
      return;
    }
    setVoiceActive(true);
    window.setTimeout(() => {
      setInput("What changed in the Payment API?");
      setVoiceActive(false);
    }, 1500);
  };

  return (
    <>
      {open && <div className="assistant-scrim" onClick={close} />}
      <aside className={`assistant ${open ? "open" : ""}`}>
        <div className="assistant-head">
          <div className="copilot-icon">
            <Icon name="spark" size={16} />
          </div>
          <div>
            <h2>
              Kintsu Copilot <small>AI ASSISTANT</small>
            </h2>
            <span>Evidence simulation · {context}</span>
          </div>
          <Button variant="icon" icon="close" onClick={close} className="ml-auto" />
        </div>

        <div className="assistant-context">
          <span>ACTIVE CONTEXT</span>
          <button onClick={() => navigate("recovery")}>
            <Icon name="recovery" size={15} />
            <span>
              <strong>KIN-2841 · Stripe API</strong>
              <small>Pending review · Critical severity</small>
            </span>
          </button>
          <div className="assistant-links">
            <button onClick={() => navigate("changes")}>Evidence</button>
            <button onClick={() => navigate("graph")}>Impact path</button>
            <button onClick={() => navigate("validation")}>Test logs</button>
            <button onClick={() => navigate("history")}>History</button>
            <button
              onClick={() => {
                close();
                navigate("chat");
              }}
              className="text-emerald-700 font-semibold hover:underline"
            >
              Full Agent Chat ↗
            </button>
          </div>
        </div>

        <div className="chat">
          {messages.map((m, i) => (
            <div key={i} className={`message ${m.who}`}>
              <span>{m.who === "ai" ? <Icon name="spark" size={13} /> : "AK"}</span>
              <p>{m.text}</p>
            </div>
          ))}
        </div>

        <div className="suggestions">
          {[
            "What changed recently?",
            "Which workflows are affected?",
            "Why did validation fail?",
            "Is the proposed fix safe?",
          ].map((prompt) => (
            <button key={prompt} onClick={() => setInput(prompt)}>
              {prompt}
            </button>
          ))}
        </div>

        <form className="chat-input" onSubmit={handleSubmit}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask Kintsu Copilot about this workspace…"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit();
              }
            }}
          />
          <div>
            <Button
              variant={voiceActive ? "danger" : "secondary"}
              icon="mic"
              className="text-xs"
              onClick={toggleVoice}
            >
              {voiceActive ? "Listening…" : "Simulate voice"}
            </Button>
            <span>Press Enter to send</span>
            <Button type="submit" variant="primary" icon="arrow" />
          </div>
        </form>
      </aside>
    </>
  );
}
