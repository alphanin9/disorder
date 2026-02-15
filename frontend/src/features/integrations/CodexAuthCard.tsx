import { FormEvent, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deleteCodexAuthFile,
  deleteCodexAuthTag,
  getCodexAuthStatus,
  setCodexAuthActiveTag,
  uploadCodexAuthFile,
} from "@/api/endpoints";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export function CodexAuthCard() {
  const queryClient = useQueryClient();
  const [tag, setTag] = useState("default");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);

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

  return (
    <Card>
      <h3 className="mb-3 text-lg font-semibold">Codex Auth Files</h3>
      <p className="mb-3 text-sm text-slate-600">Upload tagged auth files. Active tag is used for sandbox Codex runs.</p>

      <form className="space-y-3" onSubmit={onUploadSubmit}>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="codex_auth_tag">
            Tag
          </label>
          <input
            id="codex_auth_tag"
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            value={tag}
            onChange={(event) => {
              setTag(event.target.value);
            }}
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="codex_auth_files">
            Auth files
          </label>
          <input
            id="codex_auth_files"
            type="file"
            multiple
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              setSelectedFiles(files);
            }}
          />
          <p className="mt-1 text-xs text-slate-600">Allowlisted filenames only (for example: auth.json, credentials.json, token.json).</p>
        </div>

        {selectedFiles.length > 0 ? (
          <ul className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-700">
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

      <div className="mt-5 border-t border-slate-200 pt-4">
        <h4 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Tags</h4>
        {statusQuery.isLoading ? <p>Loading auth status...</p> : null}
        {statusQuery.error ? <p className="text-danger">Failed to load auth status.</p> : null}

        {statusQuery.data && statusQuery.data.tags.length === 0 ? <p className="text-sm text-slate-600">No auth files uploaded yet.</p> : null}

        <div className="space-y-2">
          {statusQuery.data?.tags.map((tagInfo) => {
            const active = statusQuery.data?.active_tag === tagInfo.tag;
            return (
              <div key={tagInfo.tag} className="rounded-md border border-slate-200 p-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-semibold">
                      {tagInfo.tag}
                      {active ? <span className="ml-2 text-xs text-success">(active)</span> : null}
                    </p>
                    <p className="text-xs text-slate-600">{tagInfo.file_count} files</p>
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

                <ul className="space-y-1 text-xs text-slate-700">
                  {tagInfo.files.map((fileInfo) => (
                    <li key={fileInfo.id} className="flex items-center justify-between rounded bg-slate-50 px-2 py-1">
                      <span>
                        {fileInfo.file_name} ({fileInfo.size_bytes} bytes)
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
