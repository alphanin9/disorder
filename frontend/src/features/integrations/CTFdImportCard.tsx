import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "@/api/client";
import { getCtfdConfig, syncCtfd } from "@/api/endpoints";
import type { CTFdSyncRequest } from "@/api/models";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

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
  const [configHint, setConfigHint] = useState<"idle" | "loaded" | "missing">("idle");

  const form = useForm<CTFdSyncValues>({
    resolver: zodResolver(ctfdSyncSchema),
    defaultValues: {
      base_url: "",
      auth_mode: "session_cookie",
      api_token: "",
      session_cookie: "",
    },
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
    onSuccess: (_data, variables) => {
      form.reset({
        base_url: variables.base_url.trim(),
        auth_mode: variables.auth_mode,
        api_token: "",
        session_cookie: "",
      });
      setConfigHint("idle");
      void queryClient.invalidateQueries({ queryKey: ["ctfs"] });
      void queryClient.invalidateQueries({ queryKey: ["challenges"] });
    },
  });

  const loadConfigMutation = useMutation({
    mutationFn: getCtfdConfig,
    onSuccess: (config) => {
      if (config.configured && config.base_url) {
        form.setValue("base_url", config.base_url, { shouldDirty: true, shouldValidate: true });
        setConfigHint("loaded");
        return;
      }
      setConfigHint("missing");
    },
  });

  const onSubmit = form.handleSubmit((values) => {
    syncMutation.mutate(values);
  });

  const syncError = syncMutation.error ? getErrorMessage(syncMutation.error, "Failed to sync CTFd challenges.") : null;
  const loadConfigError = loadConfigMutation.error ? getErrorMessage(loadConfigMutation.error, "Failed to load saved CTFd config.") : null;
  const authMode = form.watch("auth_mode");

  return (
    <Card>
      <h3 className="mb-3 text-lg font-semibold">Import from CTFd</h3>
      <p className="mb-3 text-sm text-slate-600">
        Sync challenges from a CTFd instance. Session cookie mode is default and is used for one-time import only.
      </p>

      <form className="space-y-3" onSubmit={onSubmit}>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="ctfd_auth_mode">
            Auth Mode
          </label>
          <select id="ctfd_auth_mode" className="w-full rounded-md border border-slate-300 px-3 py-2" {...form.register("auth_mode")}>
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
            className="w-full rounded-md border border-slate-300 px-3 py-2"
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
              className="w-full rounded-md border border-slate-300 px-3 py-2"
              {...form.register("session_cookie")}
            />
            {form.formState.errors.session_cookie ? <p className="mt-1 text-xs text-danger">{form.formState.errors.session_cookie.message}</p> : null}
            <p className="mt-1 text-xs text-slate-600">Used only for this sync request and never persisted by the harness.</p>
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
              className="w-full rounded-md border border-slate-300 px-3 py-2"
              {...form.register("api_token")}
            />
            {form.formState.errors.api_token ? <p className="mt-1 text-xs text-danger">{form.formState.errors.api_token.message}</p> : null}
          </div>
        )}

        <div className="flex gap-2">
          <Button type="submit" className="flex-1" disabled={syncMutation.isPending}>
            {syncMutation.isPending ? "Syncing..." : "Sync from CTFd"}
          </Button>
          <Button type="button" variant="secondary" disabled={loadConfigMutation.isPending} onClick={() => loadConfigMutation.mutate()}>
            {loadConfigMutation.isPending ? "Loading..." : "Load Saved Base URL"}
          </Button>
        </div>
      </form>

      {syncError ? <p className="mt-3 text-sm text-danger">{syncError}</p> : null}
      {syncMutation.data ? (
        <p className="mt-3 text-sm text-success">
          Synced {syncMutation.data.synced} challenges from {syncMutation.data.platform}.
        </p>
      ) : null}

      {loadConfigError ? <p className="mt-2 text-xs text-danger">{loadConfigError}</p> : null}
      {!loadConfigError && configHint === "loaded" ? <p className="mt-2 text-xs text-success">Loaded saved base URL.</p> : null}
      {!loadConfigError && configHint === "missing" ? <p className="mt-2 text-xs text-warning">No saved CTFd config found.</p> : null}
    </Card>
  );
}
