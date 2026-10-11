"use client";

import React, { useState, useEffect } from "react";
import { Screen, Project, ChangeRecord, GraphData } from "@/types";
import { Icon, Logo } from "@/components/ui/Icons";
import { Button, Select, Field } from "@/components/ui/Primitives";
import {
  defaultProjects,
  defaultChanges,
  dependencyRows,
  defaultGraphData,
  screenMeta,
} from "@/lib/data";

import { OverviewScreen } from "@/components/screens/OverviewScreen";
import { ProjectsScreen } from "@/components/screens/ProjectsScreen";
import { DependenciesScreen } from "@/components/screens/DependenciesScreen";
import { ChangesScreen } from "@/components/screens/ChangesScreen";
import { ImpactGraphScreen } from "@/components/screens/ImpactGraphScreen";
import { RecoveryStudioScreen } from "@/components/screens/RecoveryStudioScreen";
import { ValidationLabScreen } from "@/components/screens/ValidationLabScreen";
import { HistoryScreen } from "@/components/screens/HistoryScreen";
import { IntegrationsScreen } from "@/components/screens/IntegrationsScreen";
import { SettingsScreen } from "@/components/screens/SettingsScreen";
import { AgentChatScreen } from "@/components/screens/AgentChatScreen";
import { KintsuCopilot } from "@/components/layout/KintsuCopilot";
import { AuthModal } from "@/components/layout/AuthModal";

