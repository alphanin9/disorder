import { FormEvent, useEffect, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  checkCodexAuthHealth,
  deleteCodexAuthFile,
  deleteCodexAuthTag,
  getCodexAuthStatus,
  pollCodexDeviceAuth,
  setCodexAuthActiveTag,
  startCodexDeviceAuth,
  uploadCodexAuthFile,
} from "@/api/endpoints";
import type { CodexDeviceAuthStartResponse } from "@/api/models";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { inputClasses } from "@/components/ui/forms";

export function CodexAuthCard() {
  const queryClient = useQueryClient();
  const [tag, setTag] = useState("default");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [deviceFlow, setDeviceFlow] = useState<CodexDeviceAuthStartResponse | null>(null);

  const statusQuery = useQuery({
    queryKey: ["codex-auth-status"],
    queryFn: getCodexAuthStatus,
    refetchInterval: 5000,
  });

  const uploadMutation = useMutation({
    mutationFn: async (payload: { tag: string; files: File[] }) => {
      for (const file of payload.files) {
        await uploadCodexAuthFile(file, payload.tag);
      }
    },
    onSuccess: () => {
      setSelectedFiles([]);
      void queryClient.invalidateQueries({ queryKey: ["codex-auth-status"] });
    },
  });

  const startDeviceMutation = useMutation({
    mutationFn: startCodexDeviceAuth,
    onSuccess: (flow) => {
      setDeviceFlow(flow);
    },
  });

  const devicePollQuery = useQuery({
    queryKey: ["codex-device-auth", deviceFlow?.flow_id],
    queryFn: () => pollCodexDeviceAuth(deviceFlow?.flow_id ?? ""),
    enabled: Boolean(deviceFlow?.flow_id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!deviceFlow || status === "authorized" || status === "expired") {
        return false;
      }
      return deviceFlow.interval_seconds * 1000;
    },
  });

  const healthCheckMutation = useMutation({
    mutationFn: checkCodexAuthHealth,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["codex-auth-status"] });
    },
  });

  const setActiveMutation = useMutation({
    mutationFn: setCodexAuthActiveTag,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["codex-auth-status"] });
    },
  });

  const deleteFileMutation = useMutation({
    mutationFn: deleteCodexAuthFile,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["codex-auth-status"] });
    },
  });

  const deleteTagMutation = useMutation({
    mutationFn: deleteCodexAuthTag,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["codex-auth-status"] });
    },
  });

  const onUploadSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (selectedFiles.length === 0) {
      return;
    }
    uploadMutation.mutate({ tag, files: selectedFiles });
  };

  useEffect(() => {
    if (devicePollQuery.data?.status === "authorized") {
      setDeviceFlow(null);
      void queryClient.invalidateQueries({ queryKey: ["codex-auth-status"] });
    }
  }, [devicePollQuery.data?.status, queryClient]);

  return (
    <Card>
      <h3 className="mb-3 text-lg font-semibold">Codex Auth</h3>
      <p className="mb-3 text-sm text-ink-muted">Use device sign-in for tagged sandbox Codex runs. Active tag is mounted into each run.</p>

      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="codex_auth_tag">
            Tag
          </label>
          <input
            id="codex_auth_tag"
            className={inputClasses}
            value={tag}
            onChange={(event) => {
              setTag(event.target.value);
            }}
          />
        </div>

        <Button
          type="button"
          className="w-full"
          disabled={startDeviceMutation.isPending}
          onClick={() => {
            startDeviceMutation.mutate(tag);
          }}
        >
          {startDeviceMutation.isPending ? "Starting..." : "Start Device Sign-In"}
        </Button>

        {startDeviceMutation.isError ? <p className="text-sm text-danger">Failed to start Codex device sign-in.</p> : null}

        {deviceFlow ? (
          <div className="rounded-md border border-line bg-surface-muted p-3">
            <p className="text-sm font-semibold">Open device sign-in</p>
            <a className="text-sm font-semibold text-accent hover:underline" href={deviceFlow.verification_uri} target="_blank" rel="noreferrer">
              {deviceFlow.verification_uri}
            </a>
            <div className="mt-3 rounded bg-surface-strong px-3 py-2 text-center font-mono text-2xl font-semibold tracking-wide">
              {deviceFlow.user_code}
            </div>
            <p className="mt-2 text-xs text-ink-muted">Expires {new Date(deviceFlow.expires_at).toLocaleTimeString()}.</p>
            <Button
              type="button"
              className="mt-3 w-full"
              variant="secondary"
              disabled={devicePollQuery.isFetching}
              onClick={() => {
                void devicePollQuery.refetch();
              }}
            >
              {devicePollQuery.isFetching ? "Checking..." : "Check Now"}
            </Button>
            {devicePollQuery.data?.status === "pending" ? (
              <p className="mt-2 text-sm text-ink-muted">Still waiting for authorization.</p>
            ) : null}
            {devicePollQuery.data?.status === "expired" ? <p className="mt-2 text-sm text-danger">Device code expired. Start again.</p> : null}
            {devicePollQuery.isError ? <p className="mt-2 text-sm text-danger">Failed to complete device sign-in.</p> : null}
          </div>
        ) : null}
      </div>

      <form className="mt-5 space-y-3 border-t border-line pt-4" onSubmit={onUploadSubmit}>
        <h4 className="text-sm font-semibold uppercase tracking-wide text-ink-subtle">Manual fallback</h4>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="codex_auth_files">
            Auth files
          </label>
          <input
            id="codex_auth_files"
            type="file"
            multiple
            className={inputClasses}
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              setSelectedFiles(files);
            }}
          />
          <p className="mt-1 text-xs text-ink-muted">Allowlisted filenames only (for example: auth.json, credentials.json, token.json).</p>
        </div>

        {selectedFiles.length > 0 ? (
          <ul className="rounded-md bg-surface-muted px-3 py-2 text-xs text-ink-muted">
            {selectedFiles.map((file) => (
              <li key={file.name}>
                {file.name} ({file.size} bytes)
              </li>
            ))}
          </ul>
        ) : null}

        {uploadMutation.isError ? <p className="text-sm text-danger">Failed to upload auth files.</p> : null}

        <Button type="submit" className="w-full" disabled={uploadMutation.isPending || selectedFiles.length === 0}>
          {uploadMutation.isPending ? "Uploading..." : "Upload Auth Files"}
        </Button>
      </form>

      <div className="mt-5 border-t border-line pt-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h4 className="text-sm font-semibold uppercase tracking-wide text-ink-subtle">Tags</h4>
          <Button
            type="button"
            variant="secondary"
            disabled={healthCheckMutation.isPending || !statusQuery.data?.configured}
            onClick={() => {
              healthCheckMutation.mutate();
            }}
          >
            {healthCheckMutation.isPending ? "Checking..." : "Check Auth"}
          </Button>
        </div>
        {statusQuery.data?.reauth_required ? <p className="mb-2 text-sm text-danger">Codex auth needs to be renewed.</p> : null}
        {statusQuery.data?.limit_status === "exhausted" || statusQuery.data?.limit_status === "rate_limited" ? (
          <p className="mb-2 text-sm text-danger">Codex account limits are currently constrained.</p>
        ) : null}
        {statusQuery.isLoading ? <p>Loading auth status...</p> : null}
        {statusQuery.error ? <p className="text-danger">Failed to load auth status.</p> : null}

        {statusQuery.data && statusQuery.data.tags.length === 0 ? <p className="text-sm text-ink-muted">No auth files uploaded yet.</p> : null}

        <div className="space-y-2">
          {statusQuery.data?.tags.map((tagInfo) => {
            const active = statusQuery.data?.active_tag === tagInfo.tag;
            return (
              <div key={tagInfo.tag} className="rounded-md border border-line bg-surface-muted p-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-semibold">
                      {tagInfo.tag}
                      {active ? <span className="ml-2 text-xs text-success">(active)</span> : null}
                    </p>
                    <p className="text-xs text-ink-muted">
                      {tagInfo.file_count} files
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={active || setActiveMutation.isPending}
                      onClick={() => {
                        setActiveMutation.mutate(tagInfo.tag);
                      }}
                    >
                      Use Tag
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={deleteTagMutation.isPending}
                      onClick={() => {
                        deleteTagMutation.mutate(tagInfo.tag);
                      }}
                    >
                      Delete Tag
                    </Button>
                  </div>
                </div>

                <ul className="space-y-1 text-xs text-ink-muted">
                  {tagInfo.files.map((fileInfo) => (
                    <li key={fileInfo.id} className="flex items-center justify-between gap-2 rounded bg-surface-strong px-2 py-1">
                      <span className="min-w-0">
                        <span className="font-medium">{fileInfo.file_name}</span> ({fileInfo.size_bytes} bytes)
                        {fileInfo.health_status ? <span className="ml-2">health: {fileInfo.health_status}</span> : null}
                        {fileInfo.limit_summary ? <span className="ml-2">limits: {fileInfo.limit_summary}</span> : null}
                        {fileInfo.last_limit_error ? <span className="ml-2 text-danger">limits: {fileInfo.last_limit_error}</span> : null}
                      </span>
                      <button
                        type="button"
                        className="font-semibold text-danger hover:underline"
                        onClick={() => {
                          deleteFileMutation.mutate(fileInfo.id);
                        }}
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}
