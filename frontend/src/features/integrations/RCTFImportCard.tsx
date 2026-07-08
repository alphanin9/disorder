import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "@/api/client";
import { clearCtfRctfTeamToken, getCtfRctfConfig, syncRctf } from "@/api/endpoints";
import type { RCTFPerCtfConfigResponse, RCTFSyncRequest } from "@/api/models";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { inputClasses } from "@/components/ui/forms";

const rctfSyncSchema = z.object({
  base_url: z.string().trim().min(1, "Base URL is required").url("Base URL must be a valid URL"),
  team_token: z.string().trim().min(1, "Team token is required"),
});

type RCTFSyncValues = z.infer<typeof rctfSyncSchema>;

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function RCTFImportCard() {
  const queryClient = useQueryClient();
  const [lastSyncedCtf, setLastSyncedCtf] = useState<{ id: string; slug: string } | null>(null);
  const [savedConfig, setSavedConfig] = useState<RCTFPerCtfConfigResponse | null>(null);

  const form = useForm<RCTFSyncValues>({
    resolver: zodResolver(rctfSyncSchema),
    defaultValues: {
      base_url: "",
      team_token: "",
    },
  });

  const ctfConfigMutation = useMutation({
    mutationFn: (ctfId: string) => getCtfRctfConfig(ctfId),
    onSuccess: (config) => {
      setSavedConfig(config);
      if (config.base_url) {
        form.setValue("base_url", config.base_url, { shouldValidate: true });
      }
    },
  });

  const clearTokenMutation = useMutation({
    mutationFn: (ctfId: string) => clearCtfRctfTeamToken(ctfId),
    onSuccess: (config) => setSavedConfig(config),
  });

  const syncMutation = useMutation({
    mutationFn: (values: RCTFSyncValues) => {
      const payload: RCTFSyncRequest = {
        base_url: values.base_url.trim(),
        team_token: values.team_token.trim(),
      };
      return syncRctf(payload);
    },
    onSuccess: (data, variables) => {
      form.reset({
        base_url: variables.base_url.trim(),
        team_token: "",
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

  const syncError = syncMutation.error ? getErrorMessage(syncMutation.error, "Failed to sync rCTF challenges.") : null;
  const savedConfigError =
    ctfConfigMutation.error || clearTokenMutation.error
      ? getErrorMessage(ctfConfigMutation.error ?? clearTokenMutation.error, "Failed to load saved rCTF config.")
      : null;

  return (
    <Card>
      <h3 className="mb-3 text-lg font-semibold">Import from rCTF</h3>
      <p className="mb-3 text-sm text-ink-muted">
        Sync challenges from an rCTF instance using your team token. The newer rCTF v2 challenge API is auto-detected (with
        fallback to v1). The token is stored (encrypted) per CTF so the backend can auto-submit flags later.
      </p>

      <form className="space-y-3" onSubmit={onSubmit}>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="rctf_base_url">
            Base URL
          </label>
          <input
            id="rctf_base_url"
            type="url"
            autoComplete="url"
            placeholder="https://rctf.example.com"
            className={inputClasses}
            {...form.register("base_url")}
          />
          {form.formState.errors.base_url ? <p className="mt-1 text-xs text-danger">{form.formState.errors.base_url.message}</p> : null}
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="rctf_team_token">
            Team Token
          </label>
          <input
            id="rctf_team_token"
            type="password"
            autoComplete="off"
            placeholder="rctf team token"
            className={inputClasses}
            {...form.register("team_token")}
          />
          {form.formState.errors.team_token ? <p className="mt-1 text-xs text-danger">{form.formState.errors.team_token.message}</p> : null}
          <p className="mt-1 text-xs text-ink-muted">Find this on your rCTF profile page (the "team token" used for API/CLI login).</p>
        </div>

        <div className="flex gap-2">
          <Button type="submit" className="flex-1" disabled={syncMutation.isPending}>
            {syncMutation.isPending ? "Syncing..." : "Sync from rCTF"}
          </Button>
        </div>
      </form>

      {syncError ? <p className="mt-3 text-sm text-danger">{syncError}</p> : null}
      {syncMutation.data ? (
        <p className="mt-3 text-sm text-success">
          Synced {syncMutation.data.synced} challenges from {syncMutation.data.platform}
          {syncMutation.data.api_version ? ` (API ${syncMutation.data.api_version})` : ""}.
        </p>
      ) : null}

      {savedConfigError ? <p className="mt-2 text-xs text-danger">{savedConfigError}</p> : null}
      {lastSyncedCtf && savedConfig ? (
        <div className="mt-3 rounded-md border border-line bg-surface-muted p-3 text-xs text-ink-muted">
          <p className="font-medium">Saved rCTF Auth ({lastSyncedCtf.slug})</p>
          <p className="mt-1">
            base URL: <code>{savedConfig.base_url || "(none)"}</code>
          </p>
          {savedConfig.api_version ? <p>challenge API: <code>{savedConfig.api_version}</code></p> : null}
          <p>stored: {savedConfig.has_team_token ? "team token" : "(none)"}</p>
          <div className="mt-2 flex gap-2">
            <Button
              type="button"
              variant="ghost"
              disabled={!savedConfig.has_team_token || clearTokenMutation.isPending}
              onClick={() => {
                if (!lastSyncedCtf) return;
                clearTokenMutation.mutate(lastSyncedCtf.id);
              }}
            >
              {clearTokenMutation.isPending ? "Clearing..." : "Clear Team Token"}
            </Button>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
