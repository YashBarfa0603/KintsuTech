import React, { ReactNode } from "react";
import { Icon } from "./Icons";
import { IconName } from "@/types";

export function Button({
  children,
  variant = "primary",
  icon,
  onClick,
  disabled,
  type = "button",
  className = "",
  ariaLabel,
}: {
  children?: ReactNode;
  variant?: "primary" | "secondary" | "ghost" | "danger" | "icon";
  icon?: IconName;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <button
      type={type}
      className={`btn btn-${variant} ${className}`}
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
    >
      {icon && <Icon name={icon} />}
      {children}
    </button>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "gold";
}) {
  return (
    <span className={`badge badge-${tone}`}>
      <span className="status-dot" />
      {children}
    </span>
  );
}

export function Field({
  value,
  onChange,
  placeholder,
  icon,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  icon?: IconName;
}) {
  return (
    <label className="field">
      {icon && <Icon name={icon} size={15} />}
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </label>
  );
}

export function Select({
  value,
  onChange,
  children,
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  children: ReactNode;
  label?: string;
}) {
  return (
    <label className="select-wrap">
      {label && <span className="text-xs text-slate-500 font-medium mr-1">{label}</span>}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {children}
      </select>
      <Icon name="chevron" size={13} />
    </label>
  );
}
