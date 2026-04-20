"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import {
  confirmTotpEnrollment,
  regenerateTotpRecoveryCodes,
  startTotpEnrollment,
  type TotpEnrollmentStartResponse,
  useTotpStatus,
} from "@/lib/api";

export function UserSecurityPanel() {
  const {
    data: totpStatus,
    mutate: mutateTotpStatus,
    isLoading: isTotpStatusLoading,
  } = useTotpStatus();
  const [enrollment, setEnrollment] = useState<TotpEnrollmentStartResponse | null>(null);
  const [verificationCode, setVerificationCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [securityError, setSecurityError] = useState("");
  const [securityNotice, setSecurityNotice] = useState("");
  const [securityBusy, setSecurityBusy] = useState(false);

  useEffect(() => {
    if (totpStatus?.totp_enabled) {
      setEnrollment(null);
      setVerificationCode("");
    }
  }, [totpStatus?.totp_enabled]);

  useEffect(() => {
    if (!totpStatus?.totp_enabled) {
      setRecoveryCodes([]);
    }
  }, [totpStatus?.totp_enabled]);

  const securityStatus = useMemo(() => {
    if (isTotpStatusLoading) {
      return { value: "pending", label: "Loading" };
    }
    if (totpStatus?.totp_enabled) {
      return { value: "pass", label: "Enabled" };
    }
    if (totpStatus?.enrollment_pending) {
      return { value: "warn", label: "Pending Setup" };
    }
    return { value: "fail", label: "Disabled" };
  }, [isTotpStatusLoading, totpStatus?.enrollment_pending, totpStatus?.totp_enabled]);

  async function handleStartTotpEnrollment() {
    setSecurityError("");
    setSecurityNotice("");
    setSecurityBusy(true);
    try {
      const started = await startTotpEnrollment();
      setEnrollment(started);
      setRecoveryCodes([]);
      setVerificationCode("");
      await mutateTotpStatus();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to start TOTP enrollment.";
      setSecurityError(message);
    } finally {
      setSecurityBusy(false);
    }
  }

  async function handleConfirmTotpEnrollment() {
    if (!verificationCode.trim()) {
      setSecurityError("Verification code is required.");
      return;
    }
    setSecurityError("");
    setSecurityNotice("");
    setSecurityBusy(true);
    try {
      const confirmed = await confirmTotpEnrollment({ code: verificationCode.trim() });
      setEnrollment(null);
      setRecoveryCodes(confirmed.recovery_codes ?? []);
      setVerificationCode("");
      await mutateTotpStatus();
      setSecurityNotice(
        "TOTP is now enabled. Store your recovery codes in a secure location."
      );
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to confirm TOTP enrollment.";
      setSecurityError(message);
    } finally {
      setSecurityBusy(false);
    }
  }

  async function handleRegenerateRecoveryCodes() {
    setSecurityError("");
    setSecurityNotice("");
    setSecurityBusy(true);
    try {
      const regenerated = await regenerateTotpRecoveryCodes();
      setRecoveryCodes(regenerated.recovery_codes);
      await mutateTotpStatus();
      setSecurityNotice(
        "Recovery codes regenerated. Any previously unused codes are now invalid."
      );
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to regenerate recovery codes.";
      setSecurityError(message);
    } finally {
      setSecurityBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Account Security</h2>
          <p className="mt-1 text-xs text-text-secondary">
            Configure two-factor authentication (TOTP) for your user account.
          </p>
        </div>
      </CardHeader>
      <CardBody className="space-y-4">
        <div className="rounded-md border border-border bg-bg-elevated px-3 py-2">
          <p className="text-xs text-text-secondary">TOTP Status</p>
          <div className="mt-1">
            <StatusBadge value={securityStatus.value} label={securityStatus.label} />
          </div>
        </div>

        {totpStatus?.totp_enabled && (
          <div className="rounded-md border border-border bg-bg-elevated px-3 py-2">
            <p className="text-xs text-text-secondary">Recovery Codes Remaining</p>
            <p className="mt-1 font-mono text-sm text-text-primary">
              {totpStatus.recovery_codes_remaining}
            </p>
          </div>
        )}

        {!totpStatus?.totp_enabled && !enrollment && (
          <Button
            type="button"
            onClick={handleStartTotpEnrollment}
            disabled={securityBusy}
          >
            {securityBusy ? "Starting…" : "Start TOTP Enrollment"}
          </Button>
        )}

        {!totpStatus?.totp_enabled && enrollment && (
          <div className="space-y-3 rounded-md border border-border bg-bg-elevated p-3">
            <p className="text-xs text-text-secondary">
              Add this secret in your authenticator app, then enter the 6-digit code.
            </p>
            <div className="space-y-1">
              <p className="text-xs text-text-secondary">Scan QR Code</p>
              <div className="inline-flex rounded-md border border-border bg-white p-2">
                <Image
                  src={enrollment.otpauth_qr_data_url}
                  alt="TOTP enrollment QR code"
                  width={176}
                  height={176}
                  className="h-44 w-44 bg-white"
                  unoptimized
                />
              </div>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-text-secondary">Secret</p>
              <code className="block rounded bg-bg-base px-2 py-1 font-mono text-xs text-text-primary">
                {enrollment.secret}
              </code>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-text-secondary">OTPAuth URI</p>
              <code className="block overflow-x-auto rounded bg-bg-base px-2 py-1 font-mono text-xs text-text-primary">
                {enrollment.otpauth_uri}
              </code>
            </div>
            <label className="block space-y-1">
              <span className="text-xs text-text-secondary">Verification Code</span>
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={verificationCode}
                onChange={(e) => setVerificationCode(e.target.value)}
                className="h-10 w-full rounded-md border border-border bg-bg-base px-3 text-sm text-text-primary outline-none focus:border-border-focus focus:ring-2 focus:ring-border-focus/40"
                placeholder="123456"
              />
            </label>
            <div className="flex gap-2">
              <Button
                type="button"
                onClick={handleConfirmTotpEnrollment}
                disabled={securityBusy}
              >
                {securityBusy ? "Verifying…" : "Verify and Enable"}
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setEnrollment(null);
                  setVerificationCode("");
                  setSecurityError("");
                  setSecurityNotice("");
                }}
                disabled={securityBusy}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        {totpStatus?.totp_enabled && (
          <div className="flex gap-2">
            <Button
              type="button"
              onClick={handleRegenerateRecoveryCodes}
              disabled={securityBusy}
            >
              {securityBusy ? "Generating…" : "Regenerate Recovery Codes"}
            </Button>
          </div>
        )}

        {recoveryCodes.length > 0 && (
          <div className="space-y-2 rounded-md border border-border bg-bg-elevated p-3">
            <p className="text-xs text-text-secondary">
              Recovery codes are shown once. Save them in your password manager.
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {recoveryCodes.map((code) => (
                <code
                  key={code}
                  className="rounded bg-bg-base px-2 py-1 font-mono text-xs text-text-primary"
                >
                  {code}
                </code>
              ))}
            </div>
          </div>
        )}

        {securityNotice && <p className="text-xs text-pass">{securityNotice}</p>}
        {securityError && <p className="text-xs text-fail">{securityError}</p>}
      </CardBody>
    </Card>
  );
}
