import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createCtf, deleteCtf, getCtfs, updateCtf } from "@/api/endpoints";
import type { CTFCreateRequest, CTFUpdateRequest } from "@/api/models";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CTFdImportCard } from "@/features/integrations/CTFdImportCard";
import { CodexAuthCard } from "@/features/integrations/CodexAuthCard";

const ctfFormSchema = z.object({
  name: z.string().min(1, "Name is required"),
  slug: z.string().min(1, "Slug is required"),
  platform: z.string().optional(),
  default_flag_regex: z.string().optional(),
  notes: z.string().optional(),
});

type CTFFormValues = z.infer<typeof ctfFormSchema>;

function normalizeOptional(value: string | undefined): string | null {
  const trimmed = (value ?? "").trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function CTFsPage() {
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<string | null>(null);

  const ctfQuery = useQuery({
    queryKey: ["ctfs"],
    queryFn: getCtfs,
  });

  const createForm = useForm<CTFFormValues>({
    resolver: zodResolver(ctfFormSchema),
    defaultValues: {
      name: "",
      slug: "",
      platform: "manual",
      default_flag_regex: "flag\\{.*?\\}",
      notes: "",
    },
  });

  const editForm = useForm<CTFFormValues>({
    resolver: zodResolver(ctfFormSchema),
    defaultValues: {
      name: "",
      slug: "",
      platform: "",
      default_flag_regex: "",
      notes: "",
    },
  });

  const createMutation = useMutation({
    mutationFn: (values: CTFFormValues) => {
      const payload: CTFCreateRequest = {
        name: values.name.trim(),
        slug: values.slug.trim(),
        platform: normalizeOptional(values.platform),
        default_flag_regex: normalizeOptional(values.default_flag_regex),
        notes: normalizeOptional(values.notes),
      };
      return createCtf(payload);
    },
    onSuccess: () => {
      createForm.reset({
        name: "",
        slug: "",
        platform: "manual",
        default_flag_regex: "flag\\{.*?\\}",
        notes: "",
      });
      void queryClient.invalidateQueries({ queryKey: ["ctfs"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: (values: CTFFormValues) => {
      if (!editingId) {
        throw new Error("No CTF selected");
      }

      const payload: CTFUpdateRequest = {
        name: values.name.trim(),
        slug: values.slug.trim(),
        platform: normalizeOptional(values.platform),
        default_flag_regex: normalizeOptional(values.default_flag_regex),
        notes: normalizeOptional(values.notes),
      };
      return updateCtf(editingId, payload);
    },
    onSuccess: () => {
      setEditingId(null);
      editForm.reset();
      void queryClient.invalidateQueries({ queryKey: ["ctfs"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCtf,
    onSuccess: () => {
      if (editingId) {
        setEditingId(null);
        editForm.reset();
      }
      void queryClient.invalidateQueries({ queryKey: ["ctfs"] });
      void queryClient.invalidateQueries({ queryKey: ["challenges"] });
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  useEffect(() => {
    if (!editingId || !ctfQuery.data) {
      return;
    }
    const selected = ctfQuery.data.items.find((item) => item.id === editingId);
    if (!selected) {
      return;
    }
    editForm.reset({
      name: selected.name,
      slug: selected.slug,
      platform: selected.platform ?? "",
      default_flag_regex: selected.default_flag_regex ?? "",
      notes: selected.notes ?? "",
    });
  }, [ctfQuery.data, editForm, editingId]);

  return (
    <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
      <Card>
        <h2 className="mb-1 text-lg font-bold">CTF Events</h2>
        <p className="mb-5 text-sm text-slate-600">Configure per-CTF defaults like flag format regex.</p>

        {ctfQuery.isLoading ? <p>Loading CTFs...</p> : null}
        {ctfQuery.error ? <p className="text-danger">Failed to load CTFs.</p> : null}

        {ctfQuery.data ? (
          <div className="space-y-3">
            {ctfQuery.data.items.length === 0 ? <p className="text-sm text-slate-600">No CTF events yet.</p> : null}
            {ctfQuery.data.items.map((ctf) => (
              <div key={ctf.id} className="rounded-lg border border-slate-200 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-semibold">{ctf.name}</p>
                    <p className="text-xs text-slate-600">
                      slug: {ctf.slug} | platform: {ctf.platform ?? "-"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="secondary"
                      type="button"
                      onClick={() => {
                        setEditingId(ctf.id);
                      }}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      type="button"
                      className="text-danger hover:text-danger"
                      disabled={deleteMutation.isPending}
                      onClick={() => {
                        if (!window.confirm(`Delete CTF '${ctf.name}' and all associated challenges/runs?`)) {
                          return;
                        }
                        deleteMutation.mutate(ctf.id);
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
                <p className="mt-2 text-xs text-slate-700">
                  default flag regex: <code>{ctf.default_flag_regex ?? "(none)"}</code>
                </p>
              </div>
            ))}
          </div>
        ) : null}
        {deleteMutation.isError ? <p className="mt-3 text-sm text-danger">Failed to delete CTF.</p> : null}
      </Card>

      <div className="space-y-4">
        <Card>
          <h3 className="mb-3 text-lg font-semibold">Create CTF</h3>
          <form
            className="space-y-3"
            onSubmit={createForm.handleSubmit((values) => {
              createMutation.mutate(values);
            })}
          >
            <div>
              <label className="mb-1 block text-sm font-medium">Name</label>
              <input className="w-full rounded-md border border-slate-300 px-3 py-2" {...createForm.register("name")} />
              {createForm.formState.errors.name ? <p className="mt-1 text-xs text-danger">{createForm.formState.errors.name.message}</p> : null}
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Slug</label>
              <input className="w-full rounded-md border border-slate-300 px-3 py-2" {...createForm.register("slug")} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Platform</label>
              <input className="w-full rounded-md border border-slate-300 px-3 py-2" {...createForm.register("platform")} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Default Flag Regex</label>
              <input className="w-full rounded-md border border-slate-300 px-3 py-2" {...createForm.register("default_flag_regex")} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Notes</label>
              <textarea className="min-h-20 w-full rounded-md border border-slate-300 px-3 py-2" {...createForm.register("notes")} />
            </div>
            {createMutation.isError ? <p className="text-sm text-danger">Failed to create CTF.</p> : null}
            <Button type="submit" className="w-full" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Creating..." : "Create CTF"}
            </Button>
          </form>
        </Card>

        {editingId ? (
          <Card>
            <h3 className="mb-3 text-lg font-semibold">Edit CTF</h3>
            <form
              className="space-y-3"
              onSubmit={editForm.handleSubmit((values) => {
                updateMutation.mutate(values);
              })}
            >
              <div>
                <label className="mb-1 block text-sm font-medium">Name</label>
                <input className="w-full rounded-md border border-slate-300 px-3 py-2" {...editForm.register("name")} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Slug</label>
                <input className="w-full rounded-md border border-slate-300 px-3 py-2" {...editForm.register("slug")} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Platform</label>
                <input className="w-full rounded-md border border-slate-300 px-3 py-2" {...editForm.register("platform")} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Default Flag Regex</label>
                <input className="w-full rounded-md border border-slate-300 px-3 py-2" {...editForm.register("default_flag_regex")} />
                <p className="mt-1 text-xs text-slate-600">Leave blank to disable CTF-level default regex.</p>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Notes</label>
                <textarea className="min-h-20 w-full rounded-md border border-slate-300 px-3 py-2" {...editForm.register("notes")} />
              </div>
              {updateMutation.isError ? <p className="text-sm text-danger">Failed to update CTF.</p> : null}
              <div className="flex gap-2">
                <Button type="submit" className="flex-1" disabled={updateMutation.isPending}>
                  {updateMutation.isPending ? "Saving..." : "Save Changes"}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    setEditingId(null);
                    editForm.reset();
                  }}
                >
                  Cancel
                </Button>
              </div>
            </form>
          </Card>
        ) : null}
        <CTFdImportCard />
        <CodexAuthCard />
      </div>
    </div>
  );
}
