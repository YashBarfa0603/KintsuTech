"use client";

import React, { useState, useEffect } from "react";
import { Logo } from "@/components/ui/Icons";
import { supabase, isSupabaseConfigured } from "@/lib/supabase";
import { verifyTokenWithBackend } from "@/lib/api";
import "./auth/auth.css";

interface AuthScreenProps {
  initialMode?: "signin" | "signup";
  onSuccess: () => void;
  onBack: () => void;
}

export function AuthScreen({
  initialMode = "signin",
  onSuccess,
  onBack,
}: AuthScreenProps) {
  const [mode, setMode] = useState<"signin" | "signup">(initialMode);

  // Sign In state
  const [signInEmail, setSignInEmail] = useState("");
  const [signInPassword, setSignInPassword] = useState("");
  const [showSignInPassword, setShowSignInPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);

  // Sign Up state
  const [fullName, setFullName] = useState("");
  const [signUpEmail, setSignUpEmail] = useState("");
  const [organization, setOrganization] = useState("");
  const [role, setRole] = useState("");
  const [signUpPassword, setSignUpPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showSignUpPassword, setShowSignUpPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [agreedTerms, setAgreedTerms] = useState(false);

  // UI status & validation
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState<"google" | "github" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isEmailUnverified, setIsEmailUnverified] = useState(false);
  const [showCheckEmailView, setShowCheckEmailView] = useState(false);
  const [pendingVerificationEmail, setPendingVerificationEmail] = useState("");

  // Resend cooldown
  const [resendCooldown, setResendCooldown] = useState(0);
  const [resendStatus, setResendStatus] = useState<string | null>(null);

  useEffect(() => {
    setMode(initialMode);
    setError(null);
    setFieldErrors({});
    setIsEmailUnverified(false);
  }, [initialMode]);

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (resendCooldown > 0) {
      timer = setTimeout(() => setResendCooldown((prev) => prev - 1), 1000);
    }
    return () => clearTimeout(timer);
  }, [resendCooldown]);

  const validateEmail = (email: string) => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  };

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsEmailUnverified(false);
    setResendStatus(null);
    const errors: Record<string, string> = {};

    if (!signInEmail.trim()) {
      errors.signInEmail = "Please enter your work email.";
    } else if (!validateEmail(signInEmail.trim())) {
      errors.signInEmail = "Please enter a valid email address.";
    }

    if (!signInPassword) {
      errors.signInPassword = "Please enter your password.";
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }
    setFieldErrors({});
    setLoading(true);

    try {
      if (isSupabaseConfigured()) {
        const { data, error: signInErr } = await supabase.auth.signInWithPassword({
          email: signInEmail.trim(),
          password: signInPassword,
        });

        if (signInErr) {
          const errMsg = signInErr.message.toLowerCase();
          if (errMsg.includes("email not confirmed") || errMsg.includes("unconfirmed")) {
            setIsEmailUnverified(true);
            setPendingVerificationEmail(signInEmail.trim());
            setError("Your email has not been verified yet. Please check your inbox or resend the verification email.");
            return;
          }
          throw signInErr;
        }

        if (data.session?.access_token) {
          try {
            await verifyTokenWithBackend(data.session.access_token);
          } catch {
            // Non-fatal if backend verification is optional in local development
          }
        }
        onSuccess();
      } else {
        setError(
          "Supabase is not configured. Please set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local to authenticate."
        );
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Authentication failed";
      if (msg.toLowerCase().includes("invalid login credentials")) {
        setError("Invalid email or password. Please verify and try again.");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResendStatus(null);
    const errors: Record<string, string> = {};

    if (!fullName.trim()) {
      errors.fullName = "Please enter your full name.";
    }
    if (!signUpEmail.trim()) {
      errors.signUpEmail = "Please enter your work email.";
    } else if (!validateEmail(signUpEmail.trim())) {
      errors.signUpEmail = "Please enter a valid email address.";
    }
    if (!organization.trim()) {
      errors.organization = "Please enter your organization name.";
    }
    if (!role) {
      errors.role = "Please select your role.";
    }
    if (!signUpPassword) {
      errors.signUpPassword = "Please create a password.";
    } else if (signUpPassword.length < 8 || !/[a-zA-Z]/.test(signUpPassword) || !/[0-9]/.test(signUpPassword)) {
      errors.signUpPassword = "Password must be at least 8 characters with a letter and a number.";
    }
    if (!confirmPassword) {
      errors.confirmPassword = "Please confirm your password.";
    } else if (signUpPassword !== confirmPassword) {
      errors.confirmPassword = "Passwords do not match.";
    }
    if (!agreedTerms) {
      errors.agreedTerms = "You must agree to the Terms of Service and Privacy Policy.";
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }
    setFieldErrors({});
    setLoading(true);

    try {
      if (isSupabaseConfigured()) {
        const { data, error: signUpErr } = await supabase.auth.signUp({
          email: signUpEmail.trim(),
          password: signUpPassword,
          options: {
            data: {
              full_name: fullName.trim(),
              organization: organization.trim(),
              role: role,
            },
            emailRedirectTo: typeof window !== "undefined" ? window.location.origin : undefined,
          },
        });

        if (signUpErr) throw signUpErr;

        // Check if email confirmation is required (session is null)
        if (!data.session) {
          setPendingVerificationEmail(signUpEmail.trim());
          setShowCheckEmailView(true);
        } else {
          if (data.session.access_token) {
            try {
              await verifyTokenWithBackend(data.session.access_token);
            } catch {
              // optional backend token verification
            }
          }
          onSuccess();
        }
      } else {
        setError(
          "Supabase is not configured. Please set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local to register."
        );
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Sign up failed";
      if (msg.toLowerCase().includes("already registered")) {
        setError("An account with this email already exists. Please sign in instead.");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleOAuth = async (provider: "google" | "github") => {
    setError(null);
    setOauthLoading(provider);

    try {
      if (!isSupabaseConfigured()) {
        setError(
          "Supabase is not configured. Please set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local to authenticate with Google or GitHub."
        );
        setOauthLoading(null);
        return;
      }

      const redirectUrl = typeof window !== "undefined" ? window.location.origin : undefined;
      const { data, error: oauthErr } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo: redirectUrl,
        },
      });
      if (oauthErr) throw oauthErr;
      if (data?.url) {
        window.location.href = data.url;
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `Failed to sign in with ${provider}`);
      setOauthLoading(null);
    }
  };

  const handleResendVerification = async () => {
    const targetEmail = pendingVerificationEmail || signInEmail || signUpEmail;
    if (!targetEmail) return;

    setResendCooldown(60);
    setResendStatus("Sending verification email...");

    try {
      if (isSupabaseConfigured()) {
        const { error: resendErr } = await supabase.auth.resend({
          type: "signup",
          email: targetEmail,
          options: {
            emailRedirectTo: typeof window !== "undefined" ? window.location.origin : undefined,
          },
        });
        if (resendErr) throw resendErr;
      }
      setResendStatus("Verification email sent! Check your inbox and spam folder.");
    } catch (err: unknown) {
      setResendStatus(null);
      setError(err instanceof Error ? err.message : "Could not resend verification email.");
    }
  };

  return (
    <div className="auth-screen-layout">
      {/* Left Column: Editorial Hero & Value Proposition */}
      <section className="auth-hero-column">
        <div className="auth-hero-header">
          <button className="auth-back-home" onClick={onBack} aria-label="Return to KintsuTech home">
            <Logo />
          </button>
          <button className="auth-back-home" onClick={onBack}>
            ← Back to home
          </button>
        </div>

        <div className="auth-hero-body">
          <span className="auth-eyebrow">RESILIENCE, BY DESIGN</span>
          <h1 className="auth-hero-title">Build with resilience.</h1>
          <p className="auth-hero-desc">
            Connect your APIs, monitor reliability, and manage recovery from one secure workspace.
          </p>

          <div className="auth-feature-list">
            <div className="auth-feature-item">
              <span className="auth-feature-num">01</span>
              <div className="auth-feature-info">
                <h2 className="auth-feature-title">Detect changes early</h2>
                <p className="auth-feature-desc">
                  Identify undocumented changes across APIs, SDKs, MCP servers, and webhooks.
                </p>
              </div>
            </div>

            <div className="auth-feature-item">
              <span className="auth-feature-num">02</span>
              <div className="auth-feature-info">
                <h2 className="auth-feature-title">Trace real impact</h2>
                <p className="auth-feature-desc">
                  Understand which applications, components, and workflows may be affected.
                </p>
              </div>
            </div>

            <div className="auth-feature-item">
              <span className="auth-feature-num">03</span>
              <div className="auth-feature-info">
                <h2 className="auth-feature-title">Prove before you patch</h2>
                <p className="auth-feature-desc">
                  Validate controlled repair proposals before developer approval.
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="auth-hero-footer">
          <div className="auth-connection-bar" aria-hidden="true">
            <div className="auth-node-pill">
              <span className="auth-node-dot" />
              <span>APP</span>
            </div>
            <div className="auth-node-line" />
            <div className="auth-node-pill">
              <span className="auth-node-dot" />
              <span>API</span>
            </div>
          </div>
        </div>
      </section>

      {/* Right Column: Authentication Form */}
      <section className="auth-form-column">
        <div className="auth-form-card">
          {showCheckEmailView ? (
            /* Email Verification State */
            <div className="auth-verify-card">
              <div className="auth-verify-icon">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect width="20" height="16" x="2" y="4" rx="2" />
                  <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
                </svg>
              </div>
              <span className="auth-eyebrow">VERIFICATION PENDING</span>
              <h2 className="auth-verify-title">Check your email</h2>
              <p className="auth-verify-desc">
                We sent a confirmation link to <strong>{pendingVerificationEmail}</strong>. Click the link in that email to activate your account and start using KintsuTech.
              </p>

              {resendStatus && (
                <div className="auth-alert auth-alert-success">
                  {resendStatus}
                </div>
              )}
              {error && (
                <div className="auth-alert auth-alert-error">
                  {error}
                </div>
              )}

              <div className="auth-resend-group">
                <button
                  type="button"
                  className="auth-submit-btn"
                  onClick={handleResendVerification}
                  disabled={resendCooldown > 0}
                >
                  {resendCooldown > 0
                    ? `Resend available in ${resendCooldown}s`
                    : "Resend verification email"}
                </button>
                <button
                  type="button"
                  className="auth-link-sm"
                  onClick={() => {
                    setShowCheckEmailView(false);
                    setMode("signin");
                  }}
                >
                  Back to Sign In
                </button>
              </div>
            </div>
          ) : mode === "signin" ? (
            /* Sign In Mode */
            <>
              <div className="auth-form-header">
                <span className="auth-eyebrow">SECURE WORKSPACE ACCESS</span>
                <h2 className="auth-form-title">Welcome back</h2>
                <p className="auth-form-subtitle">Sign in to your KintsuTech workspace</p>
              </div>

              {error && (
                <div className="auth-alert auth-alert-error">
                  <span>{error}</span>
                  {isEmailUnverified && (
                    <button
                      type="button"
                      className="auth-alert-action-btn"
                      onClick={handleResendVerification}
                      disabled={resendCooldown > 0}
                    >
                      {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend confirmation email"}
                    </button>
                  )}
                </div>
              )}

              {resendStatus && (
                <div className="auth-alert auth-alert-success">
                  {resendStatus}
                </div>
              )}

              <form onSubmit={handleSignIn} className="auth-form" noValidate>
                <div className="auth-field">
                  <label className="auth-label" htmlFor="signin-email">
                    Email address
                  </label>
                  <input
                    id="signin-email"
                    type="email"
                    className={`auth-input ${fieldErrors.signInEmail ? "has-error" : ""}`}
                    placeholder="Enter your work email"
                    value={signInEmail}
                    onChange={(e) => {
                      setSignInEmail(e.target.value);
                      if (fieldErrors.signInEmail) setFieldErrors((prev) => ({ ...prev, signInEmail: "" }));
                    }}
                    autoComplete="email"
                  />
                  {fieldErrors.signInEmail && (
                    <span className="auth-field-error">{fieldErrors.signInEmail}</span>
                  )}
                </div>

                <div className="auth-field">
                  <div className="auth-label-row">
                    <label className="auth-label" htmlFor="signin-password">
                      Password
                    </label>
                    <button
                      type="button"
                      className="auth-link-sm"
                      onClick={() => alert("Password reset link will be sent to your email.")}
                    >
                      Forgot password?
                    </button>
                  </div>
                  <div className="auth-input-wrapper">
                    <input
                      id="signin-password"
                      type={showSignInPassword ? "text" : "password"}
                      className={`auth-input ${fieldErrors.signInPassword ? "has-error" : ""}`}
                      placeholder="Enter your password"
                      value={signInPassword}
                      onChange={(e) => {
                        setSignInPassword(e.target.value);
                        if (fieldErrors.signInPassword) setFieldErrors((prev) => ({ ...prev, signInPassword: "" }));
                      }}
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      className="auth-input-toggle"
                      onClick={() => setShowSignInPassword((s) => !s)}
                    >
                      {showSignInPassword ? "Hide" : "Show"}
                    </button>
                  </div>
                  {fieldErrors.signInPassword && (
                    <span className="auth-field-error">{fieldErrors.signInPassword}</span>
                  )}
                </div>

                <label className="auth-checkbox-label">
                  <input
                    type="checkbox"
                    className="auth-checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                  />
                  <span>Remember me</span>
                </label>

                <button type="submit" className="auth-submit-btn" disabled={loading}>
                  {loading ? "Signing in…" : "Sign in →"}
                </button>

                <div className="auth-divider">
                  <span>or continue with</span>
                </div>

                <div className="auth-oauth-grid">
                  <button
                    type="button"
                    className="auth-oauth-btn"
                    onClick={() => handleOAuth("google")}
                    disabled={oauthLoading !== null}
                  >
                    <svg className="auth-oauth-icon" viewBox="0 0 24 24">
                      <path
                        fill="#EA4335"
                        d="M12 5c1.6 0 3 .6 4.1 1.6l3.1-3.1C17.3 1.7 14.8 1 12 1 7.5 1 3.7 3.6 1.9 7.3l3.7 2.9C6.5 7.4 9 5 12 5z"
                      />
                      <path
                        fill="#4285F4"
                        d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5c-.3 1.5-1.1 2.8-2.4 3.7l3.7 2.9c2.2-2 3.7-5.1 3.7-8.8z"
                      />
                      <path
                        fill="#FBBC05"
                        d="M5.6 14.8c-.2-.7-.4-1.5-.4-2.3 0-.8.2-1.6.4-2.3L1.9 7.3C.7 9.7 0 12.3 0 15s.7 5.3 1.9 7.7l3.7-2.9z"
                      />
                      <path
                        fill="#34A853"
                        d="M12 24c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3 0-5.5-2-6.4-4.8L1.9 17.4C3.7 21.1 7.5 24 12 24z"
                      />
                    </svg>
                    <span>{oauthLoading === "google" ? "Connecting…" : "Google"}</span>
                  </button>

                  <button
                    type="button"
                    className="auth-oauth-btn"
                    onClick={() => handleOAuth("github")}
                    disabled={oauthLoading !== null}
                  >
                    <svg className="auth-oauth-icon" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
                    </svg>
                    <span>{oauthLoading === "github" ? "Connecting…" : "GitHub"}</span>
                  </button>
                </div>

                <div className="auth-switch-prompt">
                  <span>New to KintsuTech?</span>
                  <button
                    type="button"
                    className="auth-switch-btn"
                    onClick={() => {
                      setMode("signup");
                      setError(null);
                      setFieldErrors({});
                    }}
                  >
                    Create an account
                  </button>
                </div>
              </form>
            </>
          ) : (
            /* Sign Up Mode */
            <>
              <div className="auth-form-header">
                <h2 className="auth-form-title">Create your KintsuTech account</h2>
                <p className="auth-form-subtitle">Get your API resilience workspace up and running.</p>
                <p className="auth-form-desc">
                  Create an account to monitor dependencies, investigate changes, and manage verified repairs.
                </p>
              </div>

              {error && (
                <div className="auth-alert auth-alert-error">
                  {error}
                </div>
              )}

              <form onSubmit={handleSignUp} className="auth-form" noValidate>
                <div className="auth-field">
                  <label className="auth-label" htmlFor="signup-name">
                    Full name *
                  </label>
                  <input
                    id="signup-name"
                    type="text"
                    className={`auth-input ${fieldErrors.fullName ? "has-error" : ""}`}
                    placeholder="Enter your full name"
                    value={fullName}
                    onChange={(e) => {
                      setFullName(e.target.value);
                      if (fieldErrors.fullName) setFieldErrors((prev) => ({ ...prev, fullName: "" }));
                    }}
                    autoComplete="name"
                  />
                  {fieldErrors.fullName && (
                    <span className="auth-field-error">{fieldErrors.fullName}</span>
                  )}
                </div>

                <div className="auth-field">
                  <label className="auth-label" htmlFor="signup-email">
                    Work email *
                  </label>
                  <input
                    id="signup-email"
                    type="email"
                    className={`auth-input ${fieldErrors.signUpEmail ? "has-error" : ""}`}
                    placeholder="your@company.com"
                    value={signUpEmail}
                    onChange={(e) => {
                      setSignUpEmail(e.target.value);
                      if (fieldErrors.signUpEmail) setFieldErrors((prev) => ({ ...prev, signUpEmail: "" }));
                    }}
                    autoComplete="email"
                  />
                  {fieldErrors.signUpEmail && (
                    <span className="auth-field-error">{fieldErrors.signUpEmail}</span>
                  )}
                </div>

                <div className="auth-field">
                  <label className="auth-label" htmlFor="signup-org">
                    Organization / company name *
                  </label>
                  <input
                    id="signup-org"
                    type="text"
                    className={`auth-input ${fieldErrors.organization ? "has-error" : ""}`}
                    placeholder="Enter your organization"
                    value={organization}
                    onChange={(e) => {
                      setOrganization(e.target.value);
                      if (fieldErrors.organization) setFieldErrors((prev) => ({ ...prev, organization: "" }));
                    }}
                    autoComplete="organization"
                  />
                  {fieldErrors.organization && (
                    <span className="auth-field-error">{fieldErrors.organization}</span>
                  )}
                </div>

                <div className="auth-field">
                  <label className="auth-label" htmlFor="signup-role">
                    Your role *
                  </label>
                  <select
                    id="signup-role"
                    className={`auth-select ${fieldErrors.role ? "has-error" : ""}`}
                    value={role}
                    onChange={(e) => {
                      setRole(e.target.value);
                      if (fieldErrors.role) setFieldErrors((prev) => ({ ...prev, role: "" }));
                    }}
                  >
                    <option value="" disabled>Select your role</option>
                    <option value="Software Engineer">Software Engineer</option>
                    <option value="Tech Lead / Architect">Tech Lead / Architect</option>
                    <option value="DevOps / SRE">DevOps / SRE</option>
                    <option value="Engineering Manager">Engineering Manager</option>
                    <option value="Security / Compliance">Security / Compliance</option>
                    <option value="Product Manager">Product Manager</option>
                    <option value="Other">Other</option>
                  </select>
                  {fieldErrors.role && (
                    <span className="auth-field-error">{fieldErrors.role}</span>
                  )}
                </div>

                <div className="auth-field">
                  <label className="auth-label" htmlFor="signup-password">
                    Password *
                  </label>
                  <div className="auth-input-wrapper">
                    <input
                      id="signup-password"
                      type={showSignUpPassword ? "text" : "password"}
                      className={`auth-input ${fieldErrors.signUpPassword ? "has-error" : ""}`}
                      placeholder="Create a strong password"
                      value={signUpPassword}
                      onChange={(e) => {
                        setSignUpPassword(e.target.value);
                        if (fieldErrors.signUpPassword) setFieldErrors((prev) => ({ ...prev, signUpPassword: "" }));
                      }}
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      className="auth-input-toggle"
                      onClick={() => setShowSignUpPassword((s) => !s)}
                    >
                      {showSignUpPassword ? "Hide" : "Show"}
                    </button>
                  </div>
                  <span className="auth-field-hint">At least 8 characters with a letter and number.</span>
                  {fieldErrors.signUpPassword && (
                    <span className="auth-field-error">{fieldErrors.signUpPassword}</span>
                  )}
                </div>

                <div className="auth-field">
                  <label className="auth-label" htmlFor="signup-confirm-password">
                    Confirm password *
                  </label>
                  <div className="auth-input-wrapper">
                    <input
                      id="signup-confirm-password"
                      type={showConfirmPassword ? "text" : "password"}
                      className={`auth-input ${fieldErrors.confirmPassword ? "has-error" : ""}`}
                      placeholder="Re-enter your password"
                      value={confirmPassword}
                      onChange={(e) => {
                        setConfirmPassword(e.target.value);
                        if (fieldErrors.confirmPassword) setFieldErrors((prev) => ({ ...prev, confirmPassword: "" }));
                      }}
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      className="auth-input-toggle"
                      onClick={() => setShowConfirmPassword((s) => !s)}
                    >
                      {showConfirmPassword ? "Hide" : "Show"}
                    </button>
                  </div>
                  {fieldErrors.confirmPassword && (
                    <span className="auth-field-error">{fieldErrors.confirmPassword}</span>
                  )}
                </div>

                <div className="auth-field">
                  <label className="auth-checkbox-label">
                    <input
                      type="checkbox"
                      className="auth-checkbox"
                      checked={agreedTerms}
                      onChange={(e) => {
                        setAgreedTerms(e.target.checked);
                        if (fieldErrors.agreedTerms) setFieldErrors((prev) => ({ ...prev, agreedTerms: "" }));
                      }}
                    />
                    <span>
                      I agree to the <a href="#terms" className="auth-link-sm" onClick={(e) => e.preventDefault()}>Terms of Service</a> and <a href="#privacy" className="auth-link-sm" onClick={(e) => e.preventDefault()}>Privacy Policy</a>.
                    </span>
                  </label>
                  {fieldErrors.agreedTerms && (
                    <span className="auth-field-error">{fieldErrors.agreedTerms}</span>
                  )}
                </div>

                <button type="submit" className="auth-submit-btn" disabled={loading}>
                  {loading ? "Creating account…" : "Create account →"}
                </button>

                <div className="auth-divider">
                  <span>or continue with</span>
                </div>

                <div className="auth-oauth-grid">
                  <button
                    type="button"
                    className="auth-oauth-btn"
                    onClick={() => handleOAuth("google")}
                    disabled={oauthLoading !== null}
                  >
                    <svg className="auth-oauth-icon" viewBox="0 0 24 24">
                      <path
                        fill="#EA4335"
                        d="M12 5c1.6 0 3 .6 4.1 1.6l3.1-3.1C17.3 1.7 14.8 1 12 1 7.5 1 3.7 3.6 1.9 7.3l3.7 2.9C6.5 7.4 9 5 12 5z"
                      />
                      <path
                        fill="#4285F4"
                        d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5c-.3 1.5-1.1 2.8-2.4 3.7l3.7 2.9c2.2-2 3.7-5.1 3.7-8.8z"
                      />
                      <path
                        fill="#FBBC05"
                        d="M5.6 14.8c-.2-.7-.4-1.5-.4-2.3 0-.8.2-1.6.4-2.3L1.9 7.3C.7 9.7 0 12.3 0 15s.7 5.3 1.9 7.7l3.7-2.9z"
                      />
                      <path
                        fill="#34A853"
                        d="M12 24c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3 0-5.5-2-6.4-4.8L1.9 17.4C3.7 21.1 7.5 24 12 24z"
                      />
                    </svg>
                    <span>{oauthLoading === "google" ? "Connecting…" : "Google"}</span>
                  </button>

                  <button
                    type="button"
                    className="auth-oauth-btn"
                    onClick={() => handleOAuth("github")}
                    disabled={oauthLoading !== null}
                  >
                    <svg className="auth-oauth-icon" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
                    </svg>
                    <span>{oauthLoading === "github" ? "Connecting…" : "GitHub"}</span>
                  </button>
                </div>

                <div className="auth-switch-prompt">
                  <span>Already have an account?</span>
                  <button
                    type="button"
                    className="auth-switch-btn"
                    onClick={() => {
                      setMode("signin");
                      setError(null);
                      setFieldErrors({});
                    }}
                  >
                    Sign in
                  </button>
                </div>
              </form>
            </>
          )}

          <div className="auth-footer-links">
            <span onClick={() => alert("Privacy policy: KintsuTech protects all organizational telemetry.")}>Privacy</span>
            <span onClick={() => alert("Terms of Service: Resilience workspace terms.")}>Terms</span>
            <span onClick={() => alert("Support: support@kintsu.tech")}>Support</span>
          </div>
        </div>
      </section>
    </div>
  );
}
