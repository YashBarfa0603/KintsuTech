"use client";

import React, { useState } from "react";
import { Button } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";
import { supabase, isSupabaseConfigured } from "@/lib/supabase";
import { verifyTokenWithBackend } from "@/lib/api";

export function AuthModal({
  open,
  close,
  onUserChange,
}: {
  open: boolean;
  close: () => void;
  onUserChange: (user: { email: string; initials: string; role: string } | null) => void;
}) {
  const [email, setEmail] = useState("akira@kintsu.tech");
  const [password, setPassword] = useState("••••••••");
  const [isSignUp, setIsSignUp] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  if (!open) return null;

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setStatus("");

    try {
      if (isSupabaseConfigured()) {
        if (isSignUp) {
          const { data, error: signUpErr } = await supabase.auth.signUp({
            email,
            password,
          });
          if (signUpErr) throw signUpErr;
          setStatus("Check your email for confirmation link.");
          if (data.session?.access_token) {
            await verifyTokenWithBackend(data.session.access_token);
          }
        } else {
          const { data, error: signInErr } = await supabase.auth.signInWithPassword({
            email,
            password,
          });
          if (signInErr) throw signInErr;
          if (data.session?.access_token) {
            await verifyTokenWithBackend(data.session.access_token);
          }
          const initials = email.slice(0, 2).toUpperCase();
          onUserChange({ email, initials, role: "admin" });
          close();
        }
      } else {
        // Local prototype demo sign in
        const initials = email.slice(0, 2).toUpperCase();
        onUserChange({ email, initials, role: "Platform Engineer" });
        close();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Authentication error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-scrim" onClick={close}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <h2 className="font-bold text-lg text-stone-900">
            {isSignUp ? "Create KintsuTech Account" : "Sign In to KintsuTech"}
          </h2>
          <Button variant="icon" icon="close" onClick={close} />
        </div>

        <p className="modal-intro">
          Protected by Supabase verified authentication and role-based authorization policies.
        </p>

        <form onSubmit={handleAuth} className="space-y-4">
          <label className="form-label">
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>

          <label className="form-label">
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>

          {error && <p className="text-xs text-red-600 font-semibold">{error}</p>}
          {status && <p className="text-xs text-emerald-600 font-semibold">{status}</p>}

          <div className="flex items-center justify-between pt-3">
            <button
              type="button"
              className="text-xs text-stone-500 hover:text-stone-800 underline"
              onClick={() => setIsSignUp(!isSignUp)}
            >
              {isSignUp ? "Already have an account? Sign In" : "Need an account? Sign Up"}
            </button>
            <Button type="submit" disabled={loading}>
              {loading ? "Authenticating…" : isSignUp ? "Sign Up" : "Sign In"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
