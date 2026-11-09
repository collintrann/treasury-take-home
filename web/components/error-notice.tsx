import { CircleAlert, RotateCw } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export function ErrorNotice({ title, message, onRetry }: { title: string; message: string; onRetry: () => void }) {
  return (
    <Alert variant="fail" className="gap-y-2">
      <CircleAlert aria-hidden />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="grid gap-4">
        <p>{message}</p>
        <Button size="lg" onClick={onRetry} className="w-fit">
          <RotateCw aria-hidden />
          Try again
        </Button>
      </AlertDescription>
    </Alert>
  );
}
