"use client";

import React, { useState } from "react";
import { Button, Badge, Select } from "@/components/ui/Primitives";
import { Icon } from "@/components/ui/Icons";

export function SettingsScreen({ resetDemo }: { resetDemo: () => void }) {
  const [section, setSection] = useState("General & projects");
  const [saved, setSaved] = useState(false);

  const sections = [
    "General & projects",
    "Monitoring policy",
    "Access & permissions",
    "Recovery safety",
    "Data & AI",
    "Notifications",
  ];

  return (
    <>
      <div className="page-header">
        <div className="page-heading-wrap">
          <div>
            <div className="breadcrumbs">
              <span>PULSE API</span>
              <Icon name="chevron" size={10} />
              <span>STAGING</span>
              <Icon name="chevron" size={10} />
              <span>SETTINGS</span>
            </div>
            <h1>Workspace Settings</h1>
            <p>Manage environments, policies, and team access.</p>
          </div>
        </div>
        <div className="page-actions">
          {saved && <Badge tone="success">Saved to session</Badge>}
        </div>
      </div>

      <div className="grid grid-cols-4 gap-6">
        <aside className="panel p-2 flex flex-col gap-1">
          {sections.map((s) => (
            <button
              key={s}
              onClick={() => setSection(s)}
              className={`p-2.5 rounded text-left text-xs font-semibold flex items-center justify-between ${
                section === s ? "bg-stone-900 text-white" : "text-stone-700 hover:bg-stone-100"
              }`}
            >
              <span>{s}</span>
              <Icon name="chevron" size={12} />
            </button>
          ))}
        </aside>

        <section className="col-span-3 panel p-6">
          <h2 className="text-lg font-bold text-stone-900 mb-1">{section}</h2>
          <p className="text-xs text-stone-500 mb-6">
            Configure {section.toLowerCase()} for the protected workspace.
          </p>

          <div className="space-y-4">
            <div className="p-4 bg-stone-50 rounded border border-stone-200 flex items-center justify-between">
              <div>
                <strong className="text-sm text-stone-900">Protected Environment</strong>
                <p className="text-xs text-stone-500">Staging API environment with verified JWT checks</p>
              </div>
              <Badge tone="success">Active</Badge>
            </div>

            <div className="p-4 bg-stone-50 rounded border border-stone-200 flex items-center justify-between">
              <div>
                <strong className="text-sm text-stone-900">Human Approval Gate</strong>
                <p className="text-xs text-stone-500">Require an authorized platform engineer before repair activation</p>
              </div>
              <Badge tone="gold">Enforced</Badge>
            </div>

            <div className="p-4 bg-stone-50 rounded border border-stone-200 flex items-center justify-between">
              <div>
                <strong className="text-sm text-stone-900">Telemetry & Baseline Retention</strong>
                <p className="text-xs text-stone-500">Historical observed contract diffs and validation logs</p>
              </div>
              <span className="text-xs font-semibold text-stone-600">30 days</span>
            </div>
          </div>

          <div className="mt-8 pt-4 border-t border-stone-200 flex items-center justify-between">
            <Button variant="danger" onClick={resetDemo}>
              Reset Demo State
            </Button>
            <Button
              onClick={() => {
                setSaved(true);
                window.setTimeout(() => setSaved(false), 2500);
              }}
            >
              Save changes
            </Button>
          </div>
        </section>
      </div>
    </>
  );
}
