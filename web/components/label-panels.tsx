"use client";

import { useState } from "react";
import Image from "next/image";
import { Maximize, X, ZoomIn } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

// An application's label artwork, often split into front, back and neck
// panels. The chosen panel is shown large; the others are thumbnails.
export function LabelPanels({ images, brand }: { images: string[]; brand: string }) {
  const [shown, setShown] = useState(0);
  const count = images.length;
  const panelName = (index: number) => (count === 1 ? "Label image" : `Label panel ${index + 1} of ${count}`);

  return (
    <div className="grid gap-3">
      <LabelImage
        src={images[shown]}
        title={panelName(shown)}
        alt={`${panelName(shown)}, label artwork for ${brand}`}
        caption={
          count === 1
            ? "Label as submitted. Click the image to enlarge it."
            : `Panel ${shown + 1} of ${count} as submitted. Click the image to enlarge it, or choose another panel below.`
        }
      />
      {count > 1 && (
        <ul aria-label="Label panels" className="flex flex-wrap gap-3">
          {images.map((src, index) => (
            <li key={src}>
              <Button
                variant="outline"
                aria-label={panelName(index)}
                aria-pressed={index === shown}
                onClick={() => setShown(index)}
                className="relative size-24 bg-muted p-0 aria-pressed:border-3 aria-pressed:border-foreground"
              >
                <Image src={src} alt="" fill unoptimized sizes="6rem" className="object-contain p-1.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LabelImage({ src, title, alt, caption }: { src: string; title: string; alt: string; caption: string }) {
  const [actualSize, setActualSize] = useState(false);

  return (
    <Dialog onOpenChange={() => setActualSize(false)}>
      <figure className="grid gap-2">
        <DialogTrigger className="group relative block h-[min(60dvh,36rem)] w-full cursor-zoom-in overflow-hidden rounded-xl border bg-muted focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-foreground lg:h-[min(calc(100dvh-8rem),52rem)]">
          <Image src={src} alt={alt} fill unoptimized priority className="object-contain object-top p-3" />
          <span className="absolute right-3 bottom-3 inline-flex items-center gap-2 rounded-lg bg-card px-3 py-2 font-bold text-foreground ring-1 ring-foreground/15 group-hover:bg-muted">
            <ZoomIn className="size-5" aria-hidden />
            Zoom
          </span>
        </DialogTrigger>
        <figcaption className="text-muted-foreground">{caption}</figcaption>
      </figure>

      <DialogContent
        showCloseButton={false}
        aria-describedby={undefined}
        className="inset-0 top-0 left-0 grid h-dvh max-w-none translate-x-0 translate-y-0 grid-rows-[auto_1fr] gap-0 rounded-none bg-background p-0 sm:inset-4 sm:h-auto sm:max-w-none sm:rounded-xl"
      >
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-3">
          <DialogTitle className="mr-auto pr-0">{title}</DialogTitle>
          <Button variant="outline" onClick={() => setActualSize(!actualSize)}>
            {actualSize ? <Maximize aria-hidden /> : <ZoomIn aria-hidden />}
            {actualSize ? "Fit to screen" : "Actual size"}
          </Button>
          <DialogClose asChild>
            <Button>
              <X aria-hidden />
              Close
            </Button>
          </DialogClose>
        </div>
        <div className={cn("min-h-0 overflow-auto bg-muted", !actualSize && "grid place-items-center")}>
          <Image
            src={src}
            alt={alt}
            width={0}
            height={0}
            unoptimized
            onClick={() => setActualSize(!actualSize)}
            className={cn(
              "h-auto w-auto",
              actualSize ? "mx-auto block max-w-none cursor-zoom-out" : "max-h-full max-w-full cursor-zoom-in object-contain p-4",
            )}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
