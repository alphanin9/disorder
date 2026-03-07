import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "@/api/client";
import { clearCtfCtfdApiToken, clearCtfCtfdSessionCookie, getCtfCtfdConfig, syncCtfd } from "@/api/endpoints";
import type { CTFdPerCtfConfigResponse, CTFdSyncRequest } from "@/api/models";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { inputClasses } from "@/components/ui/forms";

const ctfdSyncSchema = z
  .object({
    base_url: z.string().trim().min(1, "Base URL is required").url("Base URL must be a valid URL"),
    auth_mode: z.enum(["session_cookie", "api_token"]),
    api_token: z.string().default(""),
    session_cookie: z.string().default(""),
  })
  .superRefine((values, ctx) => {
    if (values.auth_mode === "session_cookie" && values.session_cookie.trim().length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["session_cookie"],
        message: "Session cookie is required",
      });
    }
    if (values.auth_mode === "api_token" && values.api_token.trim().length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["api_token"],
        message: "API token is required",
      });
    }
  });

type CTFdSyncValues = z.infer<typeof ctfdSyncSchema>;

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function CTFdImportCard() {
  const queryClient = useQueryClient();
  const [lastSyncedCtf, setLastSyncedCtf] = useState<{ id: string; slug: string } | null>(null);
  const [savedConfig, setSavedConfig] = useState<CTFdPerCtfConfigResponse | null>(null);

  const form = useForm<CTFdSyncValues>({
    resolver: zodResolver(ctfdSyncSchema),
    defaultValues: {
      base_url: "",
      auth_mode: "session_cookie",
      api_token: "",
      session_cookie: "",
    },
  });

  const ctfConfigMutation = useMutation({
    mutationFn: (ctfId: string) => getCtfCtfdConfig(ctfId),
    onSuccess: (config) => {
      setSavedConfig(config);
      if (config.base_url) {
        form.setValue("base_url", config.base_url, { shouldValidate: true });
      }
    },
  });

  const clearSessionMutation = useMutation({
    mutationFn: (ctfId: string) => clearCtfCtfdSessionCookie(ctfId),
    onSuccess: (config) => setSavedConfig(config),
  });

  const clearTokenMutation = useMutation({
    mutationFn: (ctfId: string) => clearCtfCtfdApiToken(ctfId),
    onSuccess: (config) => setSavedConfig(config),
  });

  const syncMutation = useMutation({
    mutationFn: (values: CTFdSyncValues) => {
      const payload: CTFdSyncRequest = {
        base_url: values.base_url.trim(),
        auth_mode: values.auth_mode,
        api_token: values.auth_mode === "api_token" ? values.api_token.trim() : null,
        session_cookie: values.auth_mode === "session_cookie" ? values.session_cookie.trim() : null,
      };
      return syncCtfd(payload);
    },
    onSuccess: (data, variables) => {
      form.reset({
        base_url: variables.base_url.trim(),
        auth_mode: variables.auth_mode,
        api_token: "",
        session_cookie: "",
      });
      setLastSyncedCtf({ id: data.ctf_id, slug: data.ctf_slug });
      setSavedConfig(null);
      ctfConfigMutation.mutate(data.ctf_id);
      void queryClient.invalidateQueries({ queryKey: ["ctfs"] });
      void queryClient.invalidateQueries({ queryKey: ["challenges"] });
    },
  });

  const onSubmit = form.handleSubmit((values) => {
    syncMutation.mutate(values);
  });

  const syncError = syncMutation.error ? getErrorMessage(syncMutation.error, "Failed to sync CTFd challenges.") : null;
  const savedConfigError =
    ctfConfigMutation.error || clearSessionMutation.error || clearTokenMutation.error
      ? getErrorMessage(ctfConfigMutation.error ?? clearSessionMutation.error ?? clearTokenMutation.error, "Failed to load saved CTFd config.")
      : null;
  const authMode = form.watch("auth_mode");

  return (
    <Card>
      <h3 className="mb-3 text-lg font-semibold">Import from CTFd</h3>
      <p className="mb-3 text-sm text-ink-muted">
        Sync challenges from a CTFd instance. Session cookie mode is default and can be saved (encrypted) for future backend auto-submit.
      </p>

      <form className="space-y-3" onSubmit={onSubmit}>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="ctfd_auth_mode">
            Auth Mode
          </label>
          <select id="ctfd_auth_mode" className={inputClasses} {...form.register("auth_mode")}>
            <option value="session_cookie">Session Cookie (one-time, default)</option>
            <option value="api_token">API Token</option>
          </select>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="ctfd_base_url">
            Base URL
          </label>
          <input
            id="ctfd_base_url"
            type="url"
            autoComplete="url"
            placeholder="https://ctfd.example.com"
            className={inputClasses}
            {...form.register("base_url")}
          />
          {form.formState.errors.base_url ? <p className="mt-1 text-xs text-danger">{form.formState.errors.base_url.message}</p> : null}
        </div>

        {authMode === "session_cookie" ? (
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="ctfd_session_cookie">
              Session Cookie
            </label>
            <input
              id="ctfd_session_cookie"
              type="password"
              autoComplete="off"
              placeholder="session=..."
              className={inputClasses}
              {...form.register("session_cookie")}
            />
            {form.formState.errors.session_cookie ? <p className="mt-1 text-xs text-danger">{form.formState.errors.session_cookie.message}</p> : null}
            <p className="mt-1 text-xs text-ink-muted">Stored encrypted per CTF so backend auto-submit can use it later. Session cookies may expire and need rotation.</p>
          </div>
        ) : (
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="ctfd_api_token">
              API Token
            </label>
            <input
              id="ctfd_api_token"
              type="password"
              autoComplete="off"
              className={inputClasses}
              {...form.register("api_token")}
            />
            {form.formState.errors.api_token ? <p className="mt-1 text-xs text-danger">{form.formState.errors.api_token.message}</p> : null}
          </div>
        )}

        <div className="flex gap-2">
          <Button type="submit" className="flex-1" disabled={syncMutation.isPending}>
            {syncMutation.isPending ? "Syncing..." : "Sync from CTFd"}
          </Button>
        </div>
      </form>

      {syncError ? <p className="mt-3 text-sm text-danger">{syncError}</p> : null}
      {syncMutation.data ? (
        <p className="mt-3 text-sm text-success">
          Synced {syncMutation.data.synced} challenges from {syncMutation.data.platform}.
        </p>
      ) : null}
      {syncMutation.data ? (
        <div className="mt-2 rounded-md border border-line bg-surface-muted p-2 text-xs text-ink-muted">
          <p>
            Saved auth modes for <code>{syncMutation.data.ctf_slug}</code>:{" "}
            {syncMutation.data.stored_auth_modes.length > 0 ? syncMutation.data.stored_auth_modes.join(", ") : "(none)"}
          </p>
          <Button
            type="button"
            variant="secondary"
            className="mt-2"
            disabled={ctfConfigMutation.isPending}
            onClick={() => {
              setLastSyncedCtf({ id: syncMutation.data.ctf_id, slug: syncMutation.data.ctf_slug });
              ctfConfigMutation.mutate(syncMutation.data.ctf_id);
            }}
          >
            {ctfConfigMutation.isPending ? "Refreshing..." : "Refresh Saved Auth State"}
          </Button>
        </div>
      ) : null}

      {savedConfigError ? <p className="mt-2 text-xs text-danger">{savedConfigError}</p> : null}
      {lastSyncedCtf && savedConfig ? (
        <div className="mt-3 rounded-md border border-line bg-surface-muted p-3 text-xs text-ink-muted">
          <p className="font-medium">Saved CTFd Auth ({lastSyncedCtf.slug})</p>
          <p className="mt-1">
            base URL: <code>{savedConfig.base_url || "(none)"}</code>
          </p>
          <p>
            preferred auth: <code>{savedConfig.preferred_auth_mode ?? "(none)"}</code>
          </p>
          <p>
            stored: {savedConfig.has_session_cookie ? "session cookie" : ""}{savedConfig.has_session_cookie && savedConfig.has_api_token ? " + " : ""}{savedConfig.has_api_token ? "api token" : ""}{!savedConfig.has_session_cookie && !savedConfig.has_api_token ? "(none)" : ""}
          </p>
          <div className="mt-2 flex gap-2">
            <Button
              type="button"
              variant="ghost"
              disabled={!savedConfig.has_session_cookie || clearSessionMutation.isPending}
              onClick={() => {
                if (!lastSyncedCtf) return;
                clearSessionMutation.mutate(lastSyncedCtf.id);
              }}
            >
              {clearSessionMutation.isPending ? "Clearing..." : "Clear Session Cookie"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={!savedConfig.has_api_token || clearTokenMutation.isPending}
              onClick={() => {
                if (!lastSyncedCtf) return;
                clearTokenMutation.mutate(lastSyncedCtf.id);
              }}
            >
              {clearTokenMutation.isPending ? "Clearing..." : "Clear API Token"}
            </Button>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
