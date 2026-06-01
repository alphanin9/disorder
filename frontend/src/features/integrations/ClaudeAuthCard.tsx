import { FormEvent, useEffect, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  checkClaudeAuthHealth,
  completeClaudeOAuth,
  deleteClaudeAuthFile,
  deleteClaudeAuthTag,
  getClaudeAuthStatus,
  setClaudeAuthActiveTag,
  startClaudeOAuth,
} from "@/api/endpoints";
import type { ClaudeOAuthStartResponse } from "@/api/models";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { inputClasses } from "@/components/ui/forms";

export function ClaudeAuthCard() {
  const queryClient = useQueryClient();
  const [tag, setTag] = useState("default");
  const [oauthFlow, setOauthFlow] = useState<ClaudeOAuthStartResponse | null>(null);
  const [pastedCode, setPastedCode] = useState("");
  const [completeError, setCompleteError] = useState<string | null>(null);

  const statusQuery = useQuery({
    queryKey: ["claude-auth-status"],
    queryFn: getClaudeAuthStatus,
    refetchInterval: 5000,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["claude-auth-status"] });
  };

  const startOAuthMutation = useMutation({
    mutationFn: startClaudeOAuth,
    onSuccess: (flow) => {
      setOauthFlow(flow);
      setPastedCode("");
      setCompleteError(null);
    },
  });

  const completeOAuthMutation = useMutation({
    mutationFn: (payload: { flowId: string; code: string }) =>
      completeClaudeOAuth(payload.flowId, payload.code),
    onSuccess: (result) => {
      if (result.status === "authorized") {
        setOauthFlow(null);
        setPastedCode("");
        setCompleteError(null);
        invalidate();
      } else {
        setCompleteError(result.message ?? "Sign-in could not be completed.");
      }
    },
    onError: () => {
      setCompleteError("Failed to exchange the authorization code. Check the code and try again.");
    },
  });

  const healthCheckMutation = useMutation({
    mutationFn: checkClaudeAuthHealth,
    onSuccess: invalidate,
  });

  const setActiveMutation = useMutation({
    mutationFn: setClaudeAuthActiveTag,
    onSuccess: invalidate,
  });

  const deleteFileMutation = useMutation({
    mutationFn: deleteClaudeAuthFile,
    onSuccess: invalidate,
  });

  const deleteTagMutation = useMutation({
    mutationFn: deleteClaudeAuthTag,
    onSuccess: invalidate,
  });

  useEffect(() => {
    // Drop a stale flow once its window passes so the UI nudges a restart.
    if (!oauthFlow) {
      return;
    }
    const expiry = new Date(oauthFlow.expires_at).getTime();
    const remaining = expiry - Date.now();
    if (remaining <= 0) {
      setCompleteError("Sign-in window expired. Start again.");
      setOauthFlow(null);
      return;
    }
    const timer = setTimeout(() => {
      setCompleteError("Sign-in window expired. Start again.");
      setOauthFlow(null);
    }, remaining);
    return () => {
      clearTimeout(timer);
    };
  }, [oauthFlow]);

  const onCompleteSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!oauthFlow || !pastedCode.trim()) {
      return;
    }
    completeOAuthMutation.mutate({ flowId: oauthFlow.flow_id, code: pastedCode.trim() });
  };

  return (
    <Card>
      <h3 className="mb-3 text-lg font-semibold">Claude Code Auth</h3>
      <p className="mb-3 text-sm text-ink-muted">
        Sign in with Anthropic OAuth for tagged sandbox Claude Code runs. The active tag&apos;s credentials are seeded into each run&apos;s <code>~/.claude</code>.
      </p>

      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="claude_auth_tag">
            Tag
          </label>
          <input
            id="claude_auth_tag"
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
          disabled={startOAuthMutation.isPending}
          onClick={() => {
            startOAuthMutation.mutate(tag);
          }}
        >
          {startOAuthMutation.isPending ? "Starting..." : "Start Sign-In"}
        </Button>

        {startOAuthMutation.isError ? <p className="text-sm text-danger">Failed to start Claude sign-in.</p> : null}

        {oauthFlow ? (
          <div className="rounded-md border border-line bg-surface-muted p-3">
            <p className="text-sm font-semibold">1. Open the Anthropic login page</p>
            <a className="break-all text-sm font-semibold text-accent hover:underline" href={oauthFlow.authorize_url} target="_blank" rel="noreferrer">
              {oauthFlow.authorize_url}
            </a>
            <p className="mt-3 text-sm font-semibold">2. Paste the authorization code</p>
            <p className="text-xs text-ink-muted">After approving, Anthropic shows a code like <code>abc123#state</code>. Paste it whole.</p>
            <form className="mt-2 space-y-2" onSubmit={onCompleteSubmit}>
              <input
                className={inputClasses}
                placeholder="authorization code"
                value={pastedCode}
                onChange={(event) => {
                  setPastedCode(event.target.value);
                }}
              />
              <Button type="submit" className="w-full" disabled={completeOAuthMutation.isPending || !pastedCode.trim()}>
                {completeOAuthMutation.isPending ? "Completing..." : "Complete Sign-In"}
              </Button>
            </form>
            <p className="mt-2 text-xs text-ink-muted">Expires {new Date(oauthFlow.expires_at).toLocaleTimeString()}.</p>
            {completeError ? <p className="mt-2 text-sm text-danger">{completeError}</p> : null}
          </div>
        ) : null}
      </div>

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
        {statusQuery.data?.reauth_required ? <p className="mb-2 text-sm text-danger">Claude auth needs to be renewed.</p> : null}
        {statusQuery.isLoading ? <p>Loading auth status...</p> : null}
        {statusQuery.error ? <p className="text-danger">Failed to load auth status.</p> : null}

        {statusQuery.data && statusQuery.data.tags.length === 0 ? <p className="text-sm text-ink-muted">No credentials stored yet.</p> : null}

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
                    <p className="text-xs text-ink-muted">{tagInfo.file_count} credential(s)</p>
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

                <ul className="space-y-2 text-xs text-ink-muted">
                  {tagInfo.files.map((fileInfo) => (
                    <li key={fileInfo.id} className="rounded bg-surface-strong px-2 py-1.5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="min-w-0">
                          <span className="font-medium">{fileInfo.file_name}</span>
                          {fileInfo.health_status ? <span className="ml-2">health: {fileInfo.health_status}</span> : null}
                          {fileInfo.expires_at ? <span className="ml-2">expires {new Date(fileInfo.expires_at).toLocaleString()}</span> : null}
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
                      </div>
                      {fileInfo.last_health_error ? <p className="mt-2 text-danger">Error: {fileInfo.last_health_error}</p> : null}
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
