"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { ApiError } from "@/lib/api-client";
import { useCreateScan, useDatasets } from "@/lib/queries";
import type { IssueType, Sensitivity } from "@fastdup-dataset-cleaning/shared";

// Finite option sets — rendered as selectors, never free-text (Form UX rule a).
const SENSITIVITY_OPTIONS: { value: Sensitivity; label: string; hint: string }[] = [
  { value: "strict", label: "Strict (0.90)", hint: "Only near-identical images are flagged — fewest false positives." },
  { value: "balanced", label: "Balanced (0.85)", hint: "A good default: catches visual near-duplicates without over-flagging." },
  { value: "loose", label: "Loose (0.80)", hint: "Flags more loosely-similar images — highest recall, more review." },
];

const ISSUE_OPTIONS: { value: IssueType; label: string }[] = [
  { value: "duplicate", label: "Exact duplicates" },
  { value: "near_duplicate", label: "Near-duplicates" },
  { value: "outlier", label: "Outliers" },
  { value: "broken", label: "Broken / corrupt files" },
];

const schema = z.object({
  dataset: z.string().min(1, "Choose a dataset"),
  sensitivity: z.enum(["strict", "balanced", "loose"]),
  issue_types: z.array(z.enum(["duplicate", "near_duplicate", "outlier", "broken"])).min(1, "Select at least one issue type"),
  label: z.string().max(80, "Keep the label under 80 characters").optional(),
});

type ScanValues = z.infer<typeof schema>;

export function NewScanForm() {
  const router = useRouter();
  const { data: datasets, isLoading: datasetsLoading } = useDatasets();
  const createScan = useCreateScan();

  const form = useForm<ScanValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      // Safe-default guidance (Form UX rule b): default to the seeded demo
      // dataset. This is a hint via defaults + FormDescription, not an autofill button.
      dataset: "demo",
      sensitivity: "balanced",
      issue_types: ["duplicate", "near_duplicate", "outlier", "broken"],
      label: "",
    },
  });

  // Keep the selector value valid: if the demo dataset isn't present, select
  // the first real dataset once the list loads.
  const names = (datasets ?? []).map((d) => d.name);
  useEffect(() => {
    const current = form.getValues("dataset");
    if (names.length > 0 && !names.includes(current)) {
      form.setValue("dataset", names[0]);
    }
  }, [names, form]);

  const onSubmit = async (values: ScanValues) => {
    try {
      const run = await createScan.mutateAsync({
        dataset: values.dataset,
        sensitivity: values.sensitivity,
        issue_types: values.issue_types,
        label: values.label?.trim() || null,
      });
      toast.success("Scan started", { description: `Scanning “${values.dataset}”…` });
      router.push(`/scans/${run.run_id}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Could not start the scan";
      toast.error("Failed to start scan", { description: msg });
    }
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <Card>
          <CardHeader className="border-b border-border py-4 px-5">
            <CardTitle className="card-title">Scan configuration</CardTitle>
          </CardHeader>
          <CardContent className="p-5 space-y-6">
            <FormField
              control={form.control}
              name="dataset"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Dataset</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger className="w-72">
                        <SelectValue placeholder="Select a dataset" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {names.length === 0 ? (
                        <SelectItem value="demo">demo</SelectItem>
                      ) : (
                        names.map((n) => (
                          <SelectItem key={n} value={n}>
                            {n}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    {datasetsLoading
                      ? "Loading datasets…"
                      : names.length === 0
                        ? "No datasets found yet — run the seed script to create the demo dataset (see README)."
                        : "The seeded demo dataset is a good first run."}
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="sensitivity"
              render={({ field }) => {
                const active = SENSITIVITY_OPTIONS.find((o) => o.value === field.value);
                return (
                  <FormItem>
                    <FormLabel>Sensitivity</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger className="w-72">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {SENSITIVITY_OPTIONS.map((o) => (
                          <SelectItem key={o.value} value={o.value}>
                            {o.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>{active?.hint}</FormDescription>
                    <FormMessage />
                  </FormItem>
                );
              }}
            />

            <FormField
              control={form.control}
              name="issue_types"
              render={() => (
                <FormItem>
                  <FormLabel>Issue types to detect</FormLabel>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {ISSUE_OPTIONS.map((opt) => (
                      <FormField
                        key={opt.value}
                        control={form.control}
                        name="issue_types"
                        render={({ field }) => (
                          <FormItem className="flex flex-row items-start gap-3 space-y-0">
                            <FormControl>
                              <Checkbox
                                checked={field.value?.includes(opt.value)}
                                onCheckedChange={(checked) => {
                                  const set = new Set(field.value);
                                  if (checked) set.add(opt.value);
                                  else set.delete(opt.value);
                                  field.onChange(Array.from(set));
                                }}
                              />
                            </FormControl>
                            <FormLabel className="font-normal cursor-pointer">
                              {opt.label}
                            </FormLabel>
                          </FormItem>
                        )}
                      />
                    ))}
                  </div>
                  <FormDescription>All four are checked by default.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="label"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Run label (optional)</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g. Pre-training cleanup" className="w-72" {...field} />
                  </FormControl>
                  <FormDescription>A free-form name to recognise this run later.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => router.push("/scans")}>
            Cancel
          </Button>
          <Button type="submit" disabled={createScan.isPending}>
            {createScan.isPending ? "Starting…" : "Start scan"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