export function AppShell({
  initialScreen = "projects",
  onNavigateHome,
}: {
  initialScreen?: Screen;
  onNavigateHome?: () => void;
}) {
  const [screen, setScreen] = useState<Screen>(initialScreen);
  const [project, setProject] = useState("Pulse API");
  const [env, setEnv] = useState("Staging");

  const [copilotOpen, setCopilotOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [globalSearch, setGlobalSearch] = useState("");

  const [navDropdown, setNavDropdown] = useState<"investigate" | "repair" | "settings" | null>(null);

  // Core application state
  const [projects, setProjects] = useState<Project[]>(defaultProjects);
  const [dependencies, setDependencies] = useState<string[][]>(dependencyRows);
  const [changes, setChanges] = useState<ChangeRecord[]>(defaultChanges);
  const [graphData, setGraphData] = useState<GraphData>(defaultGraphData);

  const [caseStatus, setCaseStatus] = useState<"review" | "validated" | "approved" | "rejected">("review");
  const [validationState, setValidationState] = useState<"idle" | "running" | "done" | "failed">("idle");

  const [user, setUser] = useState<{ email: string; initials: string; role: string } | null>({
    email: "akira@kintsu.tech",
    initials: "AK",
    role: "Platform Engineer",
  });

  const navigate = (next: Screen) => {
    setScreen(next);
    setNavDropdown(null);
    setSearchOpen(false);
    setNotificationOpen(false);
    setProfileOpen(false);
  };

  const runValidation = (outcome: "success" | "failure" = "success") => {
    setValidationState("running");
    window.setTimeout(() => {
      setValidationState(outcome === "success" ? "done" : "failed");
      setCaseStatus(outcome === "success" ? "validated" : "review");
    }, 1200);
  };

  const resetDemo = () => {
    setProjects(defaultProjects);
    setDependencies(dependencyRows);
    setChanges(defaultChanges);
    setGraphData(defaultGraphData);
    setCaseStatus("review");
    setValidationState("idle");
    setProject("Pulse API");
    setEnv("Staging");
    setScreen("overview");
  };

  return (
    <div className="app-shell">
      {/* Header Level 1: Utility Bar */}
      <header className="app-header">
        <div className="header-primary">
          <div className="brand-cluster">
            <button
              className="flex items-center gap-2 cursor-pointer bg-transparent border-none"
              onClick={onNavigateHome ? onNavigateHome : () => navigate("overview")}
              aria-label="KintsuTech home"
            >
              <Logo />
            </button>

            <div className="workspace-controls">
              <div className="workspace-select">
                <span>Project:</span>
                <select value={project} onChange={(e) => setProject(e.target.value)}>
                  {projects.map((p) => (
                    <option key={p.id} value={p.name}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <Icon name="chevron" size={12} />
              </div>

              <div className="workspace-select">
                <span>Environment:</span>
                <select value={env} onChange={(e) => setEnv(e.target.value)}>
                  <option>Development</option>
                  <option>Staging</option>
                  <option>Production</option>
                </select>
                <Icon name="chevron" size={12} />
              </div>
            </div>
          </div>

          <div className="top-actions">
            {/* Search */}
            <div className="relative">
              <Button
                variant="icon"
                icon="search"
                ariaLabel="Search workspace"
                onClick={() => {
                  setSearchOpen(!searchOpen);
                  setNotificationOpen(false);
                  setProfileOpen(false);
                }}
              />
              {searchOpen && (
                <div className="absolute right-0 top-12 w-80 bg-white border border-stone-200 rounded-md shadow-lg p-2 z-50">
                  <Field
                    value={globalSearch}
                    onChange={setGlobalSearch}
                    placeholder="Search dependencies, incidents…"
                    icon="search"
                  />
                  {globalSearch && (
                    <div className="mt-2 divide-y divide-stone-100 text-xs">
                      <button
                        onClick={() => {
                          navigate("changes");
                          setSearchOpen(false);
                        }}
                        className="w-full p-2 text-left hover:bg-stone-50 block"
                      >
                        <strong>Payment API change</strong>
                        <div className="text-stone-500">CHG-841 · name → display_name</div>
                      </button>
                      <button
                        onClick={() => {
                          navigate("dependencies");
                          setSearchOpen(false);
                        }}
                        className="w-full p-2 text-left hover:bg-stone-50 block"
                      >
                        <strong>Mapbox</strong>
                        <div className="text-stone-500">GET /geocoding/v5</div>
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Notifications */}
            <div className="relative">
              <Button
                variant="icon"
                icon="bell"
                ariaLabel="Notifications"
                onClick={() => {
                  setNotificationOpen(!notificationOpen);
                  setSearchOpen(false);
                  setProfileOpen(false);
                }}
              />
              {notificationOpen && (
                <div className="absolute right-0 top-12 w-72 bg-white border border-stone-200 rounded-md shadow-lg p-3 z-50">
                  <div className="font-bold text-xs text-stone-700 mb-2">Notifications</div>
                  <div className="space-y-2 text-xs">
                    <div className="p-2 bg-stone-50 rounded">
                      <strong>Payment API changed</strong>
                      <div className="text-stone-500">3 workflows affected</div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Chat with AI Agent Entry */}
            <button
              className={`copilot-trigger ${screen === "chat" ? "ring-2 ring-emerald-500" : ""}`}
              onClick={() => navigate("chat")}
              title="Open full AI Agent Chat"
            >
              <Icon name="spark" size={15} />
              <span>Chat with AI Agent</span>
            </button>

            {/* Kintsu Copilot Trigger */}
            <button
              className="copilot-trigger"
              onClick={() => setCopilotOpen(!copilotOpen)}
            >
              <Icon name="spark" size={15} />
              <span>Kintsu Copilot</span>
            </button>

            {/* User Avatar */}
            <div className="relative">
              <button
                className="avatar-badge"
                onClick={() => {
                  setProfileOpen(!profileOpen);
                  setSearchOpen(false);
                  setNotificationOpen(false);
                }}
              >
                {user?.initials || "AK"}
              </button>
              {profileOpen && (
                <div className="absolute right-0 top-12 w-56 bg-white border border-stone-200 rounded-md shadow-lg p-3 z-50 text-xs">
                  <strong>{user?.email || "Akira K."}</strong>
                  <div className="text-stone-500 mb-2">{user?.role || "Platform Engineer"}</div>
                  <hr className="my-2 border-stone-100" />
                  <button
                    onClick={() => {
                      navigate("settings");
                      setProfileOpen(false);
                    }}
                    className="w-full text-left py-1 text-stone-700 hover:text-stone-900"
                  >
                    Platform Settings
                  </button>
                  <button
                    onClick={() => {
                      setAuthOpen(true);
                      setProfileOpen(false);
                    }}
                    className="w-full text-left py-1 text-emerald-700 hover:text-emerald-900 font-semibold"
                  >
                    Account & Auth
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Header Level 2: Horizontal Pine Green Navigation Bar */}
        <nav className="horizontal-nav" aria-label="Workspace navigation">
          <button
            className={screen === "overview" ? "active" : ""}
            onClick={() => navigate("overview")}
          >
            Overview
          </button>
          <button
            className={screen === "projects" ? "active" : ""}
            onClick={() => navigate("projects")}
          >
            Projects
          </button>
          <button
            className={screen === "dependencies" ? "active" : ""}
            onClick={() => navigate("dependencies")}
          >
            Dependencies
          </button>

          {/* Investigate Dropdown */}
          <div className="nav-dropdown">
            <button
              className={screen === "changes" || screen === "graph" ? "active" : ""}
              onClick={() => setNavDropdown(navDropdown === "investigate" ? null : "investigate")}
            >
              Investigate <Icon name="chevron" size={11} />
            </button>
            {navDropdown === "investigate" && (
              <div className="nav-dropdown-menu">
                <button onClick={() => navigate("changes")}>
                  <Icon name="activity" size={16} />
                  <span>
                    <strong>Change Detection</strong>
                    <small>Review observed changes</small>
                  </span>
                </button>
                <button onClick={() => navigate("graph")}>
                  <Icon name="graph" size={16} />
                  <span>
                    <strong>AI Dependency Graph</strong>
                    <small>Trace established impact</small>
                  </span>
                </button>
              </div>
            )}
          </div>

          {/* Repair Dropdown */}
          <div className="nav-dropdown">
            <button
              className={screen === "recovery" || screen === "validation" ? "active" : ""}
              onClick={() => setNavDropdown(navDropdown === "repair" ? null : "repair")}
            >
              Repair <Icon name="chevron" size={11} />
            </button>
            {navDropdown === "repair" && (
              <div className="nav-dropdown-menu">
                <button onClick={() => navigate("recovery")}>
                  <Icon name="recovery" size={16} />
                  <span>
                    <strong>Recovery Studio</strong>
                    <small>Review controlled proposals</small>
                  </span>
                </button>
                <button onClick={() => navigate("validation")}>
                  <Icon name="test" size={16} />
                  <span>
                    <strong>Validation Lab</strong>
                    <small>Run independent checks</small>
                  </span>
                </button>
              </div>
            )}
          </div>

          <button
            className={screen === "history" ? "active" : ""}
            onClick={() => navigate("history")}
          >
            History
          </button>

          <button
            className={screen === "chat" ? "active" : ""}
            onClick={() => navigate("chat")}
          >
            AI Agent Chat
          </button>

          {/* Settings Dropdown */}
          <div className="nav-dropdown">
            <button
              className={screen === "integrations" || screen === "settings" ? "active" : ""}
              onClick={() => setNavDropdown(navDropdown === "settings" ? null : "settings")}
            >
              Settings <Icon name="chevron" size={11} />
            </button>
            {navDropdown === "settings" && (
              <div className="nav-dropdown-menu align-right">
                <button onClick={() => navigate("integrations")}>
                  <Icon name="api" size={16} />
                  <span>
                    <strong>Integrations</strong>
                    <small>Evidence and provider connections</small>
                  </span>
                </button>
                <button onClick={() => navigate("settings")}>
                  <Icon name="settings" size={16} />
                  <span>
                    <strong>Platform Settings</strong>
                    <small>Workspace and safety policy</small>
                  </span>
                </button>
              </div>
            )}
          </div>
        </nav>
      </header>

      {/* Main Screen Body */}
      <main className="screen">
        {screen === "overview" && (
          <OverviewScreen
            navigate={navigate}
            caseStatus={caseStatus}
            validationState={validationState}
            dependencies={dependencies}
            changes={changes}
            graphData={graphData}
            projects={projects}
            currentProject={project}
            currentEnv={env}
          />
        )}
        {screen === "projects" && (
          <ProjectsScreen
            projects={projects}
            setProjects={setProjects}
            setCurrentProject={setProject}
            navigate={navigate}
            dependencies={dependencies}
            setDependencies={setDependencies}
            graphData={graphData}
            setGraphData={setGraphData}
          />
        )}
        {screen === "dependencies" && (
          <DependenciesScreen
            navigate={navigate}
            dependencies={dependencies}
            setDependencies={setDependencies}
            currentProject={project}
            currentEnv={env}
          />
        )}
        {screen === "changes" && (
          <ChangesScreen changes={changes} setChanges={setChanges} navigate={navigate} />
        )}
        {screen === "graph" && (
          <ImpactGraphScreen
            navigate={navigate}
            caseStatus={caseStatus}
            validationState={validationState}
            graphData={graphData}
            setGraphData={setGraphData}
            currentProject={project}
            currentEnv={env}
          />
        )}
        {screen === "recovery" && (
          <RecoveryStudioScreen
            caseStatus={caseStatus}
            setCaseStatus={setCaseStatus}
            validationState={validationState}
            runValidation={runValidation}
            navigate={navigate}
          />
        )}
        {screen === "validation" && (
          <ValidationLabScreen
            validationState={validationState}
            runValidation={runValidation}
            navigate={navigate}
          />
        )}
        {screen === "history" && (
          <HistoryScreen
            caseStatus={caseStatus}
            validationState={validationState}
            navigate={navigate}
          />
        )}
        {screen === "integrations" && (
          <IntegrationsScreen
            navigate={navigate}
            dependencies={dependencies}
            setDependencies={setDependencies}
          />
        )}
        {screen === "chat" && <AgentChatScreen navigate={navigate} />}
        {screen === "settings" && <SettingsScreen resetDemo={resetDemo} />}
      </main>

      {/* Floating Kintsu Copilot Drawer */}
      <KintsuCopilot
        open={copilotOpen}
        close={() => setCopilotOpen(false)}
        context={screenMeta[screen][0]}
        navigate={navigate}
      />

      {/* Supabase Authentication Modal */}
      <AuthModal
        open={authOpen}
        close={() => setAuthOpen(false)}
        onUserChange={setUser}
      />
    </div>
  );
}
