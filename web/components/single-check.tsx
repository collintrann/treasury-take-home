"use client";

import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import Image from "next/image";
import { ImageUp, LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ResultView } from "@/components/result-view";
import { Step } from "@/components/step";
import { APPLICATION_FIELDS, emptyApplication, type Application } from "@/lib/fields";
import { fetchSample, getExamples, verifyLabel, type Example, type VerificationResult } from "@/lib/api";

type Phase =
  | { kind: "editing"; error?: string }
  | { kind: "checking" }
  | { kind: "done"; result: VerificationResult };

export function SingleCheck() {
  const [image, setImageState] = useState<{ file: File; url: string } | null>(null);
  const [application, setApplication] = useState<Application>(emptyApplication);
  const [phase, setPhase] = useState<Phase>({ kind: "editing" });
  const [examples, setExamples] = useState<Example[]>([]);
  const [exampleIndex, setExampleIndex] = useState("");
  const [dragging, setDragging] = useState(false);
  const resultRef = useRef<HTMLDivElement>(null);
  const checking = phase.kind === "checking";

  useEffect(() => {
    // Without examples the picker just stays hidden.
    getExamples().then(setExamples, () => {});
  }, []);

  useEffect(() => {
    if (phase.kind === "done") resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [phase.kind]);

  function setImage(file: File | null) {
    if (image) URL.revokeObjectURL(image.url);
    setImageState(file && { file, url: URL.createObjectURL(file) });
    setPhase({ kind: "editing" });
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file && !checking) setImage(file);
  }

  async function chooseExample(value: string) {
    setExampleIndex(value);
    const example = examples[Number(value)];
    setApplication({ ...emptyApplication(), ...example.application });
    try {
      setImage(await fetchSample(example.filename));
    } catch (error) {
      setPhase({ kind: "editing", error: (error as Error).message });
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!image) return setPhase({ kind: "editing", error: "Please choose a label image first (step 1)." });
    if (!Object.values(application).some((value) => value.trim())) {
      return setPhase({ kind: "editing", error: "Please fill in at least one field from the application (step 2)." });
    }
    setPhase({ kind: "checking" });
    try {
      const trimmed = Object.fromEntries(
        Object.entries(application).map(([key, value]) => [key, value.trim()]),
      ) as Application;
      setPhase({ kind: "done", result: await verifyLabel(image.file, trimmed) });
    } catch (error) {
      setPhase({ kind: "editing", error: (error as Error).message });
    }
  }

  function startOver() {
    setImage(null);
    setApplication(emptyApplication());
    setExampleIndex("");
  }

  return (
    <div className="grid gap-6">
      <form onSubmit={onSubmit} noValidate className="grid gap-6">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          <Step number={1} title="Label image">
            <label
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                "relative grid min-h-72 cursor-pointer place-items-center rounded-xl border-3 border-dashed border-input p-3 text-center",
                "hover:border-primary focus-within:border-primary focus-within:outline-3 focus-within:outline-offset-2 focus-within:outline-foreground",
                dragging && "border-primary bg-accent",
              )}
            >
              <input
                type="file"
                accept="image/*"
                disabled={checking}
                className="sr-only"
                onChange={(e) => setImage(e.target.files?.[0] ?? null)}
              />
              {image ? (
                <span className="relative block h-80 w-full">
                  <Image
                    src={image.url}
                    alt={`Preview of ${image.file.name}`}
                    fill
                    unoptimized
                    className="rounded-lg object-contain"
                  />
                </span>
              ) : (
                <span className="grid justify-items-center gap-2 text-muted-foreground">
                  <ImageUp className="size-12 text-primary" aria-hidden />
                  <span className="text-lg font-bold text-primary">Click to choose a photo</span>
                  <span>or drag it here</span>
                </span>
              )}
            </label>
            {image && <p className="mt-2 [overflow-wrap:anywhere] text-muted-foreground">{image.file.name}. Click the picture to change it.</p>}
            {examples.length > 0 && (
              <div className="mt-4 grid gap-2">
                <Label htmlFor="example">Try an example</Label>
                <Select value={exampleIndex} onValueChange={chooseExample} disabled={checking}>
                  <SelectTrigger id="example" className="w-full">
                    <SelectValue placeholder="Choose a sample label" />
                  </SelectTrigger>
                  <SelectContent position="popper">
                    {examples.map((example, i) => (
                      <SelectItem key={example.filename} value={String(i)}>
                        {example.what_this_tests || example.filename}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </Step>

          <Step number={2} title="What the application says">
            <p className="mb-4 text-muted-foreground">
              Fill in what you have. Blank fields are skipped. The government warning is always checked.
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              {APPLICATION_FIELDS.map((field) => (
                <div key={field.key} className={cn("grid content-start gap-2", field.wide && "sm:col-span-2")}>
                  <Label htmlFor={field.key}>
                    {field.label}
                    {field.hint && <span className="font-normal text-muted-foreground">({field.hint})</span>}
                  </Label>
                  <Input
                    id={field.key}
                    autoComplete="off"
                    placeholder={field.placeholder}
                    value={application[field.key]}
                    onChange={(e) => setApplication({ ...application, [field.key]: e.target.value })}
                  />
                </div>
              ))}
            </div>
          </Step>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <Button type="submit" size="lg" disabled={checking} className="min-w-60">
            {checking ? <LoaderCircle className="animate-spin" aria-hidden /> : null}
            {checking ? "Checking…" : "Check label"}
          </Button>
          <Button type="button" variant="link" onClick={startOver} disabled={checking} className="text-lg underline">
            Start over
          </Button>
        </div>
        {phase.kind === "editing" && phase.error && (
          <Alert variant="destructive">
            <AlertDescription>{phase.error}</AlertDescription>
          </Alert>
        )}
      </form>

      <div ref={resultRef} aria-live="polite" className="scroll-mt-4">
        {phase.kind === "done" && <ResultView result={phase.result} />}
      </div>
    </div>
  );
}
