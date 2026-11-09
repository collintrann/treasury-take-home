import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BatchCheck } from "@/components/batch-check";
import { SingleCheck } from "@/components/single-check";

// Inactive tabs stay mounted (just hidden) so switching tabs never loses a
// filled-in form or stops a running batch.
const PANEL = "data-[state=inactive]:hidden";

export default function Home() {
  return (
    <>
      <header className="bg-primary text-primary-foreground">
        <div className="mx-auto max-w-6xl px-4 py-5">
          <h1 className="text-3xl font-bold">Label Check</h1>
          <p className="text-lg opacity-90">Compare an alcohol label against its application</p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Tabs defaultValue="single" className="gap-6">
          <TabsList className="w-full sm:w-fit">
            <TabsTrigger value="single">Check one label</TabsTrigger>
            <TabsTrigger value="batch">Check many labels</TabsTrigger>
          </TabsList>
          <TabsContent value="single" forceMount className={PANEL}>
            <SingleCheck />
          </TabsContent>
          <TabsContent value="batch" forceMount className={PANEL}>
            <BatchCheck />
          </TabsContent>
        </Tabs>
      </main>

      <footer className="mx-auto w-full max-w-6xl px-4 pt-6 pb-8 text-muted-foreground">
        Prototype. Not connected to COLA. Label images are not stored.
      </footer>
    </>
  );
}
